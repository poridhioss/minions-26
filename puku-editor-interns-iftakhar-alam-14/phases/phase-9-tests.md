# Phase 9 — Backend Test Suite (pytest)

## 🎯 What This Phase Did

Phase 9 built a **full pytest test suite** for the FastAPI backend — 47 tests covering authentication, experiment CRUD, run CRUD, predictions, model invariants, and the prediction service. Every test runs in **< 2 seconds** with **no external dependencies** (no Postgres, no MLflow, no MinIO). The conftest stubs them all out.

This means future refactors and feature additions can land with confidence — if a test breaks, we know exactly what regressed.

---

## 📂 What Was Created

```
backend/tests/
├── conftest.py                    ← Shared fixtures (DB, client, auth, MLflow stub) ⭐
├── pytest.ini                     ← Pytest config (asyncio mode, testpaths)
├── test_auth.py                   ← 4 tests: API key enforcement
├── test_experiments.py            ← 11 tests: experiment CRUD + pagination
├── test_runs.py                   ← 14 tests: run lifecycle + log_metric / log_param
├── test_predictions.py            ← 5 tests: prediction endpoint validation
├── test_models.py                 ← 6 tests: ORM model invariants
└── test_prediction_service.py     ← 7 tests: prediction service unit tests
```

Total: **8 files, 47 tests, all passing in 1.05s.**

---

## ⭐ The Star File: `backend/tests/conftest.py`

This is the heart of the test suite. It handles 4 big problems in one place so every test file can stay tiny and focused.

### Problem 1: Don't need a real Postgres
Use a **file-based SQLite database** at `backend/tests/_tmp/test.db`.

```python
_TMP_DIR = Path(__file__).resolve().parent / "_tmp"
_DB_FILE = _TMP_DIR / "test.db"
if _DB_FILE.exists():
    _DB_FILE.unlink()

_TEST_DB_URL = f"sqlite:///{_DB_FILE}"
os.environ["DATABASE_URL"] = _TEST_DB_URL

engine = create_engine(
    _TEST_DB_URL,
    connect_args={"check_same_thread": False},
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
```

**Why a file, not `:memory:`?** In-memory SQLite breaks when `TestClient` shuts down (its lifespan calls `engine.dispose()` → next session sees a fresh empty DB). A temp file persists across connections, fixtures, and TestClient shutdowns.

### Problem 2: Don't need a real MLflow server
The routers call `mlflow_service.start_mlflow_run()` etc. — if MLflow is offline, the underlying `MlflowClient` **blocks on HTTP** and hangs the test forever. Solution: stub the whole module at conftest import time.

```python
class _NoopRun:
    def __enter__(self): return self
    def __exit__(self, *a): return False


class _MLflowStub:
    def start_mlflow_run(self, *a, **kw): return _NoopRun()
    def log_params(self, params): pass
    def log_metrics(self, metrics, step=None): pass
    def log_sklearn_model(self, model, artifact_path="model"):
        return f"runs:/{id(model)}/{artifact_path}"
    def end_mlflow_run(self, status="FINISHED"): pass
    def list_registered_models(self): return []
    def get_latest_model_version(self, name, stage="Production"): return None
    def load_model_by_uri(self, uri): raise RuntimeError("MLflow is stubbed in tests")
    def get_or_create_mlflow_experiment(self, name): return "0"


import backend.app.services.mlflow_service as mlflow_service_module
# Monkey-patch each function on the module
mlflow_service_module.start_mlflow_run = _MLflowStub().start_mlflow_run
mlflow_service_module.log_metrics = _MLflowStub().log_metrics
# ... etc
```

This works because routers access these as `mlflow_service.X(...)` — Python resolves the attribute **at call time**, so swapping the module attribute before the test runs catches every call site.

### Problem 3: Override the `get_db` FastAPI dependency
The app's `get_db` is wired to the production `SessionLocal`. We need tests to use `TestingSessionLocal` instead:

```python
def _override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


# In the client fixture:
app.dependency_overrides[get_db] = _override_get_db
```

This is the standard FastAPI testing pattern. The override is cleared in teardown so production code is never affected.

### Problem 4: Per-test isolation without recreating the schema
The `_create_tables` fixture (session-scoped) runs `Base.metadata.create_all(bind=engine)` **once** for the whole test run. The `db_session` fixture (function-scoped) **truncates all tables** before each test:

```python
@pytest.fixture()
def db_session():
    session = TestingSessionLocal()
    try:
        for table in reversed(Base.metadata.sorted_tables):
            session.execute(table.delete())
        session.commit()
        yield session
    finally:
        session.close()
```

Reverse iteration respects foreign keys (`runs` is deleted before `experiments`). Much faster than `drop_all` + `create_all` per test.

### Auth header convenience
Every authenticated endpoint needs `X-API-Key`. One fixture:

```python
@pytest.fixture()
def auth_headers():
    return {"X-API-Key": "test-key"}
```

---

## 🧪 The Test Files

### `test_auth.py` — 4 tests
- `test_health_is_open` — `/health` works without auth.
- `test_missing_api_key_returns_401` — any other endpoint returns 401 without the header.
- `test_valid_api_key_returns_200` — correct key gets through.
- `test_invalid_api_key_returns_401` — wrong key is rejected.

### `test_experiments.py` — 11 tests
- Create, list, get-by-id, update, delete.
- Pagination (`skip` + `limit`).
- Validation: empty name, name too long, duplicate name → 409.
- Soft-delete behavior (deleted experiments don't appear in list).

### `test_runs.py` — 14 tests
- Create run, list runs (filter by `experiment_id`), get-by-id.
- `log_metric` and `log_parameter` append to the JSON dict.
- `finish_run` transitions state and sets `end_time`.
- Filter by state (`FINISHED`, `RUNNING`, `FAILED`).
- Validation: unknown experiment → 404, missing required fields → 422.

### `test_predictions.py` — 5 tests
- Schema validation: missing `features` → 422, extra fields ignored, wrong types → 422.
- Service-level prediction: real estimator loaded from a registered model URI.

### `test_models.py` — 6 tests
- ORM invariants: `Experiment.name` is unique, `Run.experiment_id` FK is enforced, JSON columns round-trip correctly, `created_at` auto-populates.

### `test_prediction_service.py` — 7 tests
- Unit tests for the service layer (model loading, input preprocessing, error paths).

---

## 🔧 A Schema Fix: `RunResponse` JSON Validator

While running the test suite, 4 tests failed with:

```
pydantic_core._pydantic_core.ValidationError: Input should be a valid dictionary
```

The cause: the `Run` ORM model stores `metrics`, `parameters`, and `tags` as `Text` (JSON strings) in the DB, but `RunResponse` declares them as `Dict[str, Any]`. Pydantic can't auto-convert `str` → `dict` without help.

**Fix** in `backend/app/schemas/run.py`:

```python
from pydantic import field_validator
import json

class RunResponse(BaseModel):
    # ... other fields ...
    metrics: Optional[Dict[str, Any]] = None
    parameters: Optional[Dict[str, Any]] = None
    tags: Optional[Dict[str, Any]] = None

    @field_validator("metrics", "parameters", "tags", mode="before")
    @classmethod
    def _parse_json(cls, v):
        if v is None or v == "":
            return None
        if isinstance(v, (dict, list)):
            return v
        if isinstance(v, str):
            try:
                return json.loads(v)
            except json.JSONDecodeError:
                return None
        return v
```

`mode="before"` runs the validator **before** Pydantic's type check, so a string can be transparently converted to a dict. This is the right place for it — the DB column is `Text`, the API contract is `Dict`. The schema is the seam where the conversion belongs.

---

## 📊 Validation

```bash
$ python -m pytest tests/ -v
============================= test session starts ==============================
collected 47 items

tests/test_auth.py ....                                                  [  8%]
tests/test_experiments.py ...........                                    [ 31%]
tests/test_models.py ......                                              [ 44%]
tests/test_prediction_service.py .......                                 [ 59%]
tests/test_predictions.py .....                                          [ 70%]
tests/test_runs.py ..............                                        [100%]

============================= 47 passed, 1 warning in 1.05s =========================
```

One warning, non-blocking:

```
StarletteDeprecationWarning: Using `httpx` with `starlette.testclient` is deprecated; install `httpx2` instead.
```

This is just Starlette telling us to upgrade to a newer `httpx` shim. Not a test failure.

---

## 🧠 What We Learned

1. **In-memory SQLite is unreliable for FastAPI TestClient tests.** `TestClient.__exit__` calls `engine.dispose()`, which (with `StaticPool`) gives you a brand-new connection to a brand-new in-memory DB. File-based SQLite is the only stable choice.
2. **Module-level monkey-patching works for routers** because they look up `mlflow_service.X` at call time, not at import. Swapping module attributes before tests run catches every call site.
3. **JSON-as-text DB columns need a Pydantic `field_validator(mode="before")` on the response schema** — the ORM and the API contract can disagree, and the schema is the seam.
4. **Truncate, don't drop-and-recreate.** The schema is built once per session; each test just deletes all rows. Way faster, and tests are still isolated.
5. **Stub everything external.** If a router calls into MLflow, Postgres, S3, etc., the conftest needs a no-op replacement. Otherwise tests hang or fail with confusing connection errors.

---

## 📂 Files Touched

- `backend/tests/conftest.py` — created (new file).
- `backend/tests/pytest.ini` — created (asyncio + testpaths config).
- `backend/tests/test_auth.py` — created.
- `backend/tests/test_experiments.py` — created.
- `backend/tests/test_runs.py` — created.
- `backend/tests/test_predictions.py` — created.
- `backend/tests/test_models.py` — created.
- `backend/tests/test_prediction_service.py` — created.
- `backend/app/schemas/run.py` — modified (added `field_validator` to `RunResponse`).
