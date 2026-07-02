"""
End-to-end tests for the SDK using a mocked transport.

Coverage:
  • Login / singleton lifecycle
  • X-API-Key header is attached to every request
  • CRUD on experiments and runs
  • The ``Run`` context manager (happy path + exception path)
  • Exception mapping (401/404/422 → AuthenticationError/NotFoundError/ValidationError)
  • ``predict()`` happy path
  • ``health()`` works without auth
"""
from __future__ import annotations

import httpx
import pytest

import mltracker
from mltracker import (
    APIError,
    AuthenticationError,
    Experiment,
    HealthResponse,
    MLTrackerClient,
    NotFoundError,
    PredictResponse,
    ValidationError,
)
from mltracker.types import Run  # the data model (not the context manager)
from mltracker.runs import Run as RunContext  # the context manager class

# Pull the constants from conftest by importing the module.
# Relative import — ``sdk`` isn't installed, only ``mltracker`` is, so we
# have to reach into the same package the conftest is in.
from .conftest import EXPERIMENT, RUN  # type: ignore[import-not-found]


# ════════════════════════════════════════════════════════════════════════
#  Singleton lifecycle
# ════════════════════════════════════════════════════════════════════════


class TestSingleton:
    def test_login_creates_singleton(self) -> None:
        assert not mltracker.is_configured()
        mltracker.login(url="http://api:8000", api_key="k")
        assert mltracker.is_configured()
        client = mltracker._get_client()
        assert client.base_url == "http://api:8000"
        assert client.api_key == "k"

    def test_login_strips_api_prefix(self) -> None:
        """Passing ``.../api/v1`` shouldn't double the prefix."""
        mltracker.login(url="http://api:8000/api/v1", api_key="k")
        assert mltracker._get_client().base_url == "http://api:8000"

    def test_reset_clears_singleton(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # Strip any env vars that may have been set by sibling tests so
        # the lazy ``from_env()`` fallback in ``_get_client`` doesn't
        # resurrect a client after ``reset()``.
        monkeypatch.delenv("MLTRACKER_URL", raising=False)
        monkeypatch.delenv("MLTRACKER_API_KEY", raising=False)
        mltracker.login(url="http://api:8000", api_key="k")
        mltracker.reset()
        assert not mltracker.is_configured()
        # Subsequent facade calls should fail loudly (no client configured)
        with pytest.raises(RuntimeError):
            mltracker.experiments.list()

    def test_login_env_fallback(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("MLTRACKER_URL", "http://from-env:9000")
        monkeypatch.setenv("MLTRACKER_API_KEY", "from-env")
        mltracker.login()  # both args omitted → fall back to env
        client = mltracker._get_client()
        assert client.base_url == "http://from-env:9000"
        assert client.api_key == "from-env"


# ════════════════════════════════════════════════════════════════════════
#  Auth header
# ════════════════════════════════════════════════════════════════════════


class TestAuth:
    def test_api_key_attached(self, mock_client) -> None:
        router, client = mock_client
        # ``pass_through`` so respx doesn't try to actually dispatch;
        # we just want to inspect the request.
        route = router.get("/api/v1/experiments/").mock(
            return_value=httpx.Response(200, json=[EXPERIMENT]),
        )

        client.experiments.list()

        assert route.called
        request = route.calls[0].request
        assert request.headers.get("X-API-Key") == "test-key"

    def test_blank_key_omits_header(self, mock_client) -> None:
        router, _ = mock_client
        # Rebuild the client with no key.
        client = MLTrackerClient(url="http://testserver", api_key="")
        try:
            route = router.get("/api/v1/experiments/").mock(
                return_value=httpx.Response(200, json=[]),
            )
            client.experiments.list()
            request = route.calls[0].request
            # X-API-Key should be absent (or empty), not "None"
            assert not request.headers.get("X-API-Key")
        finally:
            client.close()


# ════════════════════════════════════════════════════════════════════════
#  Experiments CRUD
# ════════════════════════════════════════════════════════════════════════


class TestExperiments:
    def test_list_returns_models(self, mock_client) -> None:
        router, client = mock_client
        router.get("/api/v1/experiments/").mock(
            return_value=httpx.Response(200, json=[EXPERIMENT, EXPERIMENT]),
        )
        result = client.experiments.list()
        assert len(result) == 2
        assert all(isinstance(e, Experiment) for e in result)
        assert result[0].id == 1
        assert result[0].name == "iris-baseline"

    def test_list_with_pagination(self, mock_client) -> None:
        router, client = mock_client
        route = router.get("/api/v1/experiments/").mock(
            return_value=httpx.Response(200, json=[EXPERIMENT]),
        )
        client.experiments.list(skip=10, limit=25, search="iris")
        # Confirm the params are forwarded to the server.
        url = route.calls[0].request.url
        assert "skip=10" in str(url)
        assert "limit=25" in str(url)
        assert "search=iris" in str(url)

    def test_get(self, mock_client) -> None:
        router, client = mock_client
        router.get("/api/v1/experiments/1").mock(
            return_value=httpx.Response(200, json=EXPERIMENT),
        )
        exp = client.experiments.get(1)
        assert exp.id == 1
        assert exp.name == "iris-baseline"

    def test_create(self, mock_client) -> None:
        router, client = mock_client
        route = router.post("/api/v1/experiments/").mock(
            return_value=httpx.Response(201, json=EXPERIMENT),
        )
        from mltracker.types import ExperimentCreate

        exp = client.experiments.create(ExperimentCreate(name="iris-baseline", description="x"))
        assert exp.id == 1
        # Verify the body that was sent
        import json as _json
        body = _json.loads(route.calls[0].request.content)
        assert body["name"] == "iris-baseline"
        assert body["description"] == "x"

    def test_update(self, mock_client) -> None:
        router, client = mock_client
        updated = {**EXPERIMENT, "description": "new desc"}
        router.patch("/api/v1/experiments/1").mock(
            return_value=httpx.Response(200, json=updated),
        )
        from mltracker.types import ExperimentUpdate
        exp = client.experiments.update(1, ExperimentUpdate(description="new desc"))
        assert exp.description == "new desc"

    def test_delete(self, mock_client) -> None:
        router, client = mock_client
        route = router.delete("/api/v1/experiments/1").mock(
            return_value=httpx.Response(204),
        )
        client.experiments.delete(1)
        assert route.called


# ════════════════════════════════════════════════════════════════════════
#  Runs CRUD + log_* helpers
# ════════════════════════════════════════════════════════════════════════


class TestRuns:
    def test_create(self, mock_client) -> None:
        router, client = mock_client
        router.post("/api/v1/runs/").mock(
            return_value=httpx.Response(201, json=RUN),
        )
        from mltracker.types import RunCreate
        run = client.runs.create(RunCreate(experiment_id=1, run_name="rf-v1"))
        assert isinstance(run, Run)
        assert run.id == 42
        assert run.experiment_id == 1

    def test_log_metric(self, mock_client) -> None:
        router, client = mock_client
        route = router.post("/api/v1/runs/42/metrics").mock(
            return_value=httpx.Response(200, json=RUN),
        )
        client.runs.log_metric(42, "loss", 0.42, step=3)
        import json as _json
        body = _json.loads(route.calls[0].request.content)
        assert body == {"key": "loss", "value": 0.42, "step": 3}

    def test_log_metric_no_step(self, mock_client) -> None:
        router, client = mock_client
        route = router.post("/api/v1/runs/42/metrics").mock(
            return_value=httpx.Response(200, json=RUN),
        )
        client.runs.log_metric(42, "loss", 0.42)
        import json as _json
        body = _json.loads(route.calls[0].request.content)
        # ``step`` should be omitted, not sent as null
        assert "step" not in body
        assert body["key"] == "loss"

    def test_log_parameter(self, mock_client) -> None:
        router, client = mock_client
        route = router.post("/api/v1/runs/42/parameters").mock(
            return_value=httpx.Response(200, json=RUN),
        )
        client.runs.log_parameter(42, "lr", "0.01")
        import json as _json
        body = _json.loads(route.calls[0].request.content)
        assert body == {"key": "lr", "value": "0.01"}

    def test_finish(self, mock_client) -> None:
        router, client = mock_client
        route = router.post("/api/v1/runs/42/finish").mock(
            return_value=httpx.Response(200, json={**RUN, "status": "FINISHED", "end_time": "2024-01-15T10:35:00"}),
        )
        client.runs.finish(42, status="FINISHED", final_metrics={"acc": 0.95})
        import json as _json
        body = _json.loads(route.calls[0].request.content)
        assert body["status"] == "FINISHED"
        assert body["final_metrics"] == {"acc": 0.95}


# ════════════════════════════════════════════════════════════════════════
#  Predictions
# ════════════════════════════════════════════════════════════════════════


class TestPredictions:
    def test_predict_happy_path(self, mock_client) -> None:
        router, client = mock_client
        route = router.post("/api/v1/predictions/predict").mock(
            return_value=httpx.Response(
                200,
                json={
                    "predictions": [0],
                    "model_name": "iris-baseline",
                    "model_version": "1",
                    "model_stage": "Production",
                },
            ),
        )
        result = client.predictions.predict(
            features=[5.1, 3.5, 1.4, 0.2],
            model_name="iris-baseline",
            stage="Production",
        )
        assert isinstance(result, PredictResponse)
        assert result.predictions == [0]
        assert result.model_name == "iris-baseline"

        # And the body was shaped correctly (no ``version`` field — see
        # the comment in types.py about the backend schema).
        import json as _json
        body = _json.loads(route.calls[0].request.content)
        assert body["model_name"] == "iris-baseline"
        assert body["stage"] == "Production"
        assert "version" not in body

    def test_predict_requires_model_identifier(self, mock_client) -> None:
        _, client = mock_client
        with pytest.raises(ValueError, match="model_name.*model_uri"):
            client.predictions.predict(features=[1.0, 2.0])

    def test_top_level_predict_helper(self, mock_client) -> None:
        router, _ = mock_client
        router.post("/api/v1/predictions/predict").mock(
            return_value=httpx.Response(
                200,
                json={"predictions": [1], "model_name": "iris", "model_version": "2", "model_stage": "Production"},
            ),
        )
        mltracker.login(url="http://testserver", api_key="k")
        result = mltracker.predict(features=[1.0, 2.0, 3.0], model_name="iris")
        assert result.predictions == [1]
        assert result.model_version == "2"


# ════════════════════════════════════════════════════════════════════════
#  Health
# ════════════════════════════════════════════════════════════════════════


class TestHealth:
    def test_health(self, mock_client) -> None:
        router, client = mock_client
        # /health is NOT under /api/v1 in the backend.
        router.get("/health").mock(
            return_value=httpx.Response(200, json={"status": "ok", "app": "ml-tracker", "version": "0.1.0"}),
        )
        result = client.health.get()
        assert isinstance(result, HealthResponse)
        assert result.status == "ok"
        assert result.app == "ml-tracker"


# ════════════════════════════════════════════════════════════════════════
#  Exception mapping
# ════════════════════════════════════════════════════════════════════════


class TestExceptions:
    def test_401_maps_to_authentication_error(self, mock_client) -> None:
        router, client = mock_client
        router.get("/api/v1/experiments/1").mock(
            return_value=httpx.Response(401, json={"detail": "Invalid API key"}),
        )
        with pytest.raises(AuthenticationError) as exc_info:
            client.experiments.get(1)
        assert exc_info.value.status_code == 401
        assert "Invalid API key" in str(exc_info.value)

    def test_404_maps_to_not_found(self, mock_client) -> None:
        router, client = mock_client
        router.get("/api/v1/experiments/999").mock(
            return_value=httpx.Response(404, json={"detail": "Experiment not found"}),
        )
        with pytest.raises(NotFoundError) as exc_info:
            client.experiments.get(999)
        assert exc_info.value.status_code == 404

    def test_422_maps_to_validation_error(self, mock_client) -> None:
        router, client = mock_client
        # FastAPI's 422 body is a list of {loc, msg, type} objects
        router.post("/api/v1/experiments/").mock(
            return_value=httpx.Response(
                422,
                json={"detail": [{"loc": ["body", "name"], "msg": "field required", "type": "value_error.missing"}]},
            ),
        )
        from mltracker.types import ExperimentCreate
        with pytest.raises(ValidationError) as exc_info:
            # The payload must be valid client-side; we want the SERVER
            # to reject it so the SDK can map the 422.
            client.experiments.create(ExperimentCreate(name="valid-name"))
        assert exc_info.value.status_code == 422

    def test_500_maps_to_generic_api_error(self, mock_client) -> None:
        router, client = mock_client
        router.get("/api/v1/experiments/").mock(
            return_value=httpx.Response(500, json={"detail": "Database is on fire"}),
        )
        with pytest.raises(APIError) as exc_info:
            client.experiments.list()
        assert exc_info.value.status_code == 500

    def test_validation_error_extracts_pydantic_list(self, mock_client) -> None:
        """422 from FastAPI returns a list of errors — we should join them."""
        from mltracker.exceptions import _extract_detail

        body = {"detail": [{"loc": ["body", "name"], "msg": "field required"}]}
        msg = _extract_detail(body)
        assert "name" in msg
        assert "field required" in msg


# ════════════════════════════════════════════════════════════════════════
#  Run context manager
# ════════════════════════════════════════════════════════════════════════


class TestRunContext:
    def _login(self, mock_client) -> MLTrackerClient:
        router, client = mock_client
        mltracker.login(client=client)
        return client

    def test_happy_path(self, mock_client) -> None:
        self._login(mock_client)
        router, _ = mock_client
        # 1. create run
        router.post("/api/v1/runs/").mock(
            return_value=httpx.Response(201, json=RUN),
        )
        # 2. log_param
        router.post("/api/v1/runs/42/parameters").mock(
            return_value=httpx.Response(200, json=RUN),
        )
        # 3. log_metric
        router.post("/api/v1/runs/42/metrics").mock(
            return_value=httpx.Response(200, json=RUN),
        )
        # 4. finish
        finished_run = {**RUN, "status": "FINISHED", "end_time": "2024-01-15T10:35:00"}
        router.post("/api/v1/runs/42/finish").mock(
            return_value=httpx.Response(200, json=finished_run),
        )

        with mltracker.run(experiment_id=1, run_name="rf-v1") as run:
            assert isinstance(run, RunContext)
            assert run.id == 42
            assert run.status.value == "RUNNING"  # before exit
            run.log_param("model_type", "RandomForest")
            run.log_metric("loss", 0.42, step=0)

        # After exit, the SDK called /finish and the model is updated.
        assert run.is_finished
        # (run is still in scope because we kept the ``as`` binding.)
        # The most recent call should be to /finish with status=FINISHED
        finish_route = router.routes[-1]  # last registered = /finish
        # The Pydantic finish body should include status=FINISHED
        import json as _json
        body = _json.loads(finish_route.calls[0].request.content)
        assert body["status"] == "FINISHED"

    def test_exception_marks_failed(self, mock_client) -> None:
        self._login(mock_client)
        router, _ = mock_client
        # create + finish(FAILED)
        router.post("/api/v1/runs/").mock(
            return_value=httpx.Response(201, json=RUN),
        )
        failed_run = {**RUN, "status": "FAILED"}
        router.post("/api/v1/runs/42/finish").mock(
            return_value=httpx.Response(200, json=failed_run),
        )

        with pytest.raises(RuntimeError, match="boom"):
            with mltracker.run(experiment_id=1, run_name="rf-v1") as run:
                raise RuntimeError("boom")

        # The /finish call should have been made with status=FAILED
        finish_route = router.routes[-1]
        import json as _json
        body = _json.loads(finish_route.calls[0].request.content)
        assert body["status"] == "FAILED"

    def test_finish_is_idempotent(self, mock_client) -> None:
        self._login(mock_client)
        router, _ = mock_client
        router.post("/api/v1/runs/").mock(
            return_value=httpx.Response(201, json=RUN),
        )
        finished_run = {**RUN, "status": "FINISHED"}
        finish_route = router.post("/api/v1/runs/42/finish").mock(
            return_value=httpx.Response(200, json=finished_run),
        )

        with mltracker.run(experiment_id=1) as run:
            run.finish()  # explicit finish before exit
            # Second finish should be a no-op
            run.finish()

        # The /finish endpoint should have been called exactly once
        assert finish_route.call_count == 1

    def test_run_helper_requires_experiment(self, mock_client) -> None:
        self._login(mock_client)
        with pytest.raises(ValueError, match="experiment_id.*experiment_name"):
            mltracker.run(run_name="oops")  # neither given

        with pytest.raises(ValueError, match="exactly one"):
            mltracker.run(run_name="oops", experiment_id=1, experiment_name="x")  # both given

    def test_run_helper_resolves_experiment_by_name(self, mock_client) -> None:
        self._login(mock_client)
        router, _ = mock_client
        # list returns the experiment
        router.get("/api/v1/experiments/").mock(
            return_value=httpx.Response(200, json=[EXPERIMENT]),
        )
        # and the create-run call
        router.post("/api/v1/runs/").mock(
            return_value=httpx.Response(201, json=RUN),
        )
        # finish (so the with-block cleans up)
        finished_run = {**RUN, "status": "FINISHED"}
        router.post("/api/v1/runs/42/finish").mock(
            return_value=httpx.Response(200, json=finished_run),
        )

        with mltracker.run(run_name="rf-v1", experiment_name="iris-baseline") as run:
            assert run.id == 42


# ════════════════════════════════════════════════════════════════════════
#  Top-level facade
# ════════════════════════════════════════════════════════════════════════


class TestFacades:
    def test_experiments_facade_routes_to_client(self, mock_client) -> None:
        router, client = mock_client
        router.get("/api/v1/experiments/").mock(
            return_value=httpx.Response(200, json=[EXPERIMENT]),
        )
        mltracker.login(client=client)
        result = mltracker.experiments.list()
        assert len(result) == 1
        assert isinstance(result[0], Experiment)
