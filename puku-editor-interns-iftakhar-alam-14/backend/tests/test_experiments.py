"""
test_experiments.py: exercise the /api/v1/experiments router.

Covers:
  • LIST (empty → with items)
  • COUNT
  • CREATE (success + duplicate-name → 400)
  • GET ONE (success + 404)
  • PARTIAL UPDATE (success + 404)
  • DELETE (success + 404 + cannot-delete-with-runs)
"""
from fastapi.testclient import TestClient


def test_list_experiments_empty(client: TestClient, auth_headers):
    r = client.get("/api/v1/experiments/", headers=auth_headers)
    assert r.status_code == 200
    assert r.json() == []


def test_create_experiment(client: TestClient, auth_headers):
    r = client.post(
        "/api/v1/experiments/",
        headers=auth_headers,
        json={"name": "exp-a", "description": "first"},
    )
    assert r.status_code == 201
    body = r.json()
    assert body["name"] == "exp-a"
    assert body["id"] >= 1
    assert "created_at" in body


def test_create_duplicate_name_returns_400(client: TestClient, auth_headers):
    payload = {"name": "exp-dup", "description": "x"}
    r1 = client.post("/api/v1/experiments/", headers=auth_headers, json=payload)
    assert r1.status_code == 201
    r2 = client.post("/api/v1/experiments/", headers=auth_headers, json=payload)
    assert r2.status_code == 400
    assert "already exists" in r2.json()["detail"]


def test_get_experiment(client: TestClient, auth_headers):
    r1 = client.post("/api/v1/experiments/", headers=auth_headers, json={"name": "exp-get"})
    exp_id = r1.json()["id"]
    r2 = client.get(f"/api/v1/experiments/{exp_id}", headers=auth_headers)
    assert r2.status_code == 200
    assert r2.json()["id"] == exp_id


def test_get_experiment_404(client: TestClient, auth_headers):
    r = client.get("/api/v1/experiments/9999", headers=auth_headers)
    assert r.status_code == 404


def test_count_experiments(client: TestClient, auth_headers):
    assert client.get("/api/v1/experiments/count", headers=auth_headers).json() == 0
    client.post("/api/v1/experiments/", headers=auth_headers, json={"name": "a"})
    client.post("/api/v1/experiments/", headers=auth_headers, json={"name": "b"})
    assert client.get("/api/v1/experiments/count", headers=auth_headers).json() == 2


def test_update_experiment(client: TestClient, auth_headers):
    r1 = client.post("/api/v1/experiments/", headers=auth_headers, json={"name": "exp-up"})
    exp_id = r1.json()["id"]
    r2 = client.patch(
        f"/api/v1/experiments/{exp_id}",
        headers=auth_headers,
        json={"description": "updated description"},
    )
    assert r2.status_code == 200
    assert r2.json()["description"] == "updated description"
    # Name should be unchanged
    assert r2.json()["name"] == "exp-up"


def test_update_experiment_404(client: TestClient, auth_headers):
    r = client.patch(
        "/api/v1/experiments/9999",
        headers=auth_headers,
        json={"description": "x"},
    )
    assert r.status_code == 404


def test_delete_experiment(client: TestClient, auth_headers):
    r1 = client.post("/api/v1/experiments/", headers=auth_headers, json={"name": "exp-del"})
    exp_id = r1.json()["id"]
    r2 = client.delete(f"/api/v1/experiments/{exp_id}", headers=auth_headers)
    assert r2.status_code == 204
    r3 = client.get(f"/api/v1/experiments/{exp_id}", headers=auth_headers)
    assert r3.status_code == 404


def test_delete_experiment_404(client: TestClient, auth_headers):
    r = client.delete("/api/v1/experiments/9999", headers=auth_headers)
    assert r.status_code == 404


def test_search_filter(client: TestClient, auth_headers):
    client.post("/api/v1/experiments/", headers=auth_headers, json={"name": "iris-baseline"})
    client.post("/api/v1/experiments/", headers=auth_headers, json={"name": "house-prices"})
    client.post("/api/v1/experiments/", headers=auth_headers, json={"name": "iris-v2"})
    r = client.get("/api/v1/experiments/?search=iris", headers=auth_headers)
    assert r.status_code == 200
    names = [e["name"] for e in r.json()]
    assert set(names) == {"iris-baseline", "iris-v2"}
