"""
Pydantic v2 type definitions mirroring the FastAPI backend's response schemas.

Why hand-written rather than auto-generated from the OpenAPI spec?
  • The API surface is small (~15 endpoints), so drift is easy to spot in
    code review.
  • The SDK has to be importable WITHOUT the backend being installed/running
    (we don't want to fetch /openapi.json at import time). Hand-written
    types keep the SDK fully decoupled from a live server.
  • If the API grows, swap this for a code generator.

These types are deliberately permissive (``Dict[str, Any]`` for nested
metrics/parameters/tags) because the backend stores those fields as JSON
text and the contract is "whatever the user logged".
"""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Mapping, Optional, Sequence, Union

from pydantic import BaseModel, ConfigDict, Field


# ════════════════════════════════════════════════════════════════════════
#  Enums
# ════════════════════════════════════════════════════════════════════════

class RunStatus(str, Enum):
    """Lifecycle of a training run. Mirrors ``backend/app/models/run.py``."""
    RUNNING = "RUNNING"
    FINISHED = "FINISHED"
    FAILED = "FAILED"


class ModelStage(str, Enum):
    """MLflow model-registry stage."""
    PRODUCTION = "Production"
    STAGING = "Staging"
    ARCHIVED = "Archived"
    NONE = "None"


class Status(str, Enum):
    """Generic ``status`` field on /health."""
    OK = "ok"
    DEGRADED = "degraded"


# ════════════════════════════════════════════════════════════════════════
#  Experiments
# ════════════════════════════════════════════════════════════════════════

class ExperimentBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    tags: Optional[str] = Field(
        None,
        description="Free-form tags (comma-separated or JSON string).",
    )


class ExperimentCreate(ExperimentBase):
    """Body for ``POST /api/v1/experiments/``."""


class ExperimentUpdate(BaseModel):
    """Body for ``PATCH /api/v1/experiments/{id}``. All fields optional."""
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None
    tags: Optional[str] = None


class Experiment(ExperimentBase):
    """Response for ``GET/POST/PATCH /api/v1/experiments[/{id}]``."""
    id: int
    created_at: datetime
    updated_at: Optional[datetime] = None

    # Allow population from a plain dict (which is what ``httpx.json()`` returns).
    model_config = ConfigDict(from_attributes=True)


# ════════════════════════════════════════════════════════════════════════
#  Runs
# ════════════════════════════════════════════════════════════════════════

class RunBase(BaseModel):
    run_name: Optional[str] = Field(None, max_length=255)
    status: Optional[RunStatus] = None
    artifact_uri: Optional[str] = Field(None, max_length=500)


class RunCreate(RunBase):
    """Body for ``POST /api/v1/runs/``."""
    experiment_id: int
    metrics: Optional[Dict[str, Any]] = None
    parameters: Optional[Dict[str, Any]] = None
    tags: Optional[Dict[str, Any]] = None


class RunUpdate(BaseModel):
    """Body for ``PATCH /api/v1/runs/{id}``. All fields optional."""
    run_name: Optional[str] = None
    status: Optional[RunStatus] = None
    end_time: Optional[datetime] = None
    metrics: Optional[Dict[str, Any]] = None
    parameters: Optional[Dict[str, Any]] = None
    tags: Optional[Dict[str, Any]] = None
    artifact_uri: Optional[str] = None


class Run(RunBase):
    """Response for any ``/api/v1/runs`` endpoint."""
    id: int
    experiment_id: int
    metrics: Optional[Dict[str, Any]] = None
    parameters: Optional[Dict[str, Any]] = None
    tags: Optional[Dict[str, Any]] = None
    start_time: datetime
    end_time: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


# ─── Tiny "log X" payloads (mirror the inline schemas in routers/runs.py) ─

class MetricIn(BaseModel):
    """Body for ``POST /api/v1/runs/{id}/metrics``."""
    key: str = Field(..., min_length=1, max_length=100)
    value: float
    step: Optional[int] = Field(None, ge=0)


class ParameterIn(BaseModel):
    """Body for ``POST /api/v1/runs/{id}/parameters``."""
    key: str = Field(..., min_length=1, max_length=100)
    value: str


class FinishRunIn(BaseModel):
    """Body for ``POST /api/v1/runs/{id}/finish``."""
    status: RunStatus = RunStatus.FINISHED
    final_metrics: Optional[Dict[str, float]] = None


# ════════════════════════════════════════════════════════════════════════
#  Predictions
# ════════════════════════════════════════════════════════════════════════

# Note: the backend's ``PredictIn`` schema has NO ``version`` field — only
# ``model_name`` + ``stage`` OR ``model_uri``. The TS client types
# (``frontend/src/api/types.ts``) declare a ``version`` field for the
# frontend's use, but the backend ignores it. The SDK mirrors the
# BACKEND contract, not the frontend's type, because the SDK is a thin
# HTTP client — extra fields would be silently accepted by httpx but
# silently rejected by the server.

class PredictRequest(BaseModel):
    """Body for ``POST /api/v1/predictions/predict``."""
    model_name: Optional[str] = None
    model_uri: Optional[str] = None
    stage: str = "Production"
    features: Union[Sequence[Any], Mapping[str, Any]] = Field(...)


class PredictResponse(BaseModel):
    """Response from ``POST /api/v1/predictions/predict``."""
    predictions: Any
    model_name: Optional[str] = None
    model_version: Optional[str] = None
    model_stage: Optional[str] = None

    model_config = ConfigDict(extra="allow")  # backend may add fields


# ════════════════════════════════════════════════════════════════════════
#  Model registry
# ════════════════════════════════════════════════════════════════════════

class ModelVersion(BaseModel):
    """A single version of a registered model. Mirrors MLflow's shape."""
    name: str
    version: str
    stage: ModelStage
    run_id: Optional[str] = None
    description: Optional[str] = None
    creation_timestamp: Optional[str] = None
    last_updated_timestamp: Optional[str] = None
    current_stage: Optional[str] = None
    created_at: Optional[str] = None
    last_updated: Optional[str] = None

    model_config = ConfigDict(extra="allow")


class RegisteredModel(BaseModel):
    """Response for ``GET /api/v1/models/``."""
    name: str
    description: Optional[str] = None
    creation_timestamp: Optional[str] = None
    last_updated_timestamp: Optional[str] = None
    last_updated: Optional[str] = None
    latest_versions: List[ModelVersion] = Field(default_factory=list)

    model_config = ConfigDict(extra="allow")


# ════════════════════════════════════════════════════════════════════════
#  Health
# ════════════════════════════════════════════════════════════════════════

class HealthResponse(BaseModel):
    """Response for ``GET /health``."""
    status: str
    app: str
    version: str

    # The backend attaches ``debug`` (bool) and other env-derived fields.
    # We capture them under ``extra`` so they're not lost but not typed.
    model_config = ConfigDict(extra="allow")
