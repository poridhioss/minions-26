"""
Predictions router: HTTP layer for model inference.

This is the "serving" half of the platform: a client posts a feature
vector, we look up the right model in MLflow's registry, load it
(MLflow pulls the binary from MinIO), and return the prediction.

Two ways to identify the model:

    1. By registered name + stage:   {"model_name": "rf-v1", "stage": "Production"}
    2. By direct MLflow URI:         {"model_uri":  "runs:/abc/model"}

Exactly one of those must be provided.
"""
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Body, HTTPException, status
from pydantic import BaseModel, Field

from backend.app.services import prediction_service


# ─── Router setup ──────────────────────────────────────────────────────
router = APIRouter(
    prefix="/predictions",
    tags=["predictions"],
)


# ─── Request body for /predict ─────────────────────────────────────────
class PredictIn(BaseModel):
    """
    Body for POST /predictions/predict.

    Example — by registered model name:
        {
          "model_name": "rf-v1",
          "stage":      "Production",
          "features":   [5.1, 3.5, 1.4, 0.2]
        }

    Example — by direct MLflow URI:
        {
          "model_uri": "runs:/abc123/model",
          "features":  {"sepal_length": 5.1, "sepal_width": 3.5, ...}
        }
    """
    # The two ways to identify the model (at least one required)
    model_name: Optional[str] = Field(
        None, description="Registered model name in MLflow. Alternative to model_uri."
    )
    model_uri: Optional[str] = Field(
        None, description="Direct MLflow URI like 'runs:/abc/model'. Overrides model_name."
    )
    stage: str = Field(
        "Production",
        description="Which stage to load from the registry (Production, Staging, ...).",
    )

    # The actual input data
    features: List[Any] = Field(
        ...,
        description=(
            "A list of feature values for a single sample "
            "(e.g. [5.1, 3.5, 1.4, 0.2]), or a list of such lists for batch prediction."
        ),
    )


# ════════════════════════════════════════════════════════════════════════
#  Endpoints
# ════════════════════════════════════════════════════════════════════════

# ─── PREDICT  POST /predictions/predict ────────────────────────────────
@router.post(
    "/predict",
    summary="Run inference against a model",
    description=(
        "Load a model from MLflow (by name+stage or by URI) and return "
        "its prediction for the given features."
    ),
    responses={
        200: {"description": "Prediction computed"},
        400: {"description": "Bad request (missing model identifier, bad features)"},
        404: {"description": "Model not found in registry"},
    },
)
def predict(body: PredictIn = Body(...)):
    # Input validation — at least one model identifier must be present
    if not body.model_name and not body.model_uri:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Provide either 'model_name' or 'model_uri' in the request body.",
        )

    try:
        result = prediction_service.predict(
            features=body.features,
            model_name=body.model_name,
            model_uri=body.model_uri,
            stage=body.stage,
        )
    except ValueError as exc:
        # Service raises ValueError for "model not found" or "neither name nor uri"
        msg = str(exc)
        if "not found" in msg.lower() or "no model" in msg.lower():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=msg)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=msg)

    return result


# ─── LIST AVAILABLE MODELS  GET /predictions/models ──────────────────
@router.get(
    "/models",
    response_model=List[Dict[str, Any]],
    summary="List models available for prediction",
    description=(
        "Return a list of all models currently registered in MLflow's model "
        "registry, with their latest versions and stages. Use this to discover "
        "which `model_name` values are valid for /predict."
    ),
)
def list_models():
    """
    Thin wrapper around prediction_service.list_available_models().
    Lives in the predictions router because clients fetching this list
    are typically about to call /predict.
    """
    return prediction_service.list_available_models()
