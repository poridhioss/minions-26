"""
Experiments router: HTTP layer for experiment CRUD.

This module is the "front door" for the /experiments endpoints.
It does almost no work itself — its job is to:

    1. Receive the HTTP request
    2. Validate the input via the Pydantic schema
    3. Open a database session (via dependency injection)
    4. Hand the work to the service layer
    5. Translate the service's result into a JSON response
    6. Translate the service's errors into proper HTTP error codes

The service layer is the only place that talks to the database.
"""
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from backend.app.database import get_db
from backend.app.schemas.experiment import (
    ExperimentCreate,
    ExperimentResponse,
    ExperimentUpdate,
)
from backend.app.services import experiment_service


# ─── Router setup ──────────────────────────────────────────────────────
# `APIRouter` is a "mini FastAPI app" — we attach routes to it,
# then `main.py` includes it in the real app via app.include_router(...).
router = APIRouter(
    prefix="/experiments",            # every route below is mounted under /experiments
    tags=["experiments"],             # groups routes in Swagger UI
)


# ─── Helper: translate service-layer ValueError into HTTP 400 ──────────
def _bad_request_from_value_error(exc: ValueError) -> HTTPException:
    """
    The service layer raises plain `ValueError` for business-rule
    violations (e.g. duplicate name, experiment has runs).
    This helper converts those into proper HTTP 400 responses.
    """
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


# ════════════════════════════════════════════════════════════════════════
#  Endpoints
# ════════════════════════════════════════════════════════════════════════

# ─── LIST  GET /experiments ─────────────────────────────────────────────
# Note: paths are RELATIVE to the router's `prefix="/experiments"`.
# So "/" here means "this router's root" → final URL: /experiments/
@router.get(
    "/",
    response_model=List[ExperimentResponse],
    summary="List experiments",
    description=(
        "Return a paginated list of experiments, ordered newest-first. "
        "Optionally filter by a case-insensitive substring of the name."
    ),
)
def list_experiments(
    skip: int = Query(0, ge=0, description="Number of rows to skip (pagination)"),
    limit: int = Query(50, ge=1, le=200, description="Max rows to return (1-200)"),
    search: Optional[str] = Query(
        None,
        max_length=255,
        description="Case-insensitive substring to match against experiment name",
    ),
    db: Session = Depends(get_db),
):
    return experiment_service.list_experiments(db, skip=skip, limit=limit, search=search)


# ─── COUNT  GET /experiments/count ──────────────────────────────────────
# NOTE: declare this BEFORE the /{experiment_id} route, otherwise
# FastAPI would try to match "count" as an integer experiment_id.
@router.get(
    "/count",
    response_model=int,
    summary="Count experiments",
    description="Return the total number of experiments in the system.",
)
def count_experiments(db: Session = Depends(get_db)):
    return experiment_service.count_experiments(db)


# ─── GET ONE  GET /experiments/{experiment_id} ─────────────────────────
@router.get(
    "/{experiment_id}",
    response_model=ExperimentResponse,
    summary="Get one experiment",
    description="Return a single experiment by its numeric ID. 404 if not found.",
    responses={404: {"description": "Experiment not found"}},
)
def get_experiment(
    experiment_id: int,
    db: Session = Depends(get_db),
):
    exp = experiment_service.get_experiment(db, experiment_id)
    if exp is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Experiment with id {experiment_id} not found",
        )
    return exp


# ─── CREATE  POST /experiments ─────────────────────────────────────────
@router.post(
    "/",
    response_model=ExperimentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new experiment",
    description=(
        "Create a new experiment. The name must be unique. "
        "Returns 400 if the name is already taken."
    ),
    responses={
        201: {"description": "Experiment created"},
        400: {"description": "Experiment name already exists"},
    },
)
def create_experiment(
    payload: ExperimentCreate,
    db: Session = Depends(get_db),
):
    try:
        return experiment_service.create_experiment(db, payload)
    except ValueError as exc:
        raise _bad_request_from_value_error(exc)


# ─── PARTIAL UPDATE  PATCH /experiments/{experiment_id} ───────────────
@router.patch(
    "/{experiment_id}",
    response_model=ExperimentResponse,
    summary="Partially update an experiment",
    description=(
        "Update one or more fields of an experiment. "
        "Only the fields you send in the body are changed."
    ),
    responses={404: {"description": "Experiment not found"}},
)
def update_experiment(
    experiment_id: int,
    payload: ExperimentUpdate,
    db: Session = Depends(get_db),
):
    try:
        exp = experiment_service.update_experiment(db, experiment_id, payload)
    except ValueError as exc:
        # raised on unique-name conflicts
        raise _bad_request_from_value_error(exc)

    if exp is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Experiment with id {experiment_id} not found",
        )
    return exp


# ─── DELETE  DELETE /experiments/{experiment_id} ──────────────────────
@router.delete(
    "/{experiment_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete an experiment",
    description=(
        "Delete an experiment. Returns 400 if it still has runs "
        "(you must delete the runs first)."
    ),
    responses={
        204: {"description": "Experiment deleted"},
        400: {"description": "Experiment has runs; delete them first"},
        404: {"description": "Experiment not found"},
    },
)
def delete_experiment(
    experiment_id: int,
    db: Session = Depends(get_db),
):
    try:
        deleted = experiment_service.delete_experiment(db, experiment_id)
    except ValueError as exc:
        raise _bad_request_from_value_error(exc)

    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Experiment with id {experiment_id} not found",
        )
    # 204 No Content has no body, so return None
    return None
