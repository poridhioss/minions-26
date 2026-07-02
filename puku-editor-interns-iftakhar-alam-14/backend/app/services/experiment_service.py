"""
Experiment service: business logic for managing experiments.

CRUD operations + business rules:
  • Names must be unique (DB enforces it; we translate the error nicely)
  • Cannot delete an experiment that still has runs
"""
import json
from typing import List, Optional

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.app.models.experiment import Experiment
from backend.app.schemas.experiment import ExperimentCreate, ExperimentUpdate


def create_experiment(db: Session, payload: ExperimentCreate) -> Experiment:
    """
    Create a new experiment.

    Raises:
        ValueError: if an experiment with the same name already exists.
    """
    experiment = Experiment(
        name=payload.name,
        description=payload.description,
        tags=payload.tags,
    )
    db.add(experiment)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise ValueError(f"Experiment with name '{payload.name}' already exists.")
    db.refresh(experiment)  # reload to get DB-generated fields (id, created_at)
    return experiment


def get_experiment(db: Session, experiment_id: int) -> Optional[Experiment]:
    """Return one experiment by ID, or None if not found."""
    return db.query(Experiment).filter(Experiment.id == experiment_id).first()


def get_experiment_by_name(db: Session, name: str) -> Optional[Experiment]:
    """Return one experiment by name, or None if not found."""
    return db.query(Experiment).filter(Experiment.name == name).first()


def list_experiments(
    db: Session,
    skip: int = 0,
    limit: int = 100,
    search: Optional[str] = None,
) -> List[Experiment]:
    """
    List experiments with pagination + optional name search.

    Args:
        skip:  number of rows to skip (for pagination)
        limit: max rows to return
        search: optional substring to match against experiment name (case-insensitive)
    """
    query = db.query(Experiment)
    if search:
        query = query.filter(Experiment.name.ilike(f"%{search}%"))
    return query.order_by(Experiment.created_at.desc()).offset(skip).limit(limit).all()


def count_experiments(db: Session) -> int:
    """Return total number of experiments (for pagination metadata)."""
    return db.query(Experiment).count()


def update_experiment(
    db: Session, experiment_id: int, payload: ExperimentUpdate
) -> Optional[Experiment]:
    """
    Partially update an experiment. Only fields that are explicitly set
    on `payload` are updated (Pydantic's `model_dump(exclude_unset=True)`).

    Returns the updated experiment, or None if not found.
    """
    experiment = get_experiment(db, experiment_id)
    if experiment is None:
        return None

    # exclude_unset=True means: only update fields the caller actually sent
    update_data = payload.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(experiment, field, value)

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise ValueError(f"Experiment with name '{payload.name}' already exists.")
    db.refresh(experiment)
    return experiment


def delete_experiment(db: Session, experiment_id: int) -> bool:
    """
    Delete an experiment.

    Returns:
        True if deleted, False if not found.

    Raises:
        ValueError: if the experiment has runs (must delete them first).
    """
    experiment = get_experiment(db, experiment_id)
    if experiment is None:
        return False

    # Business rule: don't allow deleting experiments with history
    if experiment.runs:
        raise ValueError(
            f"Cannot delete experiment '{experiment.name}': "
            f"it has {len(experiment.runs)} run(s). Delete the runs first."
        )

    db.delete(experiment)
    db.commit()
    return True
