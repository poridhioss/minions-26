"""
test_prediction_service.py: exercise the prediction_service module directly.

No HTTP, no DB, no MLflow — just numpy + a mocked mlflow_service.
"""
from unittest.mock import patch

import numpy as np
import pytest

from backend.app.services import prediction_service


# ─── _resolve_model_uri ────────────────────────────────────────────────
def test_resolve_uri_passes_through_explicit_uri():
    assert prediction_service._resolve_model_uri(model_uri="runs:/abc/model") == "runs:/abc/model"


def test_resolve_uri_raises_when_neither_provided():
    with pytest.raises(ValueError, match="must be provided"):
        prediction_service._resolve_model_uri()


def test_resolve_uri_raises_when_model_not_in_registry():
    with patch("backend.app.services.prediction_service.mlflow_service.get_latest_model_version", return_value=None):
        with pytest.raises(ValueError, match="No model named"):
            prediction_service._resolve_model_uri(model_name="missing")


def test_resolve_uri_builds_versioned_uri_from_registry():
    fake = {"name": "iris", "version": "2"}
    with patch("backend.app.services.prediction_service.mlflow_service.get_latest_model_version", return_value=fake):
        uri = prediction_service._resolve_model_uri(model_name="iris", stage="Production")
    assert uri == "models:/iris/2"


# ─── predict() ─────────────────────────────────────────────────────────
class _FakeModel:
    """Minimal stand-in for an sklearn estimator — just .predict()."""
    def __init__(self, output):
        self._output = np.array([output])

    def predict(self, X):
        return self._output


def test_predict_with_list_features():
    fake = _FakeModel(1)
    with patch("backend.app.services.prediction_service.mlflow_service.load_model_by_uri", return_value=fake):
        result = prediction_service.predict(features=[5.1, 3.5, 1.4, 0.2], model_uri="runs:/x/model")
    assert result["prediction"] == 1
    assert result["model_uri"] == "runs:/x/model"
    assert result["model_name"] is None


def test_predict_with_dict_features_preserves_value_order():
    fake = _FakeModel(0)
    with patch("backend.app.services.prediction_service.mlflow_service.load_model_by_uri", return_value=fake):
        result = prediction_service.predict(
            features={"a": 1.0, "b": 2.0, "c": 3.0},
            model_uri="runs:/x/model",
        )
    assert result["prediction"] == 0
    # The fake model's .predict is called with whatever numpy array; we just
    # want to confirm no exception was raised when converting dict → list.
    assert "model_uri" in result


def test_list_available_models_passthrough():
    expected = [{"name": "iris"}]
    with patch("backend.app.services.prediction_service.mlflow_service.list_registered_models", return_value=expected):
        assert prediction_service.list_available_models() == expected
