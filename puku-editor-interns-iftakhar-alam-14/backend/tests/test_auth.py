"""
test_auth.py: verify the X-API-Key authentication gate.

All routers (except /health) require a valid API key.
"""
from fastapi.testclient import TestClient


def test_health_is_open(client: TestClient):
    """The /health endpoint must work without auth (used by load balancers)."""
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    # The health endpoint returns {"status": "ok", ...}
    assert body["status"] == "ok"


def test_missing_api_key_returns_401(client: TestClient):
    """Requests with no X-API-Key header must be rejected."""
    r = client.get("/api/v1/experiments/")
    assert r.status_code == 401
    assert "API key" in r.json()["detail"]


def test_wrong_api_key_returns_401(client: TestClient):
    """Requests with a bogus key must be rejected."""
    r = client.get("/api/v1/experiments/", headers={"X-API-Key": "nope"})
    assert r.status_code == 401
    assert "Invalid" in r.json()["detail"]


def test_valid_api_key_passes_auth(client: TestClient, auth_headers):
    """A valid key should let us through to the (empty) experiment list."""
    r = client.get("/api/v1/experiments/", headers=auth_headers)
    assert r.status_code == 200
    assert r.json() == []
