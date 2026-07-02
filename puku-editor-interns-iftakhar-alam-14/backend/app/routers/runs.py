"""
Runs router: HTTP layer for run CRUD + logging endpoints.

This is the most feature-rich router in the system. A "run" is one
execution of an experiment (one model training, one evaluation, ...).

Endpoints in this file:

    GET    /runs/                     list runs (filterable)
    GET    /runs/count                count runs
    POST   /runs/                     create a new run
    GET    /runs/{run_id}             get one run
    PATCH  /runs/{run_id}             partial update
    DELETE /runs/{run_id}             delete

    POST   /runs/{run_id}/metrics     log ONE metric (forwarded to MLflow)
    POST   /runs/{run_id}/parameters  log ONE hyperparameter
    POST   /runs/{run_id}/finish      mark a run as FINISHED + record final metrics

Why a separate "log_metric" endpoint instead of just PATCHing the run?
Because logging one metric at training step 1000 is the natural way ML
code talks to a tracker, and we want to forward it to MLflow automatically.
"""
from typing import List, Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.app.database import get_db
from backend.app.schemas.run import RunCreate, RunResponse, RunUpdate
from backend.app.services import mlflow_service, run_service


# ─── Router setup ──────────────────────────────────────────────────────
router = APIRouter(
    prefix="/runs",
    tags=["runs"],
)


# ─── Tiny request-body schemas for the "log X" endpoints ──────────────
# We keep these inline because they're used only by this router and
# have no need to live in schemas/run.py.
class MetricIn(BaseModel):
    """Body for POST /runs/{run_id}/metrics"""
    key: str = Field(..., min_length=1, max_length=100, description="Metric name, e.g. 'accuracy'")
    value: float = Field(..., description="Metric value, e.g. 0.94")
    step: Optional[int] = Field(
        None,
        ge=0,
        description="Optional training step (for time-series plots in MLflow)",
    )


class ParameterIn(BaseModel):
    """Body for POST /runs/{run_id}/parameters"""
    key: str = Field(..., min_length=1, max_length=100, description="Param name, e.g. 'lr'")
    value: str = Field(..., description="Param value as a string, e.g. '0.001'")


class FinishRunIn(BaseModel):
    """Body for POST /runs/{run_id}/finish"""
    status: str = Field("FINISHED", description="FINISHED or FAILED")
    final_metrics: Optional[dict] = Field(
        None,
        description="Optional dict of final metrics to attach, e.g. {'accuracy': 0.94}",
    )


# ─── Helper ────────────────────────────────────────────────────────────
def _bad_request(exc: ValueError) -> HTTPException:
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


def _resolve_run(db: Session, run_id: int):
    """
    Common lookup used by every endpoint.
    Returns the Run ORM object, or raises 404.
    """
    run = run_service.get_run(db, run_id)
    if run is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Run with id {run_id} not found",
        )
    return run


# ════════════════════════════════════════════════════════════════════════
#  CRUD endpoints
# ════════════════════════════════════════════════════════════════════════

# ─── LIST  GET /runs ────────────────────────────────────────────────────
@router.get(
    "/",
    response_model=List[RunResponse],
    summary="List runs",
    description=(
        "Return a paginated list of runs, newest-first. "
        "Optionally filter by parent experiment and/or status."
    ),
)
def list_runs(
    experiment_id: Optional[int] = Query(None, ge=1, description="Filter by parent experiment"),
    status_filter: Optional[str] = Query(
        None,
        alias="status",                              # query string uses ?status=RUNNING
        description="Filter by status: RUNNING | FINISHED | FAILED",
    ),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    return run_service.list_runs(
        db,
        experiment_id=experiment_id,
        status=status_filter,
        skip=skip,
        limit=limit,
    )


# ─── COUNT  GET /runs/count ────────────────────────────────────────────
# Declared before /{run_id} for the same reason as in experiments.py.
@router.get("/count", response_model=int, summary="Count runs")
def count_runs(
    experiment_id: Optional[int] = Query(None, ge=1),
    db: Session = Depends(get_db),
):
    return run_service.count_runs(db, experiment_id=experiment_id)


# ─── CREATE  POST /runs ───────────────────────────────────────────────
@router.post(
    "/",
    response_model=RunResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new run",
    description=(
        "Create a new run under an experiment. "
        "Returns 400 if the parent experiment doesn't exist."
    ),
)
def create_run(
    payload: RunCreate,
    db: Session = Depends(get_db),
):
    try:
        return run_service.create_run(db, payload)
    except ValueError as exc:
        raise _bad_request(exc)


# ─── GET ONE  GET /runs/{run_id} ──────────────────────────────────────
@router.get(
    "/{run_id}",
    response_model=RunResponse,
    summary="Get one run",
    responses={404: {"description": "Run not found"}},
)
def get_run(run_id: int, db: Session = Depends(get_db)):
    return _resolve_run(db, run_id)


# ─── PARTIAL UPDATE  PATCH /runs/{run_id} ─────────────────────────────
@router.patch(
    "/{run_id}",
    response_model=RunResponse,
    summary="Partially update a run",
    description=(
        "Update one or more fields of a run. "
        "Common use: setting end_time, status, or replacing metrics/parameters."
    ),
    responses={404: {"description": "Run not found"}},
)
def update_run(
    run_id: int,
    payload: RunUpdate,
    db: Session = Depends(get_db),
):
    updated = run_service.update_run(db, run_id, payload)
    if updated is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Run with id {run_id} not found",
        )
    return updated


# ─── DELETE  DELETE /runs/{run_id} ────────────────────────────────────
@router.delete(
    "/{run_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a run",
    responses={404: {"description": "Run not found"}},
)
def delete_run(run_id: int, db: Session = Depends(get_db)):
    deleted = run_service.delete_run(db, run_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Run with id {run_id} not found",
        )
    return None


# ════════════════════════════════════════════════════════════════════════
#  Nested "log X" endpoints
# ════════════════════════════════════════════════════════════════════════

# ─── LOG METRIC  POST /runs/{run_id}/metrics ──────────────────────────
@router.post(
    "/{run_id}/metrics",
    response_model=RunResponse,
    summary="Log a single metric",
    description=(
        "Append one metric (key, value, optional step) to the run. "
        "The metric is also forwarded to MLflow so it shows up in time-series plots."
    ),
    responses={404: {"description": "Run not found"}},
)
def log_metric(
    run_id: int,
    body: MetricIn = Body(...),
    db: Session = Depends(get_db),
):
    run = _resolve_run(db, run_id)

    # 1. Update our PostgreSQL row (system of record)
    updated = run_service.log_metric(db, run_id, body.key, body.value)
    if updated is None:
        # shouldn't happen — we just resolved the run above
        raise HTTPException(status_code=404, detail=f"Run {run_id} disappeared")

    # 2. Forward to MLflow for time-series history (best-effort)
    try:
        with mlflow_service.start_mlflow_run(
            experiment_id=str(run.experiment_id),
            run_name=run.run_name,
        ):
            mlflow_service.log_metrics({body.key: body.value}, step=body.step)
    except Exception:
        # Don't fail the API call if MLflow is offline — we already wrote to PG.
        # (In production you'd want a proper retry queue or a circuit breaker.)
        pass

    return updated


# ─── LOG PARAMETER  POST /runs/{run_id}/parameters ────────────────────
@router.post(
    "/{run_id}/parameters",
    response_model=RunResponse,
    summary="Log a single hyperparameter",
    description="Append one (key, value) hyperparameter to the run.",
    responses={404: {"description": "Run not found"}},
)
def log_parameter(
    run_id: int,
    body: ParameterIn = Body(...),
    db: Session = Depends(get_db),
):
    return run_service.log_parameter(db, run_id, body.key, body.value)


# ─── FINISH  POST /runs/{run_id}/finish ───────────────────────────────
@router.post(
    "/{run_id}/finish",
    response_model=RunResponse,
    summary="Mark a run as finished",
    description=(
        "Convenience endpoint: sets end_time, status (FINISHED or FAILED), "
        "and optionally attaches final metrics in one call."
    ),
    responses={404: {"description": "Run not found"}},
)
def finish_run(
    run_id: int,
    body: FinishRunIn = Body(default_factory=FinishRunIn),
    db: Session = Depends(get_db),
):
    # Validate status value
    if body.status not in {"FINISHED", "FAILED"}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"status must be FINISHED or FAILED, got '{body.status}'",
        )

    updated = run_service.finish_run(
        db, run_id, status=body.status, final_metrics=body.final_metrics
    )
    if updated is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Run with id {run_id} not found",
        )
    return updated
