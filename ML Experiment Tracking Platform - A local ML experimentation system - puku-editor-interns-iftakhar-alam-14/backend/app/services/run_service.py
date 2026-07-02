"""
Run service: business logic for managing runs.

Runs are the "executions" inside an experiment.
Each run can have:
  • metrics    → numbers logged over time (accuracy, loss, ...)
  • parameters → hyperparameters (learning_rate, batch_size, ...)
  • tags       → arbitrary labels
  • artifacts  → files (model.pkl, plot.png, ...) stored in MinIO

The DB stores metrics/parameters/tags as JSON TEXT (see Run model).
This service handles the dict ↔ JSON conversion automatically.
"""
import json
from datetime import datetime
from typing import List, Optional, Dict, Any

from sqlalchemy.orm import Session

from backend.app.models.experiment import Experiment
from backend.app.models.run import Run
from backend.app.schemas.run import RunCreate, RunUpdate


# ─── Helpers for JSON columns ──────────────────────────────────────────
def _dump_json(value: Optional[Dict[str, Any]]) -> Optional[str]:
    """Convert a dict to a JSON string for DB storage. None stays None."""
    if value is None:
        return None
    return json.dumps(value, default=str)  # default=str handles datetimes etc.


def _load_json(value: Optional[str]) -> Optional[Dict[str, Any]]:
    """Convert a JSON string from the DB back into a dict. None stays None."""
    if value is None or value == "":
        return None
    return json.loads(value)


# ─── CRUD ──────────────────────────────────────────────────────────────
def create_run(db: Session, payload: RunCreate) -> Run:
    """
    Create a new run under an experiment.

    Raises:
        ValueError: if the parent experiment doesn't exist.
    """
    # Verify the parent experiment exists
    experiment = db.query(Experiment).filter(Experiment.id == payload.experiment_id).first()
    if experiment is None:
        raise ValueError(f"Experiment with id {payload.experiment_id} does not exist.")

    run = Run(
        experiment_id=payload.experiment_id,
        run_name=payload.run_name,
        status=payload.status or "RUNNING",
        metrics=_dump_json(payload.metrics),
        parameters=_dump_json(payload.parameters),
        tags=_dump_json(payload.tags),
        artifact_uri=payload.artifact_uri,
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    return run


def get_run(db: Session, run_id: int) -> Optional[Run]:
    """Return one run by ID, or None if not found."""
    return db.query(Run).filter(Run.id == run_id).first()


def list_runs(
    db: Session,
    experiment_id: Optional[int] = None,
    status: Optional[str] = None,
    skip: int = 0,
    limit: int = 100,
) -> List[Run]:
    """
    List runs with optional filters.

    Args:
        experiment_id: filter by parent experiment
        status:        filter by run status (RUNNING / FINISHED / FAILED)
        skip, limit:   pagination
    """
    query = db.query(Run)
    if experiment_id is not None:
        query = query.filter(Run.experiment_id == experiment_id)
    if status is not None:
        query = query.filter(Run.status == status)
    return query.order_by(Run.start_time.desc()).offset(skip).limit(limit).all()


def count_runs(db: Session, experiment_id: Optional[int] = None) -> int:
    """Return total number of runs (optionally filtered by experiment)."""
    query = db.query(Run)
    if experiment_id is not None:
        query = query.filter(Run.experiment_id == experiment_id)
    return query.count()


def update_run(db: Session, run_id: int, payload: RunUpdate) -> Optional[Run]:
    """
    Partially update a run. Common use: mark a run as FINISHED
    and set end_time + final metrics.
    """
    run = get_run(db, run_id)
    if run is None:
        return None

    update_data = payload.model_dump(exclude_unset=True)

    # Handle dict fields separately (need JSON encoding)
    for dict_field in ("metrics", "parameters", "tags"):
        if dict_field in update_data:
            setattr(run, dict_field, _dump_json(update_data[dict_field]))

    # Handle the simple scalar fields
    for field in ("run_name", "status", "end_time", "artifact_uri"):
        if field in update_data:
            setattr(run, field, update_data[field])

    db.commit()
    db.refresh(run)
    return run


def finish_run(
    db: Session,
    run_id: int,
    status: str = "FINISHED",
    final_metrics: Optional[Dict[str, Any]] = None,
) -> Optional[Run]:
    """
    Convenience method: mark a run as done and record final metrics.

    Common in MLflow-style workflows:
        run_service.finish_run(db, run_id, status="FINISHED", final_metrics={"accuracy": 0.94})
    """
    payload = RunUpdate(
        status=status,
        end_time=datetime.utcnow(),
        metrics=final_metrics,
    )
    return update_run(db, run_id, payload)


def delete_run(db: Session, run_id: int) -> bool:
    """Delete a run. Returns True if deleted, False if not found."""
    run = get_run(db, run_id)
    if run is None:
        return False
    db.delete(run)
    db.commit()
    return True


# ─── Convenience: add a single metric/param to an existing run ────────
def log_metric(db: Session, run_id: int, metric_name: str, value: float) -> Optional[Run]:
    """
    Append a single metric to a run's existing metrics dict.

    Example:
        run_service.log_metric(db, 42, "accuracy", 0.94)
    """
    run = get_run(db, run_id)
    if run is None:
        return None
    metrics = _load_json(run.metrics) or {}
    metrics[metric_name] = value
    run.metrics = _dump_json(metrics)
    db.commit()
    db.refresh(run)
    return run


def log_parameter(db: Session, run_id: int, param_name: str, value: Any) -> Optional[Run]:
    """
    Append a single parameter to a run's existing parameters dict.
    """
    run = get_run(db, run_id)
    if run is None:
        return None
    params = _load_json(run.parameters) or {}
    params[param_name] = value
    run.parameters = _dump_json(params)
    db.commit()
    db.refresh(run)
    return run


# ─── Helper to convert a Run ORM object to a dict with parsed JSON ────
def run_to_dict(run: Run) -> Dict[str, Any]:
    """
    Convert a Run ORM object to a dict with metrics/parameters/tags
    already parsed from JSON. Useful for API responses.
    """
    return {
        "id": run.id,
        "experiment_id": run.experiment_id,
        "run_name": run.run_name,
        "status": run.status,
        "metrics": _load_json(run.metrics),
        "parameters": _load_json(run.parameters),
        "tags": _load_json(run.tags),
        "artifact_uri": run.artifact_uri,
        "start_time": run.start_time,
        "end_time": run.end_time,
    }
