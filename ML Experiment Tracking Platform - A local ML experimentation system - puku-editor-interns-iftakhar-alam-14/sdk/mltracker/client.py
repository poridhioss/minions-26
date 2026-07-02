"""
Core HTTP client.

Mirrors the structure of ``frontend/src/api/client.ts``:
  • One ``httpx.Client`` per :class:`MLTrackerClient` instance.
  • Request interceptor that adds ``X-API-Key`` (analogue of the TS
    request interceptor pulling the key from ``localStorage``).
  • Response interceptor that maps non-2xx responses to typed exceptions
    (analogue of the TS response interceptor toasting ``detail``).
  • Five endpoint groups (``experiments``, ``runs``, ``models``,
    ``predictions``, ``health``) implemented as small ``_EndpointGroup``
    instances so they share the same underlying client.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Dict, Mapping, Optional, Sequence, Type, TypeVar, Union

import httpx
from pydantic import TypeAdapter

from . import exceptions as exc
from .types import (
    Experiment,
    ExperimentCreate,
    ExperimentUpdate,
    FinishRunIn,
    HealthResponse,
    MetricIn,
    ModelVersion,
    ParameterIn,
    PredictRequest,
    PredictResponse,
    RegisteredModel,
    Run,
    RunCreate,
    RunUpdate,
)

T = TypeVar("T")


# ════════════════════════════════════════════════════════════════════════
#  MLTrackerClient
# ════════════════════════════════════════════════════════════════════════


class MLTrackerClient:
    """
    A thin, typed HTTP client for the ML Tracker backend.

    Typical usage::

        client = MLTrackerClient(url="http://localhost:8000", api_key="...")
        experiments = client.experiments.list()
        for exp in experiments:
            print(exp.id, exp.name)

    Or skip the manual instantiation and just call ``mltracker.login(...)``
    + ``mltracker.experiments.list()`` (the top-level helpers share a
    singleton client).
    """

    DEFAULT_TIMEOUT = 30.0
    DEFAULT_BASE_URL = "http://localhost:8000"
    API_PREFIX = "/api/v1"

    def __init__(
        self,
        url: Optional[str] = None,
        *,
        api_key: Optional[str] = None,
        timeout: float = DEFAULT_TIMEOUT,
        transport: Optional[httpx.BaseTransport] = None,
        headers: Optional[Mapping[str, str]] = None,
    ):
        # Store the base URL; strip trailing slash and any user-supplied
        # ``/api/v1`` suffix (we add it ourselves).
        base = (url or self.DEFAULT_BASE_URL).rstrip("/")
        if base.endswith(self.API_PREFIX):
            base = base[: -len(self.API_PREFIX)]
        self.base_url = base

        self.api_key = api_key or os.getenv("MLTRACKER_API_KEY", "")

        # Build the persistent headers. The X-API-Key header is added on
        # every request via the request event hook so it stays current if
        # the user mutates ``self.api_key`` after construction.
        default_headers = {"Content-Type": "application/json", "Accept": "application/json"}
        if headers:
            default_headers.update(dict(headers))
        self._default_headers = default_headers

        # The transport argument is the test seam — tests pass
        # ``httpx.MockTransport`` to fake responses without a real server.
        self._http = httpx.Client(
            base_url=base,
            timeout=timeout,
            headers=default_headers,
            transport=transport,
            event_hooks={"request": [self._add_api_key]},
        )

        # Endpoint groups — lazy attribute so ``MLTrackerClient(url=...)``
        # doesn't even construct them if the user only calls ``.health``.
        self._experiments: Optional[_ExperimentsAPI] = None
        self._runs: Optional[_RunsAPI] = None
        self._models: Optional[_ModelsAPI] = None
        self._predictions: Optional[_PredictionsAPI] = None
        self._health: Optional[_HealthAPI] = None

    # ─── Lifecycle ────────────────────────────────────────────────────
    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> "MLTrackerClient":
        return self

    def __exit__(self, *exc_info: Any) -> None:
        self.close()

    @classmethod
    def from_env(cls) -> "MLTrackerClient":
        """
        Build a client from environment variables:
            MLTRACKER_URL      (default: http://localhost:8000)
            MLTRACKER_API_KEY  (no default — required for real auth)
        """
        return cls(
            url=os.getenv("MLTRACKER_URL"),
            api_key=os.getenv("MLTRACKER_API_KEY"),
        )

    # ─── Property-style endpoint groups ──────────────────────────────
    @property
    def experiments(self) -> "_ExperimentsAPI":
        if self._experiments is None:
            self._experiments = _ExperimentsAPI(self)
        return self._experiments

    @property
    def runs(self) -> "_RunsAPI":
        if self._runs is None:
            self._runs = _RunsAPI(self)
        return self._runs

    @property
    def models(self) -> "_ModelsAPI":
        if self._models is None:
            self._models = _ModelsAPI(self)
        return self._models

    @property
    def predictions(self) -> "_PredictionsAPI":
        if self._predictions is None:
            self._predictions = _PredictionsAPI(self)
        return self._predictions

    @property
    def health(self) -> "_HealthAPI":
        if self._health is None:
            self._health = _HealthAPI(self)
        return self._health

    # ─── Low-level HTTP ──────────────────────────────────────────────
    def _add_api_key(self, request: httpx.Request) -> None:
        """Event hook: attach X-API-Key on every outgoing request."""
        if self.api_key:
            request.headers["X-API-Key"] = self.api_key

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: Optional[Mapping[str, Any]] = None,
        json: Any = None,
        model: Optional[Type[T]] = None,
    ) -> Union[T, Any]:
        """
        Single funnel for every HTTP call:
          1. Build the URL (path is relative; we add the /api/v1 prefix).
          2. Make the request via the underlying ``httpx.Client``.
          3. Raise a typed exception on non-2xx (see ``exceptions.py``).
          4. Optionally validate the response body through a Pydantic model.

        ``model=None`` means "return the raw JSON dict" (useful for the
        ``/predictions/predict`` endpoint whose response shape depends on
        the model).
        """
        if not path.startswith("/"):
            path = "/" + path

        # Every endpoint lives under ``/api/v1`` *except* ``/health`` (which
        # is mounted at the FastAPI app root for liveness probes). Adding
        # the prefix here keeps endpoint groups short and makes it
        # impossible to accidentally hit the unversioned path.
        if not path.startswith("/health"):
            path = self.API_PREFIX + path

        try:
            response = self._http.request(
                method,
                path,
                params=params,
                json=json,
            )
        except httpx.RequestError as e:
            # Connection error, timeout, etc.
            raise exc.APIError(f"Network error contacting {self.base_url}: {e}") from e

        # Raise a typed exception on non-2xx
        if response.status_code >= 400:
            self._raise_for_status(response)

        # 204 No Content (e.g. DELETE) — return None
        if response.status_code == 204 or not response.content:
            return None

        body = response.json()
        if model is not None:
            # ``list[Experiment]`` / ``Sequence[Run]`` etc. don't have a
            # ``model_validate`` of their own — they're ``typing`` aliases.
            # Pydantic's ``TypeAdapter`` is the universal entry point that
            # handles bare classes *and* parameterized generics uniformly.
            return TypeAdapter(model).validate_python(body)
        return body

    def _raise_for_status(self, response: httpx.Response) -> None:
        """Map ``response`` to the right :class:`MLTrackerError` subclass."""
        cls = exc.exception_for_status(response.status_code)
        try:
            body: Any = response.json()
        except Exception:
            body = response.text
        message = exc._extract_detail(body) or response.reason_phrase or f"HTTP {response.status_code}"
        raise cls(message, status_code=response.status_code, body=body)


# ════════════════════════════════════════════════════════════════════════
#  Endpoint groups
# ════════════════════════════════════════════════════════════════════════
#
# Each group is a tiny façade over ``MLTrackerClient._request`` with the
# Pydantic model already bound. This keeps the call sites short while
# centralising the URL paths and HTTP verbs in one place per resource.


@dataclass
class _BaseAPI:
    client: MLTrackerClient

    # ─── Internal helper used by every endpoint ───────────────────────
    def _do(
        self,
        method: str,
        path: str,
        *,
        params: Optional[Mapping[str, Any]] = None,
        json: Any = None,
        model: Optional[Type[T]] = None,
    ) -> Union[T, Any]:
        return self.client._request(method, path, params=params, json=json, model=model)


class _ExperimentsAPI(_BaseAPI):
    """CRUD for ``/api/v1/experiments``."""

    PREFIX = "/experiments"

    def list(
        self,
        *,
        skip: int = 0,
        limit: int = 50,
        search: Optional[str] = None,
    ) -> Sequence[Experiment]:
        params: Dict[str, Any] = {"skip": skip, "limit": limit}
        if search:
            params["search"] = search
        result = self._do("GET", f"{self.PREFIX}/", params=params, model=list[Experiment])
        return result or []

    def count(self) -> int:
        return int(self._do("GET", f"{self.PREFIX}/count"))

    def get(self, experiment_id: int) -> Experiment:
        return self._do("GET", f"{self.PREFIX}/{experiment_id}", model=Experiment)

    def create(self, payload: Union[ExperimentCreate, Mapping[str, Any]]) -> Experiment:
        body = payload.model_dump(exclude_none=True) if isinstance(payload, ExperimentCreate) else dict(payload)
        return self._do("POST", f"{self.PREFIX}/", json=body, model=Experiment)

    def update(
        self,
        experiment_id: int,
        payload: Union[ExperimentUpdate, Mapping[str, Any]],
    ) -> Experiment:
        body = payload.model_dump(exclude_none=True) if isinstance(payload, ExperimentUpdate) else dict(payload)
        return self._do("PATCH", f"{self.PREFIX}/{experiment_id}", json=body, model=Experiment)

    def delete(self, experiment_id: int) -> None:
        self._do("DELETE", f"{self.PREFIX}/{experiment_id}")


class _RunsAPI(_BaseAPI):
    """CRUD for ``/api/v1/runs`` plus the nested ``log_*`` endpoints."""

    PREFIX = "/runs"

    def list(
        self,
        *,
        experiment_id: Optional[int] = None,
        status: Optional[str] = None,
        skip: int = 0,
        limit: int = 50,
    ) -> Sequence[Run]:
        params: Dict[str, Any] = {"skip": skip, "limit": limit}
        if experiment_id is not None:
            params["experiment_id"] = experiment_id
        if status is not None:
            params["status"] = status
        result = self._do("GET", f"{self.PREFIX}/", params=params, model=list[Run])
        return result or []

    def count(self, *, experiment_id: Optional[int] = None) -> int:
        params: Dict[str, Any] = {}
        if experiment_id is not None:
            params["experiment_id"] = experiment_id
        return int(self._do("GET", f"{self.PREFIX}/count", params=params))

    def get(self, run_id: int) -> Run:
        return self._do("GET", f"{self.PREFIX}/{run_id}", model=Run)

    def create(self, payload: Union[RunCreate, Mapping[str, Any]]) -> Run:
        body = payload.model_dump(exclude_none=True) if isinstance(payload, RunCreate) else dict(payload)
        return self._do("POST", f"{self.PREFIX}/", json=body, model=Run)

    def update(self, run_id: int, payload: Union[RunUpdate, Mapping[str, Any]]) -> Run:
        body = payload.model_dump(exclude_none=True) if isinstance(payload, RunUpdate) else dict(payload)
        return self._do("PATCH", f"{self.PREFIX}/{run_id}", json=body, model=Run)

    def delete(self, run_id: int) -> None:
        self._do("DELETE", f"{self.PREFIX}/{run_id}")

    # ─── Nested "log X" endpoints ─────────────────────────────────────
    def log_metric(
        self,
        run_id: int,
        key: str,
        value: float,
        *,
        step: Optional[int] = None,
    ) -> Run:
        body = MetricIn(key=key, value=value, step=step).model_dump(exclude_none=True)
        return self._do("POST", f"{self.PREFIX}/{run_id}/metrics", json=body, model=Run)

    def log_parameter(self, run_id: int, key: str, value: str) -> Run:
        body = ParameterIn(key=key, value=value).model_dump()
        return self._do("POST", f"{self.PREFIX}/{run_id}/parameters", json=body, model=Run)

    def finish(
        self,
        run_id: int,
        *,
        status: str = "FINISHED",
        final_metrics: Optional[Mapping[str, float]] = None,
    ) -> Run:
        body = FinishRunIn(status=status, final_metrics=dict(final_metrics) if final_metrics else None)  # type: ignore[arg-type]
        return self._do("POST", f"{self.PREFIX}/{run_id}/finish", json=body.model_dump(exclude_none=True), model=Run)


class _ModelsAPI(_BaseAPI):
    """Read-only view of the MLflow model registry (via the backend proxy)."""

    PREFIX = "/models"

    def list(self) -> Sequence[RegisteredModel]:
        result = self._do("GET", f"{self.PREFIX}/", model=list[RegisteredModel])
        return result or []

    def versions(self, name: str) -> Sequence[ModelVersion]:
        result = self._do("GET", f"{self.PREFIX}/{name}", model=list[ModelVersion])
        return result or []

    def latest(self, name: str, stage: str = "Production") -> Optional[ModelVersion]:
        return self._do(
            "GET",
            f"{self.PREFIX}/{name}/latest",
            params={"stage": stage},
            model=ModelVersion,
        )


class _PredictionsAPI(_BaseAPI):
    """Inference endpoint + the "what can I predict against?" listing."""

    PREFIX = "/predictions"

    def predict(
        self,
        features: Union[Sequence[Any], Mapping[str, Any]],
        *,
        model_name: Optional[str] = None,
        model_uri: Optional[str] = None,
        stage: str = "Production",
    ) -> PredictResponse:
        if not model_name and not model_uri:
            raise ValueError("Provide either `model_name` or `model_uri`.")
        body = PredictRequest(
            model_name=model_name,
            model_uri=model_uri,
            stage=stage,
            features=features,
        ).model_dump(exclude_none=True)
        return self._do("POST", f"{self.PREFIX}/predict", json=body, model=PredictResponse)

    def available(self) -> Sequence[RegisteredModel]:
        result = self._do("GET", f"{self.PREFIX}/models", model=list[RegisteredModel])
        return result or []


class _HealthAPI(_BaseAPI):
    """Backend liveness probe. No auth required."""

    def get(self) -> HealthResponse:
        return self._do("GET", "/health", model=HealthResponse)
