# Phase 4 — Services (Business Logic)

## 🎯 What This Phase Did

Phase 4 created the **business logic layer** — the "brain" of the application. Services are pure Python functions that orchestrate the database, MLflow, and MinIO to do the actual work that the API endpoints will trigger.

> 🧠 If schemas are the **forms** at the government office, and models are the **filing cabinets**, services are the **employees** who take your form, look up the right cabinet, file it, and hand you back a receipt.

---

## 📂 What Was Created

```
backend/app/services/
├── __init__.py
├── experiment_service.py    ← CRUD + rules for experiments
├── run_service.py           ← CRUD + log metrics/params
├── mlflow_service.py        ← Bridge to MLflow server
└── prediction_service.py    ← Load model + run inference
```

> The `__init__.py` was left empty in this phase. You can choose to re-export functions from it later, but keeping it empty is also fine — callers import the specific module: `from backend.app.services import experiment_service`.

---

## ⭐ File 1: `experiment_service.py` (CRUD + Business Rules)

**Purpose:** Create, read, update, delete experiments, with the rule that names must be unique and you can't delete an experiment that has runs.

Key functions:

```python
def create_experiment(db: Session, payload: ExperimentCreate) -> Experiment:
    """Insert a new experiment. Raises 400 if the name is already taken."""
    if get_experiment_by_name(db, payload.name):
        raise HTTPException(status_code=400, detail=f"Experiment '{payload.name}' already exists")
    exp = Experiment(name=payload.name, description=payload.description, tags=payload.tags)
    db.add(exp); db.commit(); db.refresh(exp)
    return exp


def list_experiments(db: Session, skip: int = 0, limit: int = 50, search: str | None = None):
    """List experiments with pagination and optional name search."""
    q = db.query(Experiment)
    if search:
        q = q.filter(Experiment.name.ilike(f"%{search}%"))
    return q.order_by(Experiment.created_at.desc()).offset(skip).limit(limit).all()


def delete_experiment(db: Session, experiment_id: int) -> None:
    """Delete an experiment, but only if it has no runs."""
    exp = get_experiment(db, experiment_id)  # raises 404 if not found
    if exp.runs:
        raise HTTPException(status_code=400, detail="Cannot delete experiment with existing runs")
    db.delete(exp); db.commit()
```

**Other functions:** `get_experiment`, `get_experiment_by_name`, `count_experiments`, `update_experiment`.

**Business rules enforced here:**
- Names must be unique across experiments
- Can't delete an experiment that still has runs (so you must delete runs first)

---

## ⭐ File 2: `run_service.py` (CRUD + Logging)

**Purpose:** Manage runs and the special "log metric / log parameter" operations that are the heart of ML experiment tracking.

Key features:

```python
# ─── JSON ↔ Text helpers (the column is Text, but clients send Dict) ───
def _dump_json(d: dict | None) -> str | None:
    return json.dumps(d) if d else None

def _load_json(s: str | None) -> dict | None:
    return json.loads(s) if s else None
```

These helpers convert between the Python `dict` that the client sends and the **JSON string** we store in the `Text` column. So clients send nice nested dicts, but the database just sees a string.

```python
def log_metric(db: Session, run_id: int, key: str, value: float, step: int | None = None):
    """Append (or update) one metric in a run's metrics dict."""
    run = get_run(db, run_id)  # raises 404 if missing
    metrics = _load_json(run.metrics) or {}
    metrics[key] = value
    run.metrics = _dump_json(metrics)
    db.commit()
    # Phase 4 also forwards to MLflow for time-series history
    mlflow_service.log_metrics(run_id, {key: value}, step=step)
```

**Other functions:** `create_run`, `get_run`, `list_runs`, `count_runs`, `update_run`, `finish_run`, `delete_run`, `log_parameter`, `run_to_dict`.

**Why `payload.model_dump(exclude_unset=True)` in updates?**
This Pydantic feature sends **only the fields the client actually set**, ignoring the ones they didn't. So `PATCH /runs/1` with `{"status": "FINISHED"}` won't accidentally wipe out the metrics field.

---

## ⭐ File 3: `mlflow_service.py` (Bridge to MLflow)

**Purpose:** Talk to the MLflow tracking server so we get all the nice ML-specific features (parameter comparison charts, metric history plots, model registry, model versioning) for free.

```python
import mlflow
from backend.app.core.config import settings

# Tell the mlflow library where the tracking server lives
mlflow.set_tracking_uri(settings.MLFLOW_TRACKING_URI)


def get_or_create_mlflow_experiment(name: str) -> str:
    """Mirror our experiment in MLflow; return the experiment_id."""
    exp = mlflow.get_experiment_by_name(name)
    if exp is None:
        exp_id = mlflow.create_experiment(name)
    else:
        exp_id = exp.experiment_id
    return exp_id


@contextmanager
def start_mlflow_run(experiment_id: str, run_name: str | None = None):
    """Context manager: yields an mlflow run, ensures it always ends."""
    run = mlflow.start_run(experiment_id=experiment_id, run_name=run_name)
    try:
        yield run
    finally:
        mlflow.end_run()
```

**Other functions:** `log_params`, `log_metrics`, `log_sklearn_model` (auto-logs a scikit-learn model to MLflow + MinIO), `end_mlflow_run`, `list_registered_models`, `get_latest_model_version`, `load_model_by_uri`.

**Why a context manager for `start_mlflow_run`?**
If training crashes mid-way, `mlflow.end_run()` still gets called — no orphan runs left in MLflow's UI.

---

## ⭐ File 4: `prediction_service.py` (Inference)

**Purpose:** Load a trained model from storage and run inference on new data. This is the **"serving"** part of the platform.

```python
def predict(features: list, model_name: str | None = None, model_uri: str | None = None):
    """Either look up the latest production model by name, or use a direct URI."""
    if model_uri is None:
        if model_name is None:
            raise HTTPException(400, "Provide either model_name or model_uri")
        model_uri = mlflow_service.get_latest_model_uri(model_name)

    # mlflow.pyfunc loads the model + handles preprocessing
    model = mlflow.pyfunc.load_model(model_uri)
    prediction = model.predict([features])
    return {"prediction": prediction.tolist()[0], "model_uri": model_uri}
```

**Other functions:** `_resolve_model_uri`, `list_available_models`.

**Pattern:** Accepts **either** `model_name` (looks up the latest version in MLflow's registry) **or** `model_uri` (direct path like `runs:/abc123/model`). This gives flexibility for both production and debugging.

---

## 🧠 The Concepts You Should Understand

### 1. Why a separate service layer?

You **could** put all logic inside the router function. But that makes the code:
- ❌ Hard to test (you'd need a running HTTP server to test business logic)
- ❌ Hard to reuse (the same logic called from CLI, SDK, or background job would need to be copy-pasted)
- ❌ Hard to read (router files would become huge)

By separating it:
- ✅ Services are **plain Python functions** that take a `db` session and return data
- ✅ Routers become thin: just parse input → call service → format output
- ✅ You can test services with a unit test that creates a test DB, calls `create_experiment(...)`, and checks the result

### 2. The Session pattern

Every service function takes a `db: Session` as its **first argument**. The router gets this from FastAPI's dependency injection:

```python
# In the router (Phase 5)
@router.post("/experiments")
def create(payload: ExperimentCreate, db: Session = Depends(get_db)):
    return experiment_service.create_experiment(db, payload)

# In the service (Phase 4)
def create_experiment(db: Session, payload):
    db.add(...)
    db.commit()
```

The session is created by `get_db()` in Phase 1, used by the service, and closed when the request finishes.

### 3. The `HTTPException` pattern

Services raise `HTTPException` instead of returning error codes. The router doesn't need to check `if error: ...` — FastAPI's exception handler converts the exception into a proper HTTP response.

```python
# Service raises
raise HTTPException(status_code=404, detail="Run not found")

# FastAPI automatically sends:
# HTTP/1.1 404 Not Found
# {"detail": "Run not found"}
```

### 4. `model_dump(exclude_unset=True)`

This Pydantic feature means "give me a dict, but **only** the fields the client actually set". So this `PATCH` request:

```json
{"status": "FINISHED"}
```

becomes this Python dict:
```python
{"status": "FINISHED"}
```

NOT:
```python
{"run_name": None, "status": "FINISHED", "end_time": None, ...}  # all the unset fields
```

This is critical for partial updates — you don't want to wipe out fields the client didn't intend to change.

### 5. MLflow as a side effect

`run_service.log_metric` does **two things**:
1. Updates our PostgreSQL row (system of record)
2. Forwards to MLflow (specialized ML tracking with time-series history)

This is the **dual-write** pattern. PostgreSQL is the source of truth for "what runs exist"; MLflow is the source of truth for "the metric history of each run".

---

## 🔄 Services in the Request Lifecycle

```
HTTP POST /api/v1/runs/42/metrics
body: {"key": "accuracy", "value": 0.94, "step": 100}
        │
        ▼
   ┌────────┐
   │ Router │  (Phase 5)
   └───┬────┘
       │ db: Session = Depends(get_db)
       │ payload = MetricIn(...)
       ▼
   ┌──────────────────────┐
   │  run_service         │   (Phase 4 — this phase)
   │  .log_metric(...)    │
   └────┬───────────┬─────┘
        │           │
        │           └────► mlflow_service.log_metrics(...)
        │                    │
        │                    └─► MLflow server (port 5000)
        │
        └──────────► db.commit()
                     │
                     └─► PostgreSQL (port 5432)
```

---

## ✅ How to Verify Phase 4 Works

```python
>>> from backend.app.services import experiment_service, run_service, mlflow_service, prediction_service
>>> dir(experiment_service)
['create_experiment', 'delete_experiment', 'get_experiment', 'get_experiment_by_name',
 'list_experiments', 'count_experiments', 'update_experiment', ...]
>>> # All modules import without error → services are syntactically correct
```

The functions themselves need a live database to actually execute, but importing them is enough to know the module structure is right.

---

## 🧩 Where Phase 4 Fits in the Big Picture

```
HTTP request
     │
     ▼
┌─────────┐    ┌─────────┐    ┌─────────────┐    ┌────────┐    ┌──────────┐
│ Router  │───►│ Schema  │───►│  Service    │───►│ Model  │───►│   DB     │
│ (Phase5)│    │ (Phase3)│    │  (Phase 4)  │    │(Phase2)│    │ Postgres │
└─────────┘    └─────────┘    └──────┬──────┘    └────────┘    └──────────┘
                                      │
                                      ├──► MLflow server (port 5000)
                                      │
                                      └──► MinIO / S3 (port 9000)
```

**Phase 4 is where the application actually does things.** Everything before this was just definitions and plumbing.

---

## 📋 Files Inventory

| File | Lines | Purpose |
|---|---|---|
| `backend/app/services/__init__.py` | 0 | Package marker |
| `backend/app/services/experiment_service.py` | ~125 | CRUD + uniqueness + delete rules |
| `backend/app/services/run_service.py` | ~211 | CRUD + log metrics/params + JSON helpers |
| `backend/app/services/mlflow_service.py` | ~144 | Talk to MLflow tracking server |
| `backend/app/services/prediction_service.py` | ~107 | Load model + run inference |

**Total: ~587 lines** of business logic.
