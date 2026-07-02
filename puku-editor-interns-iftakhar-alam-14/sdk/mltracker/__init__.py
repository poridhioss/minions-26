"""
mltracker — Python SDK for the ML Experiment Tracking Platform.

A thin, typed wrapper around the 20 HTTP endpoints exposed by the FastAPI
backend. Designed to feel like an ML library (``mltracker.run(...)``,
``mltracker.predict(...)``) rather than an HTTP client.

Typical usage::

    import mltracker

    mltracker.login(url="http://localhost:8000", api_key="...")

    exp = mltracker.experiments.create(name="iris-baseline")
    with mltracker.run(experiment_id=exp.id, name="rf-v1") as run:
        run.log_param("n_estimators", 100)
        run.log_metric("accuracy", 0.94)

    print(mltracker.predict(model_name="rf-v1", features=[5.1, 3.5, 1.4, 0.2]))

Or set environment variables (``MLTRACKER_URL``, ``MLTRACKER_API_KEY``) and
skip the explicit ``login()`` call entirely.
"""
from __future__ import annotations

import os
from typing import Any, Mapping, Optional, Sequence, Union

from .client import MLTrackerClient
from .exceptions import (
    APIError,
    AuthenticationError,
    MLTrackerError,
    NotFoundError,
    ValidationError,
)
from .runs import Run, run
from . import types as types_module
from .types import (
    Experiment,
    ExperimentCreate,
    ExperimentUpdate,
    HealthResponse,
    ModelVersion,
    ParameterIn,
    PredictRequest,
    PredictResponse,
    RegisteredModel,
    RunCreate,
    RunStatus,
    RunUpdate,
    Status,
)

__version__ = "0.1.0"

__all__ = [
    # Version
    "__version__",
    # Exceptions
    "APIError",
    "AuthenticationError",
    "MLTrackerError",
    "NotFoundError",
    "ValidationError",
    # Client + session
    "MLTrackerClient",
    "login",
    "is_configured",
    # Top-level helpers
    "experiments",
    "runs",
    "models",
    "predict",
    "Run",
    "run",
    # Re-exports for type hints
    "Experiment",
    "ExperimentCreate",
    "ExperimentUpdate",
    "HealthResponse",
    "ModelVersion",
    "ParameterIn",
    "PredictRequest",
    "PredictResponse",
    "RegisteredModel",
    "RunCreate",
    "RunStatus",
    "RunUpdate",
    "Status",
]


# ════════════════════════════════════════════════════════════════════════
#  Module-level singleton client
# ════════════════════════════════════════════════════════════════════════
#
# The TS frontend has ``axios.create({})`` as a module-level singleton.
# We follow the same pattern: importable helpers (``mltracker.experiments``,
# ``mltracker.predict``) are thin facades over a single ``MLTrackerClient``
# instance that the user configures once via ``login()`` (or env vars).
#
# This means most user code never has to hold a client object — it can just
# call ``mltracker.experiments.list()`` and trust that ``login()`` (or the
# env) has been set up first. Tests that need isolation can ignore the
# singleton and instantiate ``MLTrackerClient(...)`` directly.
_client: Optional[MLTrackerClient] = None


def _get_client() -> MLTrackerClient:
    """
    Return the singleton client, creating it lazily from env vars if needed.

    Raises
    ------
    RuntimeError
        If neither :func:`login` was called nor ``MLTRACKER_URL`` /
        ``MLTRACKER_API_KEY`` are set. The facades surface this through
        their ``__getattr__`` so a user who forgets ``login()`` sees a
        helpful error instead of a silent attempt to talk to
        ``localhost:8000``.
    """
    global _client
    if _client is None:
        if not (os.getenv("MLTRACKER_URL") or os.getenv("MLTRACKER_API_KEY")):
            raise RuntimeError(
                "mltracker is not configured: call mltracker.login(url=..., api_key=...) "
                "or set the MLTRACKER_URL / MLTRACKER_API_KEY environment variables."
            )
        _client = MLTrackerClient.from_env()
    return _client


def login(
    url: Optional[str] = None,
    *,
    api_key: Optional[str] = None,
    timeout: float = 30.0,
    client: Optional[MLTrackerClient] = None,
) -> MLTrackerClient:
    """
    Configure the global SDK client. Call this once at the top of your script.

    Parameters
    ----------
    url
        Base URL of the FastAPI backend, e.g. ``"http://localhost:8000"``.
        Falls back to ``MLTRACKER_URL`` env var, then ``http://localhost:8000``.
    api_key
        API key sent as the ``X-API-Key`` header. Falls back to
        ``MLTRACKER_API_KEY`` env var.
    timeout
        HTTP request timeout in seconds. Default 30.
    client
        Pre-built :class:`MLTrackerClient` to install as the singleton.
        Useful for tests that want to inject a ``TestClient``-backed client.

    Returns
    -------
    The (new) global :class:`MLTrackerClient` instance.
    """
    global _client
    if client is not None:
        _client = client
        return _client
    # ``url`` and ``api_key`` fall back to the same env vars the
    # ``from_env`` classmethod uses, so ``login()`` with no args and
    # ``MLTrackerClient.from_env()`` produce identical clients.
    if url is None:
        url = os.getenv("MLTRACKER_URL")
    if api_key is None:
        api_key = os.getenv("MLTRACKER_API_KEY")
    _client = MLTrackerClient(url=url, api_key=api_key, timeout=timeout)
    return _client


def is_configured() -> bool:
    """Return True if ``login()`` has been called or env vars are set."""
    if _client is not None:
        return True
    return bool(os.getenv("MLTRACKER_URL") or os.getenv("MLTRACKER_API_KEY"))


def reset() -> None:
    """Drop the cached singleton. Test-only helper."""
    global _client
    _client = None


# ════════════════════════════════════════════════════════════════════════
#  Top-level facades — these are what user code calls
# ════════════════════════════════════════════════════════════════════════


class _ExperimentsFacade:
    """Proxy for ``client.experiments.*`` so callers can write ``mltracker.experiments.list()``."""

    def __getattr__(self, name: str):
        return getattr(_get_client().experiments, name)


class _RunsFacade:
    """Proxy for ``client.runs.*`` (CRUD only). The context manager is :func:`mltracker.run`."""

    def __getattr__(self, name: str):
        return getattr(_get_client().runs, name)


class _ModelsFacade:
    """Proxy for ``client.models.*``."""

    def __getattr__(self, name: str):
        return getattr(_get_client().models, name)


experiments = _ExperimentsFacade()
runs = _RunsFacade()
models = _ModelsFacade()


def predict(
    features: Union[Sequence[Any], Mapping[str, Any]],
    *,
    model_name: Optional[str] = None,
    model_uri: Optional[str] = None,
    stage: str = "Production",
) -> PredictResponse:
    """
    Run inference against a registered model. Thin wrapper over
    :meth:`MLTrackerClient.predictions.predict`.

    Provide ``model_uri`` OR (``model_name`` + optional ``stage``).
    """
    return _get_client().predictions.predict(
        features=features,
        model_name=model_name,
        model_uri=model_uri,
        stage=stage,
    )


def health() -> HealthResponse:
    """Return the backend's ``/health`` payload as a :class:`HealthResponse`."""
    return _get_client().health.get()
