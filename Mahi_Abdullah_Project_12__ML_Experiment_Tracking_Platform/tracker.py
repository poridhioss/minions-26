"""Python SDK for logging ML experiments to the local SQLite tracker.

Public API:
    start_run(name, project=None, tags=None, notes=None) -> Run

`Run` exposes:
    .log_params(params: dict)
    .log_epoch(metric_name: str, value: float, step: int)
    .log_metric(metric_name: str, value: float, step: int | None = None)
    .finish(metrics: dict | None = None, status: str = "completed")

Usage:
    from tracker import start_run

    run = start_run(name="ResNet Test", project="Vision", tags="CNN,test")
    run.log_params({"lr": 0.001, "epochs": 10, "batch_size": 32})
    for epoch in range(10):
        run.log_epoch("accuracy", 0.85 + epoch * 0.01, epoch)
        run.log_epoch("loss", 0.5 - epoch * 0.03, epoch)
    run.finish(metrics={"accuracy": 0.94, "loss": 0.21})
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Dict, Optional

from database import get_db, init_db

# Defensive: make sure the schema (including the `end_time` column added in
# Prompt 2) exists even if the SDK is used without booting Flask first.
init_db()


# Valid terminal states for an experiment. Kept tiny on purpose.
_TERMINAL_STATUSES = {"completed", "failed", "crashed", "killed"}


def _utc_now() -> str:
    """Return the current UTC time as an ISO-8601 string."""
    return datetime.utcnow().isoformat(timespec="seconds")


class Run:
    """A single training run bound to a row in the `experiments` table."""

    def __init__(self, run_id: int, name: str, project: Optional[str],
                 tags: Optional[str], notes: Optional[str]) -> None:
        self.id = run_id
        self.name = name
        self.project = project
        self.tags = tags
        self.notes = notes
        self._finished = False

    # ------------------------------------------------------------------ #
    # Param / metric logging                                              #
    # ------------------------------------------------------------------ #
    def log_params(self, params: Dict[str, Any]) -> None:
        """Persist hyper-parameters as JSON on the experiment row."""
        if self._finished:
            raise RuntimeError(
                f"Run {self.id} is already finished; start a new run to log more."
            )
        if not isinstance(params, dict):
            raise TypeError("log_params() expects a dict of name -> value")

        payload = json.dumps(params, ensure_ascii=False, sort_keys=True)
        conn = get_db()
        try:
            conn.execute(
                "UPDATE experiments SET params = ? WHERE id = ?",
                (payload, self.id),
            )
            conn.commit()
        finally:
            conn.close()

    def log_epoch(self, metric_name: str, value: float, step: int) -> None:
        """Insert one per-step metric reading into `epoch_metrics`."""
        # `log_epoch` is the name in the spec; keep it as the primary API.
        self.log_metric(metric_name, value, step)

    def log_metric(self, metric_name: str, value: float,
                   step: Optional[int] = None) -> None:
        """Insert a metric reading. `step` is required by the schema."""
        if self._finished:
            raise RuntimeError(
                f"Run {self.id} is already finished; start a new run to log more."
            )
        if step is None:
            raise ValueError("step is required when logging epoch metrics")
        try:
            numeric_value = float(value)
        except (TypeError, ValueError) as exc:
            raise TypeError(
                f"metric value must be numeric, got {type(value).__name__}"
            ) from exc

        conn = get_db()
        try:
            conn.execute(
                """
                INSERT INTO epoch_metrics (experiment_id, metric_name, value, step)
                VALUES (?, ?, ?, ?)
                """,
                (self.id, metric_name, numeric_value, int(step)),
            )
            conn.commit()
        finally:
            conn.close()

    # ------------------------------------------------------------------ #
    # Lifecycle                                                           #
    # ------------------------------------------------------------------ #
    def finish(self, metrics: Optional[Dict[str, Any]] = None,
               status: str = "completed") -> None:
        """Mark the run as done, persist final metrics, stamp end time."""
        if self._finished:
            return  # Idempotent: double-finish is a no-op.

        if status not in _TERMINAL_STATUSES:
            raise ValueError(
                f"status must be one of {sorted(_TERMINAL_STATUSES)}, got {status!r}"
            )

        metrics_json = (
            json.dumps(metrics, ensure_ascii=False, sort_keys=True)
            if metrics is not None
            else None
        )

        conn = get_db()
        try:
            conn.execute(
                """
                UPDATE experiments
                   SET metrics  = COALESCE(?, metrics),
                       status   = ?,
                       end_time = ?
                 WHERE id = ?
                """,
                (metrics_json, status, _utc_now(), self.id),
            )
            conn.commit()
        finally:
            conn.close()

        self._finished = True

    # ------------------------------------------------------------------ #
    # Ergonomics                                                           #
    # ------------------------------------------------------------------ #
    def __enter__(self) -> "Run":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        if not self._finished:
            status = "failed" if exc_type is not None else "completed"
            try:
                self.finish(status=status)
            except Exception:
                # Never let cleanup swallow the original exception.
                pass

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return (
            f"Run(id={self.id}, name={self.name!r}, project={self.project!r}, "
            f"tags={self.tags!r}, finished={self._finished})"
        )


def start_run(name: str,
              project: Optional[str] = None,
              tags: Optional[str] = None,
              notes: Optional[str] = None,
              status: str = "running") -> Run:
    """Insert a new experiment row and return a `Run` bound to it.

    Args:
        name:    Human-readable run name.
        project: Optional grouping/project label.
        tags:    Free-form tag string (e.g. "CNN,test").
        notes:   Optional free-form notes.
        status:  Initial status; defaults to "running" per the spec.
    """
    if not name:
        raise ValueError("`name` is required when starting a run")

    conn = get_db()
    try:
        cursor = conn.execute(
            """
            INSERT INTO experiments (name, project, tags, notes, status)
            VALUES (?, ?, ?, ?, ?)
            """,
            (name, project, tags, notes, status),
        )
        conn.commit()
        run_id = cursor.lastrowid
    finally:
        conn.close()

    return Run(run_id=run_id, name=name, project=project,
               tags=tags, notes=notes)
