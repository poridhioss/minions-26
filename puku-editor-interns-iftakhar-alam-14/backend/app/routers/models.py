"""
Models router: HTTP layer for browsing the MLflow model registry.

This is a read-only view onto MLflow's model registry. It exists so the
frontend can show a "Models" page without needing to talk to MLflow
directly.

Endpoints:

    GET /models/                  list every registered model + its versions
    GET /models/{name}            list versions of a single registered model
    GET /models/{name}/latest     latest version in a given stage (default: Production)
"""
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query, status

from backend.app.services import mlflow_service


# ─── Router setup ──────────────────────────────────────────────────────
router = APIRouter(
    prefix="/models",
    tags=["models"],
)


# ════════════════════════════════════════════════════════════════════════
#  Endpoints
# ════════════════════════════════════════════════════════════════════════

# ─── LIST ALL  GET /models ─────────────────────────────────────────────
@router.get(
    "/",
    response_model=List[Dict[str, Any]],
    summary="List all registered models",
    description=(
        "Return every model currently registered in MLflow, along with "
        "its latest versions. Returns an empty list if MLflow is unreachable."
    ),
)
def list_models():
    return mlflow_service.list_registered_models()


# ─── LIST VERSIONS  GET /models/{name} ────────────────────────────────
@router.get(
    "/{name}",
    response_model=List[Dict[str, Any]],
    summary="List versions of one model",
    description="Return the latest versions of the model with the given registered name.",
    responses={404: {"description": "No model with that name in the registry"}},
)
def get_model_versions(name: str):
    """
    Filter the global list down to just the requested name.
    (We could also call _client.search_model_versions directly, but
     going through the service keeps MLflow access in one place.)
    """
    all_models = mlflow_service.list_registered_models()
    matches = [m for m in all_models if m.get("name") == name]
    if not matches:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No registered model named '{name}'.",
        )
    return matches[0].get("latest_versions", [])


# ─── LATEST VERSION  GET /models/{name}/latest ────────────────────────
@router.get(
    "/{name}/latest",
    response_model=Optional[Dict[str, Any]],
    summary="Get the latest version of a model in a given stage",
    description=(
        "Returns the latest version of the named model that is currently "
        "in the given stage (Production, Staging, Archived, None). "
        "Returns 404 if no version is in that stage."
    ),
    responses={404: {"description": "No version of this model in that stage"}},
)
def get_latest_version(
    name: str,
    stage: str = Query(
        "Production",
        description="Which stage to look in (Production, Staging, Archived, None).",
    ),
):
    info = mlflow_service.get_latest_model_version(name, stage=stage)
    if info is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                f"No version of model '{name}' found in stage '{stage}'. "
                f"Register the model and promote it to that stage first."
            ),
        )
    return info
