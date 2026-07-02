"""
test_models.py: exercise the /api/v1/models router.

Like test_predictions.py, we patch `mlflow_service.*` to avoid needing
a live MLflow tracking server.
"""
from unittest.mock import patch

from fastapi.testclient import TestClient


# ─── /models/ ──────────────────────────────────────────────────────────
def test_list_models_empty(client: TestClient, auth_headers):
    with patch("backend.app.routers.models.mlflow_service.list_registered_models", return_value=[]):
        r = client.get("/api/v1/models/", headers=auth_headers)
    assert r.status_code == 200
    assert r.json() == []


def test_list_models_with_data(client: TestClient, auth_headers):
    fake = [
        {
            "name": "iris",
            "latest_versions": [
                {"version": "1", "run_id": "abc", "status": "READY", "current_stage": "Production"}
            ],
        }
    ]
    with patch("backend.app.routers.models.mlflow_service.list_registered_models", return_value=fake):
        r = client.get("/api/v1/models/", headers=auth_headers)
    assert r.status_code == 200
    body = r.json()
    assert body[0]["name"] == "iris"
    assert body[0]["latest_versions"][0]["current_stage"] == "Production"


# ─── /models/{name} ────────────────────────────────────────────────────
def test_get_model_versions(client: TestClient, auth_headers):
    fake = [
        {"name": "iris", "latest_versions": [{"version": "1"}]},
        {"name": "house", "latest_versions": [{"version": "2"}]},
    ]
    with patch("backend.app.routers.models.mlflow_service.list_registered_models", return_value=fake):
        r = client.get("/api/v1/models/iris", headers=auth_headers)
    assert r.status_code == 200
    assert r.json() == [{"version": "1"}]


def test_get_model_versions_404(client: TestClient, auth_headers):
    with patch("backend.app.routers.models.mlflow_service.list_registered_models", return_value=[]):
        r = client.get("/api/v1/models/nope", headers=auth_headers)
    assert r.status_code == 404


# ─── /models/{name}/latest ─────────────────────────────────────────────
def test_get_latest_version(client: TestClient, auth_headers):
    fake_info = {
        "name": "iris", "version": "3", "run_id": "xyz",
        "current_stage": "Production", "source": "runs:/xyz/model",
    }
    with patch("backend.app.routers.models.mlflow_service.get_latest_model_version", return_value=fake_info) as g:
        r = client.get("/api/v1/models/iris/latest?stage=Production", headers=auth_headers)
    assert r.status_code == 200
    assert r.json()["version"] == "3"
    g.assert_called_once_with("iris", stage="Production")


def test_get_latest_version_404(client: TestClient, auth_headers):
    with patch("backend.app.routers.models.mlflow_service.get_latest_model_version", return_value=None):
        r = client.get("/api/v1/models/iris/latest", headers=auth_headers)
    assert r.status_code == 404
    assert "iris" in r.json()["detail"]
