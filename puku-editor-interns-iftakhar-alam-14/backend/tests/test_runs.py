"""
test_runs.py: exercise the /api/v1/runs router.

Covers:
  • CREATE (success + parent-experiment-doesn't-exist → 400)
  • LIST + COUNT + filters
  • GET ONE (success + 404)
  • PATCH (status, end_time, metrics)
  • DELETE
  • log_metric / log_parameter
  • finish
"""
import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def experiment_id(client: TestClient, auth_headers) -> int:
    """Create a parent experiment for run tests."""
    r = client.post("/api/v1/experiments/", headers=auth_headers, json={"name": "parent-exp"})
    return r.json()["id"]


def test_create_run(client: TestClient, auth_headers, experiment_id):
    r = client.post(
        "/api/v1/runs/",
        headers=auth_headers,
        json={
            "experiment_id": experiment_id,
            "run_name": "run-1",
            "status": "RUNNING",
        },
    )
    assert r.status_code == 201
    body = r.json()
    assert body["experiment_id"] == experiment_id
    assert body["run_name"] == "run-1"
    assert body["status"] == "RUNNING"


def test_create_run_with_missing_experiment(client: TestClient, auth_headers):
    r = client.post(
        "/api/v1/runs/",
        headers=auth_headers,
        json={"experiment_id": 9999, "run_name": "orphan"},
    )
    assert r.status_code == 400
    assert "does not exist" in r.json()["detail"]


def test_list_runs_empty(client: TestClient, auth_headers, experiment_id):
    r = client.get("/api/v1/runs/", headers=auth_headers)
    assert r.status_code == 200
    assert r.json() == []


def test_count_runs(client: TestClient, auth_headers, experiment_id):
    assert client.get("/api/v1/runs/count", headers=auth_headers).json() == 0
    client.post("/api/v1/runs/", headers=auth_headers,
                json={"experiment_id": experiment_id, "run_name": "r1"})
    client.post("/api/v1/runs/", headers=auth_headers,
                json={"experiment_id": experiment_id, "run_name": "r2"})
    assert client.get("/api/v1/runs/count", headers=auth_headers).json() == 2


def test_filter_runs_by_experiment(client: TestClient, auth_headers, experiment_id):
    # Create another experiment with a run
    r = client.post("/api/v1/experiments/", headers=auth_headers, json={"name": "other"})
    other_id = r.json()["id"]
    client.post("/api/v1/runs/", headers=auth_headers,
                json={"experiment_id": experiment_id, "run_name": "in-first"})
    client.post("/api/v1/runs/", headers=auth_headers,
                json={"experiment_id": other_id, "run_name": "in-second"})

    r = client.get(f"/api/v1/runs/?experiment_id={experiment_id}", headers=auth_headers)
    assert r.status_code == 200
    names = [run["run_name"] for run in r.json()]
    assert names == ["in-first"]


def test_get_run(client: TestClient, auth_headers, experiment_id):
    r = client.post(
        "/api/v1/runs/",
        headers=auth_headers,
        json={"experiment_id": experiment_id, "run_name": "lookup"},
    )
    run_id = r.json()["id"]
    r2 = client.get(f"/api/v1/runs/{run_id}", headers=auth_headers)
    assert r2.status_code == 200
    assert r2.json()["run_name"] == "lookup"


def test_get_run_404(client: TestClient, auth_headers):
    r = client.get("/api/v1/runs/9999", headers=auth_headers)
    assert r.status_code == 404


def test_patch_run_status(client: TestClient, auth_headers, experiment_id):
    r = client.post(
        "/api/v1/runs/",
        headers=auth_headers,
        json={"experiment_id": experiment_id, "run_name": "r", "status": "RUNNING"},
    )
    run_id = r.json()["id"]
    r2 = client.patch(
        f"/api/v1/runs/{run_id}",
        headers=auth_headers,
        json={"status": "FINISHED"},
    )
    assert r2.status_code == 200
    assert r2.json()["status"] == "FINISHED"


def test_log_metric(client: TestClient, auth_headers, experiment_id):
    r = client.post(
        "/api/v1/runs/",
        headers=auth_headers,
        json={"experiment_id": experiment_id, "run_name": "r"},
    )
    run_id = r.json()["id"]
    r2 = client.post(
        f"/api/v1/runs/{run_id}/metrics",
        headers=auth_headers,
        json={"key": "accuracy", "value": 0.94},
    )
    assert r2.status_code == 200
    assert r2.json()["metrics"]["accuracy"] == 0.94


def test_log_parameter(client: TestClient, auth_headers, experiment_id):
    r = client.post(
        "/api/v1/runs/",
        headers=auth_headers,
        json={"experiment_id": experiment_id, "run_name": "r"},
    )
    run_id = r.json()["id"]
    r2 = client.post(
        f"/api/v1/runs/{run_id}/parameters",
        headers=auth_headers,
        json={"key": "lr", "value": "0.001"},
    )
    assert r2.status_code == 200
    assert r2.json()["parameters"]["lr"] == "0.001"


def test_finish_run(client: TestClient, auth_headers, experiment_id):
    r = client.post(
        "/api/v1/runs/",
        headers=auth_headers,
        json={"experiment_id": experiment_id, "run_name": "r"},
    )
    run_id = r.json()["id"]
    r2 = client.post(
        f"/api/v1/runs/{run_id}/finish",
        headers=auth_headers,
        json={"status": "FINISHED", "final_metrics": {"accuracy": 0.95}},
    )
    assert r2.status_code == 200
    body = r2.json()
    assert body["status"] == "FINISHED"
    assert body["metrics"]["accuracy"] == 0.95
    assert body["end_time"] is not None


def test_finish_run_rejects_bad_status(client: TestClient, auth_headers, experiment_id):
    r = client.post(
        "/api/v1/runs/",
        headers=auth_headers,
        json={"experiment_id": experiment_id, "run_name": "r"},
    )
    run_id = r.json()["id"]
    r2 = client.post(
        f"/api/v1/runs/{run_id}/finish",
        headers=auth_headers,
        json={"status": "WAT", "final_metrics": {}},
    )
    assert r2.status_code == 400


def test_delete_run(client: TestClient, auth_headers, experiment_id):
    r = client.post(
        "/api/v1/runs/",
        headers=auth_headers,
        json={"experiment_id": experiment_id, "run_name": "r"},
    )
    run_id = r.json()["id"]
    r2 = client.delete(f"/api/v1/runs/{run_id}", headers=auth_headers)
    assert r2.status_code == 204
    r3 = client.get(f"/api/v1/runs/{run_id}", headers=auth_headers)
    assert r3.status_code == 404


def test_cannot_delete_experiment_with_runs(client: TestClient, auth_headers, experiment_id):
    client.post(
        "/api/v1/runs/",
        headers=auth_headers,
        json={"experiment_id": experiment_id, "run_name": "r"},
    )
    r = client.delete(f"/api/v1/experiments/{experiment_id}", headers=auth_headers)
    assert r.status_code == 400
    assert "run(s)" in r.json()["detail"]
