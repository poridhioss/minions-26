"""
MLflow service: thin wrapper around the MLflow Tracking API.

This service bridges our FastAPI backend with a running MLflow server.
It uses MLflow's REST API (via the `mlflow` Python client) so the
backend doesn't have to be a Python subprocess — it's a clean HTTP client.

Public functions:
  • get_or_create_mlflow_experiment(name) → mlflow experiment_id
  • start_mlflow_run(experiment_id, run_name) → mlflow active run
  • log_metric / log_param / log_model     → push data into MLflow
  • list_registered_models / load_model    → for prediction
"""
import logging
from typing import Any, Dict, List, Optional

import mlflow
import mlflow.sklearn
from mlflow import MlflowClient

from backend.app.core.config import settings


logger = logging.getLogger(__name__)


# ─── Configure the MLflow client once at import time ──────────────────
# Setting the tracking URI tells the mlflow library where to send API calls.
mlflow.set_tracking_uri(settings.MLFLOW_TRACKING_URI)
_client = MlflowClient(tracking_uri=settings.MLFLOW_TRACKING_URI)


# ─── Experiments ───────────────────────────────────────────────────────
def get_or_create_mlflow_experiment(name: str) -> str:
    """
    Look up an MLflow experiment by name; create it if it doesn't exist.
    Returns the MLflow experiment_id (a string).
    """
    existing = mlflow.get_experiment_by_name(name)
    if existing is not None:
        return existing.experiment_id

    experiment_id = mlflow.create_experiment(
        name=name,
        artifact_location=settings.MLFLOW_ARTIFACT_ROOT,
    )
    logger.info("Created MLflow experiment '%s' (id=%s)", name, experiment_id)
    return experiment_id


# ─── Runs ──────────────────────────────────────────────────────────────
def start_mlflow_run(experiment_id: str, run_name: Optional[str] = None):
    """
    Start an MLflow run under the given experiment_id.
    Returns an `ActiveRun` context manager — use it with `with`.

    Example:
        with start_mlflow_run("1", "rf-baseline") as run:
            mlflow.log_param("lr", 0.01)
            mlflow.log_metric("acc", 0.94)
    """
    return mlflow.start_run(experiment_id=experiment_id, run_name=run_name)


def log_params(params: Dict[str, Any]) -> None:
    """Log multiple hyperparameters to the active MLflow run."""
    if not params:
        return
    mlflow.log_params(params)


def log_metrics(metrics: Dict[str, float], step: Optional[int] = None) -> None:
    """Log multiple metrics to the active MLflow run."""
    if not metrics:
        return
    mlflow.log_metrics(metrics, step=step)


def log_sklearn_model(model: Any, artifact_path: str = "model") -> str:
    """
    Log a trained scikit-learn model to the active MLflow run.
    Returns the model URI (e.g. 'runs:/abc123/model').
    """
    return mlflow.sklearn.log_model(model, artifact_path=artifact_path)


def end_mlflow_run(status: str = "FINISHED") -> None:
    """End the current active MLflow run with a given status."""
    mlflow.end_run(status=status)


# ─── Model registry / loading (for prediction) ────────────────────────
def list_registered_models() -> List[Dict[str, Any]]:
    """Return a list of all models registered in MLflow's model registry."""
    try:
        models = _client.search_registered_models()
        return [
            {
                "name": m.name,
                "latest_versions": [
                    {
                        "version": v.version,
                        "run_id": v.run_id,
                        "status": v.status,
                        "current_stage": v.current_stage,
                    }
                    for v in (m.latest_versions or [])
                ],
            }
            for m in models
        ]
    except Exception as exc:
        logger.warning("Failed to list registered models: %s", exc)
        return []


def get_latest_model_version(model_name: str, stage: str = "Production") -> Optional[Dict[str, Any]]:
    """
    Look up the latest version of a registered model in a given stage.
    Returns None if the model or stage doesn't exist.
    """
    try:
        versions = _client.get_latest_versions(model_name, stages=[stage])
        if not versions:
            return None
        v = versions[0]
        return {
            "name": v.name,
            "version": v.version,
            "run_id": v.run_id,
            "current_stage": v.current_stage,
            "source": v.source,
        }
    except Exception as exc:
        logger.warning("Failed to get model %s @ %s: %s", model_name, stage, exc)
        return None


def load_model_by_uri(model_uri: str) -> Any:
    """
    Load a serialized model from MLflow by its URI.
    Example URI: 'models:/random-forest/1' or 'runs:/abc123/model'
    """
    return mlflow.sklearn.load_model(model_uri)
