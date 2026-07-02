"""
The :class:`Run` context manager.

Usage::

    import mltracker

    mltracker.login()

    with mltracker.run("iris-v1", experiment_id=1, params={"lr": 0.01}) as run:
        run.log_param("model", "RandomForest")
        for epoch in range(10):
            ...
            run.log_metric("loss", loss, step=epoch)
        run.log_metrics({"acc": acc, "f1": f1})

On ``__exit__`` the run is automatically marked ``FINISHED``. If the
block raises, the run is marked ``FAILED`` and the exception is
re-raised (we don't swallow user code errors).

If you want manual control, use the lower-level ``client.runs`` API.
"""
from __future__ import annotations

import logging
from types import TracebackType
from typing import Any, Dict, Mapping, Optional, Type, Union

from .client import MLTrackerClient
from .types import Run as RunModel, RunStatus

logger = logging.getLogger(__name__)


class Run:
    """
    A single training run — like ``mlflow.start_run()`` but bound to the
    ML Tracker backend.

    Constructed via the :func:`mltracker.run` helper. The context-manager
    protocol handles the lifecycle::

        with mltracker.run(...) as r:
            ...
    """

    def __init__(
        self,
        client: MLTrackerClient,
        experiment_id: int,
        run_name: Optional[str] = None,
        parameters: Optional[Mapping[str, Any]] = None,
        tags: Optional[Mapping[str, Any]] = None,
    ):
        self._client = client
        self._experiment_id = experiment_id
        self._run_name = run_name
        self._parameters = dict(parameters or {})
        self._tags = dict(tags or {})
        self._model: Optional[RunModel] = None
        self._finished = False
        self._failed = False

    # ─── Properties ───────────────────────────────────────────────────
    @property
    def id(self) -> int:
        """Backend ID of the run. Raises if the run isn't started yet."""
        if self._model is None:
            raise RuntimeError("Run has not been started yet.")
        return self._model.id

    @property
    def model(self) -> RunModel:
        """The underlying :class:`Run` Pydantic model (i.e. a snapshot)."""
        if self._model is None:
            raise RuntimeError("Run has not been started yet.")
        return self._model

    @property
    def is_finished(self) -> bool:
        return self._finished

    @property
    def status(self) -> Optional[RunStatus]:
        return None if self._model is None else self._model.status

    # ─── Context manager ──────────────────────────────────────────────
    def __enter__(self) -> "Run":
        # Build the payload. Backend accepts initial parameters in the
        # create call, so we only need a follow-up PATCH to merge extras
        # if the user passes them.
        from .types import RunCreate  # local import to avoid a cycle

        try:
            self._model = self._client.runs.create(
                RunCreate(
                    experiment_id=self._experiment_id,
                    run_name=self._run_name,
                    status=RunStatus.RUNNING,
                    parameters=self._parameters or None,
                    tags=self._tags or None,
                )
            )
        except Exception as e:
            # If even creation fails, we have no run to update. The
            # exception bubbles out of ``__enter__`` and Python's ``with``
            # statement treats the block as not entered — so __exit__
            # won't be called. That's the correct behaviour: nothing to
            # clean up.
            logger.error("Failed to start run: %s", e)
            raise
        return self

    def __exit__(
        self,
        exc_type: Optional[Type[BaseException]],
        exc_val: Optional[BaseException],
        exc_tb: Optional[TracebackType],
    ) -> None:
        # Returning None / False means "don't swallow the exception".
        if exc_type is not None:
            self.fail(reason=repr(exc_val))
            return

        if not self._finished:
            self.finish()

    # ─── Logging helpers ──────────────────────────────────────────────
    def log_param(self, key: str, value: Any) -> None:
        """Log a single hyperparameter. Value is stringified (backend contract)."""
        self._require_started()
        # Backend expects string for parameter value
        self._client.runs.log_parameter(self.id, key, str(value))
        # The backend returns the updated Run; we don't need to re-fetch
        # because every log call hits the server (single source of truth).

    def log_params(self, params: Mapping[str, Any]) -> None:
        """Log many parameters in one logical operation (still N HTTP calls)."""
        for k, v in params.items():
            self.log_param(k, v)

    def log_metric(
        self,
        key: str,
        value: float,
        *,
        step: Optional[int] = None,
    ) -> None:
        """Log a single scalar metric, optionally with a step (epoch)."""
        self._require_started()
        self._client.runs.log_metric(self.id, key, float(value), step=step)

    def log_metrics(
        self,
        metrics: Mapping[str, float],
        *,
        step: Optional[int] = None,
    ) -> None:
        """Log many metrics at once. The backend accepts them individually,
        so this is a thin loop — useful for end-of-epoch ``{loss, acc, f1}``
        style logging."""
        for k, v in metrics.items():
            self.log_metric(k, v, step=step)

    def set_tag(self, key: str, value: Any) -> None:
        """Add or update a tag. Tags are merged on the server side via PATCH."""
        self._require_started()
        self._client.runs.update(self.id, {"tags": {key: value}})

    # ─── Terminal actions ─────────────────────────────────────────────
    def finish(
        self,
        *,
        status: Union[str, RunStatus] = RunStatus.FINISHED,
    ) -> None:
        """Mark the run as ``FINISHED`` (or any other terminal status)."""
        self._require_started()
        if self._finished:
            return
        status_str = status.value if isinstance(status, RunStatus) else str(status)
        try:
            self._model = self._client.runs.finish(self.id, status=status_str)
        except Exception as e:
            # The user's ``with`` block succeeded, but we couldn't mark
            # the run finished. Log loudly — the backend still has a
            # RUNNING run that needs cleanup.
            logger.error("Failed to mark run %s as %s: %s", self.id, status_str, e)
            raise
        self._finished = True
        logger.debug("Run %s marked %s", self.id, status_str)

    def fail(self, reason: Optional[str] = None) -> None:
        """Mark the run as ``FAILED``. Idempotent. ``reason`` is logged but
        not stored on the server (the backend schema doesn't have a
        failure_reason column yet)."""
        self._require_started()
        if self._finished:
            return
        if reason:
            logger.warning("Run %s failed: %s", self.id, reason)
        try:
            self._model = self._client.runs.finish(self.id, status=RunStatus.FAILED.value)
        except Exception as e:
            # Best-effort — if even the FAIL call fails (network down),
            # the user gets a logged warning and a stale RUNNING row in
            # the backend. They'll see it in the UI as a stuck run.
            logger.error("Failed to mark run %s as FAILED: %s", self.id, e)
            return
        self._finished = True
        self._failed = True

    # ─── Helpers ──────────────────────────────────────────────────────
    def _require_started(self) -> None:
        if self._model is None:
            raise RuntimeError(
                "Run methods must be called inside the `with` block "
                "(i.e. after __enter__ has run)."
            )


# ════════════════════════════════════════════════════════════════════════
#  Module-level helper
# ════════════════════════════════════════════════════════════════════════


def run(
    run_name: Optional[str] = None,
    *,
    experiment_id: Optional[int] = None,
    experiment_name: Optional[str] = None,
    parameters: Optional[Mapping[str, Any]] = None,
    tags: Optional[Mapping[str, Any]] = None,
) -> Run:
    """
    Start a new :class:`Run` against the singleton client.

    Exactly one of ``experiment_id`` / ``experiment_name`` must be
    supplied. If a name is given, the SDK looks up the experiment
    (creating it if missing — handy for quick scripts).

    Examples::

        with mltracker.run(experiment_id=1, run_name="rf-v1") as r:
            ...

        with mltracker.run(experiment_name="iris", run_name="rf-v1") as r:
            ...
    """
    from . import _get_client  # avoid circular import at module load

    if (experiment_id is None) == (experiment_name is None):
        raise ValueError("Provide exactly one of `experiment_id` or `experiment_name`.")

    client = _get_client()

    if experiment_id is None:
        # Resolve by name. We do a quick create-if-missing dance so the
        # user doesn't have to spin up an experiment first.
        experiment_id = _resolve_experiment_id(client, experiment_name)  # type: ignore[arg-type]

    return Run(
        client=client,
        experiment_id=experiment_id,
        run_name=run_name,
        parameters=parameters,
        tags=tags,
    )


def _resolve_experiment_id(client: MLTrackerClient, name: str) -> int:
    """Look up an experiment by name; create it if it doesn't exist."""
    # ``list`` is paginated; we cap at 200 and assume experiments are
    # roughly in name-order. For huge registries this should switch to
    # a dedicated /experiments/by-name endpoint, but that doesn't exist
    # in the backend yet.
    try:
        for exp in client.experiments.list(limit=200, search=name):
            if exp.name == name:
                return exp.id
    except Exception:
        # If even listing fails (e.g. no network), fall through to create.
        pass

    from .types import ExperimentCreate

    created = client.experiments.create(ExperimentCreate(name=name))
    return created.id
