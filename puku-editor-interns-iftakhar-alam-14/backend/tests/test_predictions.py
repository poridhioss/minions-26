"""
test_predictions.py: exercise the /api/v1/predictions router.

We don't have a real MLflow server in the test environment, so we patch
`prediction_service.predict` and `prediction_service.list_available_models`
to return canned data. That lets us verify the router's validation +
error-translation logic without needing the full stack.
"""
from unittest.mock import patch

from fastapi.testclient import TestClient


# ─── /predict ──────────────────────────────────────────────────────────
def test_predict_requires_model_identifier(client: TestClient, auth_headers):
    r = client.post(
        "/api/v1/predictions/predict",
        headers=auth_headers,
        json={"features": [1, 2, 3, 4]},
    )
    assert r.status_code == 400
    assert "model_name" in r.json()["detail"] or "model_uri" in r.json()["detail"]


def test_predict_success(client: TestClient, auth_headers):
    with patch("backend.app.routers.predictions.prediction_service.predict") as p:
        p.return_value = {
            "prediction": 2,
            "model_uri": "models:/iris/1",
            "model_name": "iris",
        }
        r = client.post(
            "/api/v1/predictions/predict",
            headers=auth_headers,
            json={"model_name": "iris", "features": [5.1, 3.5, 1.4, 0.2]},
        )
    assert r.status_code == 200
    body = r.json()
    assert body["prediction"] == 2
    p.assert_called_once()


def test_predict_model_not_found_404(client: TestClient, auth_headers):
    """A ValueError containing 'not found' / 'no model' should be translated to 404."""
    from backend.app.routers.predictions import prediction_service
    with patch.object(prediction_service, "predict", side_effect=ValueError("No model named 'x' found in stage 'Production'.")):
        r = client.post(
            "/api/v1/predictions/predict",
            headers=auth_headers,
            json={"model_name": "x", "features": [1, 2, 3, 4]},
        )
    assert r.status_code == 404
    assert "not found" in r.json()["detail"] or "No model" in r.json()["detail"]


def test_predict_generic_value_error_400(client: TestClient, auth_headers):
    """A ValueError that isn't 'not found' should be 400."""
    from backend.app.routers.predictions import prediction_service
    with patch.object(prediction_service, "predict", side_effect=ValueError("bad features shape")):
        r = client.post(
            "/api/v1/predictions/predict",
            headers=auth_headers,
            json={"model_name": "x", "features": [1, 2, 3, 4]},
        )
    assert r.status_code == 400


# ─── /predictions/models ──────────────────────────────────────────────
def test_list_available_models(client: TestClient, auth_headers):
    with patch("backend.app.routers.predictions.prediction_service.list_available_models") as p:
        p.return_value = [{"name": "iris", "latest_versions": []}]
        r = client.get("/api/v1/predictions/models", headers=auth_headers)
    assert r.status_code == 200
    assert r.json()[0]["name"] == "iris"
