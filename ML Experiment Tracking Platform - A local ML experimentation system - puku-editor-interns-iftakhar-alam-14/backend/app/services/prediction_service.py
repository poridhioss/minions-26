"""
Prediction service: load a trained model and run inference.

Two ways to specify a model:
  1. By registered model name + stage:
       predict(model_name="rf-v1", stage="Production", features=[...])
  2. By direct MLflow URI:
       predict(model_uri="runs:/abc123/model", features=[...])

In both cases we:
  1. Resolve the model URI (registry lookup or use as-is)
  2. Download/load the model from MinIO via MLflow
  3. Call model.predict(features)
  4. Return the result as a plain Python value
"""
import logging
from typing import Any, List, Dict, Optional, Union

import numpy as np

from backend.app.services import mlflow_service


logger = logging.getLogger(__name__)


def _resolve_model_uri(
    model_name: Optional[str] = None,
    model_uri: Optional[str] = None,
    stage: str = "Production",
) -> str:
    """
    Return a valid MLflow model URI.

    Raises:
        ValueError: if neither model_name nor model_uri is provided,
                    or if the named model is not found in the registry.
    """
    if model_uri:
        return model_uri

    if not model_name:
        raise ValueError("Either 'model_name' or 'model_uri' must be provided.")

    info = mlflow_service.get_latest_model_version(model_name, stage=stage)
    if info is None:
        raise ValueError(
            f"No model named '{model_name}' found in stage '{stage}'. "
            f"Register the model and promote it to '{stage}' first."
        )
    return f"models:/{model_name}/{info['version']}"


def predict(
    features: Union[List[Any], Dict[str, Any]],
    model_name: Optional[str] = None,
    model_uri: Optional[str] = None,
    stage: str = "Production",
) -> Dict[str, Any]:
    """
    Run inference with a registered model or a direct model URI.

    Args:
        features:   a list of feature values, or a dict {feature_name: value}
        model_name: registered model name (alternative to model_uri)
        model_uri:  direct MLflow URI like 'runs:/abc/model' (overrides model_name)
        stage:      which stage to load from the registry (default: Production)

    Returns:
        {
            "prediction":  <the model's output>,
            "model_uri":   <the URI that was used>,
            "model_name":  <resolved name, if any>,
            "model_version": <version, if loaded from registry>
        }
    """
    # 1. Resolve the URI to use
    resolved_uri = _resolve_model_uri(model_name, model_uri, stage)

    # 2. Load the model from MLflow (downloads from MinIO under the hood)
    logger.info("Loading model from %s", resolved_uri)
    model = mlflow_service.load_model_by_uri(resolved_uri)

    # 3. Convert features to a 2D numpy array (sklearn expects [samples, features])
    if isinstance(features, dict):
        # dict → list in the dict's value order
        feature_values = [features[k] for k in features.keys()]
        X = np.array([feature_values])
    else:
        X = np.array([features])

    # 4. Run inference
    raw_prediction = model.predict(X)
    prediction = raw_prediction[0].item() if hasattr(raw_prediction[0], "item") else raw_prediction[0]

    return {
        "prediction": prediction,
        "model_uri": resolved_uri,
        "model_name": model_name,
    }


def list_available_models() -> List[Dict[str, Any]]:
    """
    Convenience wrapper for the router — returns all models in the registry.
    """
    return mlflow_service.list_registered_models()
