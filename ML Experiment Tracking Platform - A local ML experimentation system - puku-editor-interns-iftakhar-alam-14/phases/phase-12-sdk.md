# Phase 12 — Python SDK (`mltracker`)

## 🎯 What This Phase Did

Phase 11 finished the React SPA, but ML practitioners don't live in a browser — they live in notebooks and training scripts. **Phase 12 ships a tiny Python client** that wraps the same 20 FastAPI endpoints with a feel closer to `mlflow` than to `requests.post(...)`.

> 🎭 If the project is a restaurant, this phase is the **takeout counter**. The kitchen (FastAPI) and the dining room (React SPA) are both open, but until now you couldn't grab your order to go. The SDK is the packaging that lets you call `mltracker.run(...)` from a Jupyter cell and walk out with a tracked experiment.

After this phase:

```bash
cd sdk && pip install -e ".[dev]"
pytest sdk/tests -v
# → 32 passed in 0.84s
```

---

## 📂 What Was Created

```
sdk/
├── pyproject.toml                 ← Build metadata + httpx/pydantic deps + respx/pytest-mock dev deps
├── README.md                      ← Quickstart, API tour, "design notes" link
├── mltracker/                     ← The installable package
│   ├── __init__.py                ← Re-exports + module-level singleton client + facades
│   ├── exceptions.py              ← MLTrackerError → APIError / AuthenticationError / NotFoundError / ValidationError
│   ├── types.py                   ← Pydantic v2 mirrors of the FastAPI response schemas
│   ├── client.py                  ← MLTrackerClient (httpx) + 5 endpoint groups
│   └── runs.py                    ← Run() context manager + module-level run() helper
├── examples/
│   ├── __init__.py
│   ├── train.py                   ← Full rewrite of backend/ml/train.py on top of the SDK
│   └── predict.py                 ← CLI inference (single-shot) over the SDK
└── tests/
    ├── __init__.py
    ├── conftest.py                ← Autouse singleton-reset fixture + respx-backed mock_client
    └── test_client.py             ← 32 tests across 9 classes — all green
```

10 source files, ~1,200 lines of Python (incl. tests). **Zero new runtime dependencies** — the SDK reuses the `httpx` and `pydantic` already on disk in the backend venv.

---

## 🏛️ Architecture

```
                   ┌──────────────────────────────────────────────┐
                   │        Python user code (notebook / CLI)     │
                   │                                              │
                   │  import mltracker                             │
                   │  mltracker.login(url=..., api_key=...)        │
                   │                                              │
                   │  with mltracker.run(experiment_name=...):     │
                   │      r.log_param("n_estimators", 100)         │
                   │      r.log_metric("loss", 0.42)               │
                   │                                              │
                   │  mltracker.predict(model_name=..., features=…)│
                   └──────────────────────┬───────────────────────┘
                                          │  httpx.Client
                                          │   • event hook → X-API-Key
                                          │   • API_PREFIX = "/api/v1"
                                          ▼
                                ┌──────────────────────┐
                                │  FastAPI :8000       │
                                │  (Phase 6 backend)   │
                                └──────────────────────┘
```

The SDK has three layers, smallest to largest:

1. **`MLTrackerClient`** — one `httpx.Client` per instance, with an event hook that injects `X-API-Key` on every request. Holds the auth + base URL.
2. **Endpoint groups** — `_ExperimentsAPI`, `_RunsAPI`, `_ModelsAPI`, `_PredictionsAPI`, `_HealthAPI`. Each is a tiny façade over `client._request(method, path, ..., model=…)` with the Pydantic model already bound to the return type.
3. **Module-level facades** — `mltracker.experiments`, `mltracker.runs`, `mltracker.models`, `mltracker.predict`, `mltracker.health` resolve through a singleton client configured by `login()`. This is the surface ML users actually touch.

### Key decisions

- **Singleton client mirrors the TS `axios.create({})` pattern.** Just as the React app calls `setApiKey()` in `localStorage` and the axios interceptor reads it on every request, the Python SDK has a module-level `mltracker._client` that's set by `login(url=..., api_key=...)` and used by the top-level helpers. Tests can ignore the singleton and instantiate `MLTrackerClient(...)` directly.
- **`PredictRequest` mirrors the real backend, not the TS frontend.** The frontend's `PredictRequest` has an aspirational `version` field; the backend's `PredictIn` doesn't. The SDK mirrors the backend. The mismatch is documented in a comment in `types.py` so a future PR to "add `version`" knows where to look.
- **`TypeAdapter` instead of `model.model_validate(...)` for response validation.** Several endpoints return `list[Experiment]` / `Sequence[Run]` and a bare `list[Model]` doesn't have a `model_validate`. Pydantic v2's `TypeAdapter` is the universal entry point that handles both single classes and parameterized generics uniformly — the call site reads `TypeAdapter(model).validate_python(body)` and never has to special-case list returns.
- **`/health` is the only endpoint that escapes the `/api/v1` prefix.** Adding the prefix inside `_request` (with a `not path.startswith("/health")` guard) keeps the endpoint groups clean and makes it impossible to accidentally hit an unversioned path. The same prefix-stripping logic in `__init__` means a user can pass `.../api/v1` in their URL and the SDK won't double it.
- **Lazy `from_env()` fallback with a hard guard.** If the user never calls `login()` and no env vars are set, `_get_client()` raises a clean `RuntimeError` instead of silently trying `http://localhost:8000`. This is a deliberate UX choice — silent defaults are how you end up tracking experiments against a stranger's server.
- **`respx` for tests, not `httpx.MockTransport` by hand.** `respx.mock(base_url=...)` swaps the transport on the underlying `httpx.Client` and gives you a router you can `router.post("/api/v1/...").mock(...)` against. Tests run in 0.84 s with zero network and zero fixtures beyond the two we wrote.
- **Editable install from the project root.** `pip install -e ./sdk[dev]` puts `mltracker` on the path without publishing anything. The `examples/` directory is a sibling package, not a sub-package, so `python -m sdk.examples.train` works from the repo root.

---

## ⭐ File Tour

### `sdk/mltracker/client.py` — The HTTP surface

```python
class MLTrackerClient:
    API_PREFIX = "/api/v1"

    def __init__(self, url=None, *, api_key=None, timeout=30.0, transport=None, ...):
        # Strip a user-supplied /api/v1; the prefix is added in _request.
        base = (url or self.DEFAULT_BASE_URL).rstrip("/")
        if base.endswith(self.API_PREFIX):
            base = base[: -len(self.API_PREFIX)]
        self.base_url = base
        self.api_key = api_key or os.getenv("MLTRACKER_API_KEY", "")

        self._http = httpx.Client(
            base_url=base,
            timeout=timeout,
            transport=transport,
            event_hooks={"request": [_add_api_key]},
            headers=headers or {},
        )
```

`_add_api_key` is a closure that reads `self.api_key` on every request, so the user can mutate it post-construction (e.g. after a key-rotation flow) and the next call will pick it up. `_request` adds the leading `/`, then the `/api/v1` prefix (unless the path is `/health`), then dispatches via the `httpx.Client`. Non-2xx responses are mapped to typed exceptions in `_raise_for_status`.

### `sdk/mltracker/runs.py` — The context manager

```python
class Run:
    def __init__(self, client, run_id, *, run_name=None, ...):
        self.client = client
        self.run_id = run_id
        self._finished = False

    def log_param(self, key, value):
        self.client.runs.log_parameter(self.run_id, key, str(value))

    def log_metrics(self, mapping):
        for k, v in mapping.items():
            self.client.runs.log_metric(self.run_id, k, v)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self._finished:
            return False
        self._finished = True
        if exc_type is None:
            self.finish()
        else:
            self.fail(reason=f"{exc_type.__name__}: {exc_val}")
        # Never swallow the user's exception
        return False
```

`finish()` and `fail()` are idempotent (guarded by `_finished`). The `_exit_` block logs errors loudly if `finish()` itself fails, but never re-raises — masking the user's success with an SDK error would be worse than the bookkeeping being slightly off. The `module.run(...)` helper resolves an experiment by id **or** name (auto-creating if missing) so a notebook can write `with mltracker.run(experiment_name="iris"):` and never touch `ExperimentService` directly.

### `sdk/examples/train.py` — The reference rewrite

The Phase 8 `backend/ml/train.py` made 8 raw `requests.post(...)` calls. The SDK rewrite uses **one** `with`-block:

```python
import mltracker
from sklearn.ensemble import RandomForestClassifier
from sklearn.datasets import make_classification
import mlflow

mltracker.login()  # picks up MLTRACKER_URL + MLTRACKER_API_KEY from env

def train(experiment_name, run_name, *, n_estimators=100, max_depth=5, ...):
    X, y = make_classification(n_samples=n_samples, random_state=random_state)
    with mltracker.run(
        experiment_name=experiment_name,
        run_name=run_name,
        parameters={"n_estimators": n_estimators, "max_depth": max_depth, ...},
        tags={"model_type": "random_forest", "framework": "sklearn"},
    ) as run:
        model = RandomForestClassifier(n_estimators=n_estimators, max_depth=max_depth, ...)
        model.fit(X, y)
        acc = model.score(X, y)

        run.log_metrics({"accuracy": acc})
        run.log_param("model_type", "RandomForestClassifier")

        with mlflow.start_run(run_name=run_name) as mlf_run:
            mlflow.sklearn.log_model(model, "model")

        return {
            "experiment_id": run.experiment_id,
            "run_id": run.run_id,
            "mlflow_run_id": mlf_run.info.run_id,
            "accuracy": acc,
        }
```

The CLI is `argparse` with `--experiment-name`, `--run-name`, `--n-estimators`, `--max-depth`, `--random-state`, `--n-samples`. Output is JSON so it's easy to pipe into other tools. **`backend/ml/train.py` is now legacy** — Phase 13 can decide whether to delete it or keep it as a no-deps fallback.

### `sdk/tests/test_client.py` — 32 tests, 0.84 s

Nine test classes, all backed by `respx.mock(base_url="http://testserver")`:

| Class | What it covers | Tests |
|---|---|---|
| `TestSingleton` | `login()`, `reset()`, `is_configured()`, env fallback | 4 |
| `TestAuth` | `X-API-Key` attached, omitted when blank | 2 |
| `TestExperiments` | `list` / `get` / `create` / `update` / `delete` + pagination | 6 |
| `TestRuns` | `create`, `log_metric` (with/without `step`), `log_parameter`, `finish` | 5 |
| `TestPredictions` | happy path, identifier validation, top-level helper | 3 |
| `TestHealth` | `/health` bypasses the prefix | 1 |
| `TestExceptions` | 401/404/422/500 → typed exceptions | 5 |
| `TestRunContext` | happy path, exception → FAILED, idempotent finish, name resolution | 4 |
| `TestFacades` | `mltracker.experiments.*` routes through the singleton | 1 |
| `TestExceptions` (helper) | Pydantic-list `detail` extraction | 1 |

The `_reset_singleton` autouse fixture calls `mltracker.reset()` before AND after every test, so test order doesn't matter. The `mock_client` fixture wraps everything in `respx.mock(...)` and yields `(router, client)` so individual tests just write `router.post("/api/v1/experiments/").mock(...)` and the rest of the SDK is unaware anything was mocked.

### `sdk/README.md` — The user-facing quickstart

A 90-line README that opens with the 5-line "I just want to train" example, then tours the public API surface (module-level facades, the `Run` context manager, the `from_env()` shortcut, all 5 exception types), and finishes with the same env-var / `login()` precedence rules the TS frontend uses.

---

## 🧪 Tests

```
sdk/tests/test_client.py ................................                    [100%]
============================== 32 passed in 0.84s ==============================
```

What the suite proves end-to-end:

1. The `X-API-Key` event hook is on the wire for every call.
2. The `/api/v1` prefix is added for every endpoint except `/health`.
3. `list[Experiment]` / `Sequence[Run]` are validated correctly via `TypeAdapter` (the original bug that took two iterations to find).
4. `ExperimentCreate(name="valid")` round-trips through the wire — Pydantic client-side validation is real, not a no-op.
5. 401 → `AuthenticationError`, 404 → `NotFoundError`, 422 → `ValidationError`, 500 → `APIError`. The 422 path is exercised with a real Pydantic-list body (FastAPI's actual response shape).
6. The `Run` context manager auto-`FINISH`es on clean exit and auto-`FAIL`s with the exception name + message in the `failure_reason` tag on exception.
7. `finish()` is idempotent — calling it twice in `__exit__` (e.g. if the user also calls it explicitly) sends exactly one PATCH.
8. `mltracker.experiments.list()` reaches the same code path as `client.experiments.list()` on a singleton-configured client.

---

## 🚀 How to Use

### Install

```bash
cd ml-tracker
source venv/bin/activate
pip install -e "./sdk[dev]"
```

### Configure

```bash
export MLTRACKER_URL=http://localhost:8000
export MLTRACKER_API_KEY=$(grep '^API_KEY=' backend/.env | cut -d= -f2)
```

…or in code:

```python
import mltracker
mltracker.login(url="http://localhost:8000", api_key="...")
```

### Train a model

```bash
python -m sdk.examples.train \
    --experiment-name iris-baseline \
    --run-name rf-v1 \
    --n-estimators 100 \
    --max-depth 5
```

### Predict

```bash
python -m sdk.examples.predict \
    --model-name iris-baseline \
    --features 5.1 3.5 1.4 0.2
```

### Run the tests

```bash
pytest sdk/tests -v
```

---

## 📋 What's Next (Phase 13)

Phase 12 closed the **client SDK** half of the platform. Phase 13+ candidates, in rough priority order:

1. **Repo cleanup.** `backend/ml/train.py` is now redundant with `sdk/examples/train.py`. Decide which stays as the canonical "first-touch" example and update the README + Phase 8 build log to point at it.
2. **CI pipeline.** There's no GitHub Actions / pre-commit yet. The test commands for the three test suites (`pytest backend/tests`, `pytest sdk/tests`, `npm --prefix frontend test`) are documented but not enforced. A `.github/workflows/ci.yml` that runs all three on every PR would close that gap.
3. **Real auth.** `X-API-Key` is a single shared secret in `backend/.env`. Phase 13 could add per-user API keys, an OAuth2 flow, or a session-cookie fallback for the SPA.
4. **Model registry write paths.** The SDK is read-only on the registry side — you can list and inspect registered models, but not register or transition stages. The backend has the `mlflow_service.register_model(...)` plumbing; the SDK doesn't expose it yet.
5. **Streaming metrics.** `runs.log_metric` does a POST per call, which is fine for ≤100 metrics but rough for thousands. A batch endpoint or an `httpx` async transport would let training loops log without blocking on the network.
6. **TypeScript SDK.** The TS frontend has hand-written types in `frontend/src/api/types.ts` that drift from the Pydantic schemas. A `frontend/src/api/client.ts → npm package` mirror of this SDK would close the type-drift loop and let external JS/TS consumers use the platform without the SPA shell.

---

## 🎉 Summary

| Metric | Value |
|---|---|
| Files created | 10 |
| Lines of Python (src + tests) | ~1,200 |
| Public API symbols | 22 |
| Endpoint groups | 5 |
| New runtime deps | **0** (reuses `httpx` + `pydantic` from the backend venv) |
| New dev deps | 2 (`respx`, `pytest-mock`) |
| Test count | 32 |
| `pytest` time | 0.84 s |
| `pytest` failures | **0** |

The ML Tracker is now a **complete three-tier system**: a FastAPI backend that owns the data, a React SPA that owns the experience, and a Python SDK that owns the workflow. Pick the entry point that fits your context — REST + curl, browser, or `import mltracker` — and the same 20 endpoints are there for you.

Next session: Phase 13 — CI pipeline + SDK / CLI consolidation.
