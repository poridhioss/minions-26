"""
Shared pytest fixtures.

The big idea: every test gets a fresh :class:`MLTrackerClient` built on
top of an ``httpx.MockTransport`` (via ``respx``). This means the
SDK is tested in complete isolation from a running backend — no Flask
test client, no live server, no port collisions.

``mock_client`` is the workhorse fixture: it returns the respx router
and the client, both wired up. Tests then do::

    def test_something(mock_client):
        mock_client.post("/api/v1/experiments/").mock(
            return_value=httpx.Response(200, json={...})
        )
        ...
        mltracker.experiments.create(...)
"""
from __future__ import annotations

from typing import Iterator, Tuple

import httpx
import pytest
import respx

import mltracker
from mltracker.client import MLTrackerClient


@pytest.fixture(autouse=True)
def _reset_singleton() -> Iterator[None]:
    """
    The SDK exposes a module-level singleton client. Without resetting,
    tests that call ``mltracker.login()`` would leak state across tests.
    """
    mltracker.reset()
    yield
    mltracker.reset()


@pytest.fixture
def mock_client() -> Iterator[Tuple[respx.Router, MLTrackerClient]]:
    """
    Yields ``(router, client)`` where the client is bound to ``router`` as
    its transport. All outgoing requests are intercepted — anything not
    explicitly mocked will raise ``respx``'s "no route matched" error,
    which is what we want (catches over-mocking).
    """
    with respx.mock(base_url="http://testserver") as router:
        # respx intercepts the underlying httpx transport; the client
        # uses a normal ``httpx.Client`` underneath, so this works
        # transparently with our request hooks (X-API-Key, etc.).
        client = MLTrackerClient(url="http://testserver", api_key="test-key")
        try:
            yield router, client
        finally:
            client.close()


# ─── Sample response bodies ────────────────────────────────────────────
# Centralised so individual tests don't have to repeat the JSON. These
# mirror what the backend actually returns; if the backend schema
# changes, update these and any test that asserts on a field will
# start failing — exactly the signal we want.

EXPERIMENT = {
    "id": 1,
    "name": "iris-baseline",
    "description": "Synthetic-blobs classification",
    "tags": "sklearn,rf",
    "created_at": "2024-01-15T10:30:00",
    "updated_at": None,
}

RUN = {
    "id": 42,
    "experiment_id": 1,
    "run_name": "rf-v1",
    "status": "RUNNING",
    "metrics": {"loss": 0.42},
    "parameters": {"n_estimators": "100"},
    "tags": {"framework": "sklearn"},
    "start_time": "2024-01-15T10:30:01",
    "end_time": None,
    "artifact_uri": None,
}
