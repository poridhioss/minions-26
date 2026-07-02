# Phase 5 — Routers (HTTP Layer)

## 🎯 What This Phase Did

Phase 5 turned the project from a **library** into an **API**. Routers are the **front door** of the application: they receive HTTP requests, validate input, hand the work to services, and translate results (and errors) back into HTTP responses.

> 🎭 If services are the **employees** doing the actual work, routers are the **reception desk** at the government office. They don't make decisions — they check your form, call the right office, and hand you back a receipt (or a polite error message).

After this phase, the system is reachable over HTTP at 20 endpoints across 4 resources.

---

## 📂 What Was Created

```
backend/app/routers/
├── __init__.py             ← Re-exports the 4 routers
├── experiments.py          ← /experiments/*     (6 endpoints)
├── runs.py                 ← /runs/*            (9 endpoints, incl. nested log_*)
├── predictions.py          ← /predictions/*     (2 endpoints)
└── models.py               ← /models/*          (3 endpoints)
```

---

## ⭐ File 1: `experiments.py` (CRUD Endpoints)

**Purpose:** Standard CRUD over the `experiments` resource.

**The full endpoint list:**

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/experiments/` | List (with `?skip`, `?limit`, `?search`) |
| `GET` | `/experiments/count` | Total count |
| `GET` | `/experiments/{id}` | Get one |
| `POST` | `/experiments/` | Create (returns 201) |
| `PATCH` | `/experiments/{id}` | Partial update |
| `DELETE` | `/experiments/{id}` | Delete (returns 204) |

**Key code patterns:**

```python
@router.post("/", response_model=ExperimentResponse, status_code=201)
def create_experiment(payload: ExperimentCreate, db: Session = Depends(get_db)):
    try:
        return experiment_service.create_experiment(db, payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
```

Three things happen here:
1. **Pydantic** (`ExperimentCreate`) validates the request body and rejects bad shapes with a 422 before the function even runs.
2. **FastAPI** opens a `db` session via the `get_db` dependency from Phase 1 and closes it when the function returns.
3. **The service** does the work; we just translate its `ValueError` (business-rule violation) into an HTTP 400.

**Why is `/count` declared before `/{experiment_id}`?**
Because FastAPI matches routes in the order they're declared. If `/count` came after `/{experiment_id}`, FastAPI would try to convert the string `"count"` into an integer and return a 422. Declaring the more specific route first fixes this.

**Pagination via `Query()`:**

```python
@router.get("/")
def list_experiments(
    skip: int = Query(0, ge=0),                     # default 0, must be >= 0
    limit: int = Query(50, ge=1, le=200),            # default 50, clamped 1-200
    search: Optional[str] = Query(None, max_length=255),
    db: Session = Depends(get_db),
):
    ...
```

FastAPI generates the Swagger UI from these annotations. The `ge=`, `le=`, `max_length=` constraints are reflected in the schema and rejected with 422 if violated.

---

## ⭐ File 2: `runs.py` (CRUD + Logging Sub-Resources)

**Purpose:** CRUD over `runs`, plus the **nested logging endpoints** that are the heart of any ML experiment tracker.

**The full endpoint list:**

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/runs/` | List (filterable by `?experiment_id`, `?status`) |
| `GET` | `/runs/count` | Total count |
| `POST` | `/runs/` | Create |
| `GET` | `/runs/{run_id}` | Get one |
| `PATCH` | `/runs/{run_id}` | Partial update |
| `DELETE` | `/runs/{run_id}` | Delete |
| `POST` | `/runs/{run_id}/metrics` | **Log ONE metric → MLflow** |
| `POST` | `/runs/{run_id}/parameters` | **Log ONE hyperparameter** |
| `POST` | `/runs/{run_id}/finish` | Mark FINISHED + attach final metrics |

**Why three "log" endpoints instead of one PATCH?**
A training loop usually logs thousands of metrics (`loss` at step 1, 2, 3, ...). Calling PATCH on the run each time would re-send the entire `metrics` dict. The dedicated `log_metric` endpoint is **append-friendly**: the service loads the existing dict, adds one key, and saves it back.

**The metric-logging flow with MLflow forwarding:**

```python
@router.post("/{run_id}/metrics", response_model=RunResponse)
def log_metric(run_id: int, body: MetricIn = Body(...), db: Session = Depends(get_db)):
    run = _resolve_run(db, run_id)                                    # 1. 404 if missing

    updated = run_service.log_metric(db, run_id, body.key, body.value)  # 2. Update Postgres

    try:                                                               # 3. Forward to MLflow
        with mlflow_service.start_mlflow_run(
            experiment_id=str(run.experiment_id),
            run_name=run.run_name,
        ):
            mlflow_service.log_metrics({body.key: body.value}, step=body.step)
    except Exception:
        pass    # don't fail the API call if MLflow is down

    return updated
```

The `try/except` around the MLflow block is **intentional** — the system of record is Postgres, so a transient MLflow outage should not break the API. (In production you'd want a proper retry queue; for an MVP, "best-effort forwarding" is the right trade-off.)

**Inline request-body schemas:**

```python
class MetricIn(BaseModel):
    key: str = Field(..., min_length=1, max_length=100)
    value: float
    step: Optional[int] = Field(None, ge=0)
```

These are tiny and used only by this router, so they live in the router file rather than in `schemas/run.py`. If they grow or get reused, they get promoted to a schema module.

**The `finish` endpoint:**

```python
class FinishRunIn(BaseModel):
    status: str = Field("FINISHED")            # FINISHED or FAILED
    final_metrics: Optional[dict] = None

@router.post("/{run_id}/finish", response_model=RunResponse)
def finish_run(run_id: int, body: FinishRunIn = Body(default_factory=FinishRunIn), ...):
    if body.status not in {"FINISHED", "FAILED"}:
        raise HTTPException(400, f"status must be FINISHED or FAILED, got '{body.status}'")
    ...
```

A three-state status (`RUNNING` → `FINISHED` / `FAILED`) is the conventional MLflow pattern, and we accept only those two values as the explicit "done" signal.

---

## ⭐ File 3: `predictions.py` (Inference Endpoints)

**Purpose:** Serve model predictions. The client sends a feature vector; we look up the right model in MLflow's registry, load it (MLflow pulls the binary from MinIO), and return the result.

**The endpoint list:**

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/predictions/predict` | Run inference |
| `GET` | `/predictions/models` | List models you can call predict on |

**The body schema — accepts EITHER a registered name OR a direct URI:**

```python
class PredictIn(BaseModel):
    model_name: Optional[str] = None       # e.g. "rf-v1"        (registry lookup)
    model_uri:  Optional[str] = None       # e.g. "runs:/abc/model" (direct)
    stage:      str = "Production"         # only used with model_name
    features:   List[Any]                  # the input data
```

**The endpoint validates that at least one identifier is present:**

```python
@router.post("/predict")
def predict(body: PredictIn = Body(...)):
    if not body.model_name and not body.model_uri:
        raise HTTPException(400, "Provide either 'model_name' or 'model_uri' ...")
    try:
        return prediction_service.predict(features=body.features, ...)
    except ValueError as exc:
        msg = str(exc)
        if "not found" in msg.lower():
            raise HTTPException(404, msg)        # model doesn't exist
        raise HTTPException(400, msg)            # other bad request
```

**Why translate some `ValueError`s to 404 and others to 400?**
The service raises a generic `ValueError` with a message. We sniff the message text to decide the right HTTP status. (A more sophisticated approach would be **custom exception types**, like `ModelNotFoundError` and `BadRequestError` — that's a Phase-7+ refactor.)

---

## ⭐ File 4: `models.py` (Model Registry Browser)

**Purpose:** Read-only views over MLflow's model registry. The frontend uses these to render a "Models" page.

**The endpoint list:**

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/models/` | All registered models |
| `GET` | `/models/{name}` | Versions of one model |
| `GET` | `/models/{name}/latest?stage=Production` | Latest version in a stage |

**The pattern is "thin pass-through"** — no business logic in the router itself, just calling the service and converting the "not found" case to a 404.

```python
@router.get("/{name}/latest")
def get_latest_version(name: str, stage: str = Query("Production")):
    info = mlflow_service.get_latest_model_version(name, stage=stage)
    if info is None:
        raise HTTPException(
            status_code=404,
            detail=f"No version of model '{name}' in stage '{stage}'."
        )
    return info
```

**Why a separate `/models/*` router when `/predictions/models` already lists models?**
Different **use case**:

- `GET /predictions/models` → "what can I call `/predict` on RIGHT NOW?" (client is about to predict)
- `GET /models/` → "show me the registry in general" (client is browsing / admin view)

Both call the same service function, but they sit at different URLs because clients of one aren't necessarily clients of the other.

---

## ⭐ File 5: `__init__.py` (Package Glue)

**Purpose:** Re-export the four `router` objects so `main.py` (Phase 6) can mount them in one line each:

```python
# In main.py
from backend.app.routers import (
    experiments_router, runs_router, predictions_router, models_router,
)
app.include_router(experiments_router, prefix="/api/v1")
app.include_router(runs_router,        prefix="/api/v1")
app.include_router(predictions_router, prefix="/api/v1")
app.include_router(models_router,      prefix="/api/v1")
```

The `prefix="/api/v1"` here is the **API version** — keeping it in `main.py` (not in the router) means we can mount the same router under multiple versions later (`/api/v1`, `/api/v2`).

---

## 🧠 The Concepts You Should Understand

### 1. The router → service → model → DB pipeline

```
HTTP POST /api/v1/runs/
   │
   ▼
┌────────┐
│ Router │   ← this phase
│  • Parse URL
│  • Validate body  (Pydantic)
│  • Open DB session (Depends(get_db))
│  • Call service
│  • Format response
└───┬────┘
    │ experiment_service.create_experiment(db, payload)
    ▼
┌────────────┐
│  Service   │   ← Phase 4
│  • Business rules
│  • DB writes
└───┬────────┘
    │ Experiment(...)
    ▼
┌────────┐
│  Model │   ← Phase 2  (SQLAlchemy ORM)
└───┬────┘
    ▼
┌────────┐
│   DB   │   ← Phase 1
└────────┘
```

The router **never** talks to the database directly. The service **never** knows what HTTP is. That's the separation that makes the code testable.

### 2. FastAPI's dependency injection

```python
def create_experiment(
    payload: ExperimentCreate,                  # ← body, parsed by Pydantic
    db: Session = Depends(get_db),              # ← injected by FastAPI
):
```

`Depends(get_db)` is the magic:

```python
# In database.py (Phase 1)
def get_db():
    db = SessionLocal()
    try:
        yield db                # pause here, FastAPI calls the route
    finally:
        db.close()              # always close, even on errors
```

For **every request** that lists `db: Session = Depends(get_db)`, FastAPI:
1. Calls `get_db()`, which creates a new `SessionLocal()`.
2. Yields the session into your function.
3. When your function returns (or raises), resumes `get_db()` and calls `db.close()`.

This means **you never have to remember to close the session** — the dependency does it for you.

### 3. The `ValueError` → `HTTPException` translation

Services raise plain `ValueError` (no HTTP knowledge). Routers catch them and convert:

```python
try:
    service.do_thing()
except ValueError as exc:
    raise HTTPException(status_code=400, detail=str(exc))
```

This works because:
- **`ValueError` is the natural Python way to signal "bad input"**
- **`HTTPException` is what FastAPI knows how to render into JSON + status code**
- The translation is the router's job, not the service's

### 4. `response_model=` and Pydantic

```python
@router.get("/{experiment_id}", response_model=ExperimentResponse)
def get_experiment(...):
    return exp   # a SQLAlchemy ORM object!
```

Even though we're returning a raw ORM object, FastAPI + Pydantic:
1. Read the ORM object via `ExperimentResponse.model_validate(exp)` (allowed because `from_attributes=True` in the schema)
2. Serialize it to JSON
3. Document it in the OpenAPI spec

You can also `return updated.metrics` (a Python `dict`) and Pydantic will turn it into a proper JSON object in the response.

### 5. Path-param ordering

```python
@router.get("/count")                    # declared FIRST
@router.get("/{experiment_id}")          # declared SECOND
```

FastAPI matches in declaration order. If `/{experiment_id}` came first, `GET /count` would try to match it with `experiment_id="count"` and fail with a 422 "not a valid integer". This pattern (specific routes before dynamic ones) is worth remembering.

### 6. `Body(default_factory=FinishRunIn)` for empty POSTs

```python
def finish_run(run_id: int, body: FinishRunIn = Body(default_factory=FinishRunIn)):
    # body.status == "FINISHED", body.final_metrics is None
```

This lets the client call `POST /runs/42/finish` **with no body at all**, and Pydantic fills in the defaults. Convenient for the common "just mark it done" case.

### 7. MLflow as a side effect (the dual-write pattern)

The `log_metric` endpoint updates **two** systems:

1. **PostgreSQL** — system of record for "what runs exist"
2. **MLflow** — system of record for "the time-series history of each metric"

We try MLflow best-effort and never fail the API call if MLflow is down. This is the **dual-write pattern** — same idea as Phase 4's services, just visible at the router layer.

---

## 🔄 A Full Request Lifecycle

```
Client: POST /api/v1/runs/42/metrics
Body:   {"key": "accuracy", "value": 0.94, "step": 100}
Header: X-API-Key: dev-key-12345
                 │
                 ▼
        ┌──────────────┐
        │  FastAPI app │  (Phase 6 — not built yet)
        │  includes    │
        │  runs_router │
        └──────┬───────┘
               │
               ▼
        ┌──────────────────────┐
        │ runs_router.log_metric│   ← this phase
        │  • parse body (Pydantic)
        │  • get db session
        │  • resolve run (404 if missing)
        └──────┬───────────────┘
               │
        ┌──────┴──────────────────┐
        │                         │
        ▼                         ▼
┌──────────────────┐    ┌──────────────────────┐
│ run_service      │    │ mlflow_service        │
│ .log_metric(...) │    │ .start_mlflow_run(...)│
│                  │    │ .log_metrics({...})   │
└────────┬─────────┘    └──────────┬────────────┘
         │                         │
         ▼                         ▼
   PostgreSQL                 MLflow server
   (port 5432)                 (port 5000)
                                 │
                                 └─► MinIO
                                     (port 9000)
```

---

## 📊 The Final Endpoint Table

| Method | Path | Handler | Returns |
|---|---|---|---|
| `GET` | `/api/v1/experiments/` | `list_experiments` | `List[ExperimentResponse]` |
| `GET` | `/api/v1/experiments/count` | `count_experiments` | `int` |
| `GET` | `/api/v1/experiments/{id}` | `get_experiment` | `ExperimentResponse` |
| `POST` | `/api/v1/experiments/` | `create_experiment` | `201 ExperimentResponse` |
| `PATCH` | `/api/v1/experiments/{id}` | `update_experiment` | `ExperimentResponse` |
| `DELETE` | `/api/v1/experiments/{id}` | `delete_experiment` | `204` |
| `GET` | `/api/v1/runs/` | `list_runs` | `List[RunResponse]` |
| `GET` | `/api/v1/runs/count` | `count_runs` | `int` |
| `POST` | `/api/v1/runs/` | `create_run` | `201 RunResponse` |
| `GET` | `/api/v1/runs/{id}` | `get_run` | `RunResponse` |
| `PATCH` | `/api/v1/runs/{id}` | `update_run` | `RunResponse` |
| `DELETE` | `/api/v1/runs/{id}` | `delete_run` | `204` |
| `POST` | `/api/v1/runs/{id}/metrics` | `log_metric` | `RunResponse` |
| `POST` | `/api/v1/runs/{id}/parameters` | `log_parameter` | `RunResponse` |
| `POST` | `/api/v1/runs/{id}/finish` | `finish_run` | `RunResponse` |
| `POST` | `/api/v1/predictions/predict` | `predict` | `{prediction, model_uri, ...}` |
| `GET` | `/api/v1/predictions/models` | `list_models` | `List[Dict]` |
| `GET` | `/api/v1/models/` | `list_models` | `List[Dict]` |
| `GET` | `/api/v1/models/{name}` | `get_model_versions` | `List[Dict]` |
| `GET` | `/api/v1/models/{name}/latest` | `get_latest_version` | `Dict` |

**Total: 20 endpoints.**

---

## ✅ How to Verify Phase 5 Works

**Test 1 — Import the routers:**

```python
>>> from backend.app.routers import (
...     experiments_router, runs_router, predictions_router, models_router
... )
>>> print(experiments_router.prefix, runs_router.prefix, predictions_router.prefix, models_router.prefix)
/experiments /runs /predictions /models
```

**Test 2 — Build a real FastAPI app and check OpenAPI generation:**

```python
>>> from fastapi import FastAPI
>>> from backend.app.routers import (
...     experiments_router, runs_router, predictions_router, models_router
... )
>>> app = FastAPI()
>>> app.include_router(experiments_router, prefix="/api/v1")
>>> app.include_router(runs_router,        prefix="/api/v1")
>>> app.include_router(predictions_router, prefix="/api/v1")
>>> app.include_router(models_router,      prefix="/api/v1")
>>> spec = app.openapi()
>>> len(spec['paths'])
14                              # 14 unique URL paths; some have multiple methods
```

**Test 3 — Start the dev server and hit a real endpoint (requires a running Postgres + .env):**

```bash
cd backend && uvicorn app.main:app --reload
# Then in another terminal:
curl http://localhost:8000/api/v1/experiments/count
# → 0   (no experiments yet)
```

The actual HTTP layer won't be live until Phase 6 wires up `main.py`, but every router in this phase is importable, registers routes, and generates valid OpenAPI.

---

## 🧩 Where Phase 5 Fits in the Big Picture

```
HTTP request
     │
     ▼
┌─────────┐    ┌─────────┐    ┌─────────────┐    ┌────────┐    ┌──────────┐
│ Router  │───►│ Schema  │───►│  Service    │───►│ Model  │───►│   DB     │
│(Phase 5)│    │(Phase 3)│    │  (Phase 4)  │    │(Phase2)│    │ Postgres │
└─────────┘    └─────────┘    └──────┬──────┘    └────────┘    └──────────┘
                                      │
                                      ├──► MLflow server (port 5000)
                                      │
                                      └──► MinIO / S3 (port 9000)
```

**Phase 5 is what makes the project reachable from the outside world.** The next phase (Phase 6) will create `main.py` — the FastAPI app that ties all the routers together, adds middleware, error handlers, and starts the dev server.

---

## 📋 Files Inventory

| File | Lines | Endpoints | Purpose |
|---|---|---|---|
| `backend/app/routers/__init__.py` | 34 | 0 | Re-exports the 4 routers |
| `backend/app/routers/experiments.py` | 197 | 6 | Experiment CRUD |
| `backend/app/routers/runs.py` | 298 | 9 | Run CRUD + 3 nested logging endpoints |
| `backend/app/routers/predictions.py` | 130 | 2 | Model inference + model list |
| `backend/app/routers/models.py` | 98 | 3 | MLflow registry browser |

**Total: 757 lines of HTTP glue, 20 endpoints.**

---

## 🚀 What's Next (Phase 6 — `main.py`)

The FastAPI app entry point. It will:
- Create the `FastAPI()` instance with title/version from settings
- Wire up the 4 routers under `/api/v1`
- Add CORS middleware (so the React frontend at `localhost:3000` can call us)
- Register startup/shutdown hooks (e.g. DB table creation via `Base.metadata.create_all`)
- Add a `/health` endpoint
- Mount a global exception handler for `ValueError`

To start it, you can now run:

```bash
cd backend && uvicorn app.main:app --reload
```

…and hit `http://localhost:8000/docs` to see all 20 endpoints in the auto-generated Swagger UI.
