"""
conftest.py: shared pytest fixtures for the backend test suite.

Strategy
--------
We don't want tests to require a running Postgres / MLflow / MinIO.
Instead we:

  1. Use a single SQLite database on **disk** in a temp file
     (``backend/tests/_tmp/test.db``) so the schema is persistent across
     connections. SQLite in-memory is fragile — every call to
     ``engine.dispose()`` (which TestClient's lifespan shutdown does) gives
     you a fresh empty DB. A temp file sidesteps that whole class of bugs.

  2. Monkey-patch ``backend.app.database`` and ``backend.app.main`` so the
     app's lifespan, the dependency override, and the test's own
     per-test-cleanup session ALL talk to the same engine.

  3. Build the schema once per session, then truncate all tables before
     every test (per-test isolation without the cost of re-creating
     the schema).

  4. Replace the ``get_db`` FastAPI dependency with a generator that
     yields a SessionLocal()-bound session. Override is cleared in
     teardown.

  5. Stub the ``mlflow_service`` module so the routers' "best-effort
     forward to MLflow" calls don't block on a real MLflow server
     (which isn't running in the test environment).

Tests import ``client`` and ``auth_headers`` from this module:

    def test_list(client, auth_headers):
        r = client.get("/api/v1/experiments/", headers=auth_headers)
        assert r.status_code == 200
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Generator

# Make sure the project root is on sys.path BEFORE importing the app
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

# Provide env vars before any app imports read them
os.environ.setdefault("SECRET_KEY", "test-secret-key-12345")
os.environ.setdefault("API_KEYS", "test-key")
os.environ.setdefault("MLFLOW_TRACKING_URI", "http://localhost:5000")
os.environ.setdefault("MLFLOW_ARTIFACT_ROOT", "./mlruns")

# ─── Temp-file SQLite DB ───────────────────────────────────────────────
# A file-based SQLite DB is the only reliable choice here. In-memory
# variants break as soon as the app's lifespan calls ``engine.dispose()``
# (a fresh connection from a (re)created engine sees an empty DB).
_TMP_DIR = Path(__file__).resolve().parent / "_tmp"
_TMP_DIR.mkdir(exist_ok=True)
_DB_FILE = _TMP_DIR / "test.db"
# Make sure each test run starts with a clean DB
if _DB_FILE.exists():
    _DB_FILE.unlink()

_TEST_DB_URL = f"sqlite:///{_DB_FILE}"
os.environ["DATABASE_URL"] = _TEST_DB_URL

# Now safe to import the app
from backend.app import database as db_module  # noqa: E402
from backend.app.database import Base, get_db  # noqa: E402
import backend.app.models  # noqa: E402,F401  (register models on Base.metadata)

# ─── The single test engine ────────────────────────────────────────────
engine = create_engine(
    _TEST_DB_URL,
    connect_args={"check_same_thread": False},
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Enable FK enforcement on SQLite (off by default)
@event.listens_for(engine, "connect")
def _enable_fk(dbapi_conn, _):
    cur = dbapi_conn.cursor()
    cur.execute("PRAGMA foreign_keys=ON")
    cur.close()

# Monkey-patch the module-level engine / SessionLocal that the rest of
# the app captured at import time.
db_module.engine = engine
db_module.SessionLocal = TestingSessionLocal


def _override_get_db():
    """Dependency override factory — uses TestingSessionLocal directly."""
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


db_module.get_db = _override_get_db


# ─── Stub MLflow service ───────────────────────────────────────────────
# The routers call ``mlflow_service.start_mlflow_run`` / ``log_metrics`` /
# ``list_registered_models`` etc. In tests we don't want a real MLflow
# server — and worse, if MLflow is offline the MlflowClient blocks on
# HTTP requests, hanging the test suite. Swap the module for a no-op stub.
class _NoopRun:
    def __enter__(self): return self
    def __exit__(self, *a): return False


class _MLflowStub:
    def start_mlflow_run(self, *a, **kw): return _NoopRun()
    def log_params(self, params): pass
    def log_metrics(self, metrics, step=None): pass
    def log_sklearn_model(self, model, artifact_path="model"): return f"runs:/{id(model)}/{artifact_path}"
    def end_mlflow_run(self, status="FINISHED"): pass
    def list_registered_models(self): return []
    def get_latest_model_version(self, name, stage="Production"): return None
    def load_model_by_uri(self, uri): raise RuntimeError("MLflow is stubbed in tests")
    def get_or_create_mlflow_experiment(self, name): return "0"


import backend.app.services.mlflow_service as mlflow_service_module
mlflow_service_module.start_mlflow_run = _MLflowStub().start_mlflow_run
mlflow_service_module.log_params = _MLflowStub().log_params
mlflow_service_module.log_metrics = _MLflowStub().log_metrics
mlflow_service_module.log_sklearn_model = _MLflowStub().log_sklearn_model
mlflow_service_module.end_mlflow_run = _MLflowStub().end_mlflow_run
mlflow_service_module.list_registered_models = _MLflowStub().list_registered_models
mlflow_service_module.get_latest_model_version = _MLflowStub().get_latest_model_version
mlflow_service_module.load_model_by_uri = _MLflowStub().load_model_by_uri
mlflow_service_module.get_or_create_mlflow_experiment = _MLflowStub().get_or_create_mlflow_experiment


# ─── Schema bootstrap (once per test session) ──────────────────────────
@pytest.fixture(scope="session", autouse=True)
def _create_tables() -> Generator[None, None, None]:
    """Create all tables on the in-memory engine before any test runs."""
    Base.metadata.create_all(bind=engine)
    yield
    # Best-effort cleanup; not strictly necessary
    engine.dispose()
    if _DB_FILE.exists():
        _DB_FILE.unlink()


# ─── Per-test DB cleanup ───────────────────────────────────────────────
@pytest.fixture()
def db_session() -> Generator:
    """
    Truncate all tables before each test, then yield a session so the test
    can do additional DB work.
    """
    session = TestingSessionLocal()
    try:
        # Reverse so we don't fight FKs (runs → experiments)
        for table in reversed(Base.metadata.sorted_tables):
            session.execute(table.delete())
        session.commit()
        yield session
    finally:
        session.close()


# ─── FastAPI test client ───────────────────────────────────────────────
@pytest.fixture()
def client(db_session) -> Generator[TestClient, None, None]:
    """
    TestClient with:
      • ``get_db`` overridden to use our test session
      • ``main.py``'s captured ``engine`` / ``SessionLocal`` rebound to
        the test engine (so the lifespan's ``create_all`` runs on the
        same DB the test sees).
    """
    from backend.app.main import app
    import backend.app.main as main_module

    app.dependency_overrides[get_db] = _override_get_db
    main_module.engine = engine
    main_module.SessionLocal = TestingSessionLocal

    with TestClient(app, raise_server_exceptions=True) as c:
        yield c
    app.dependency_overrides.clear()


# ─── Auth header convenience ───────────────────────────────────────────
@pytest.fixture()
def auth_headers() -> dict:
    """Headers every authenticated request must include."""
    return {"X-API-Key": "test-key"}
