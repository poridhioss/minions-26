# Phase 8 — ML Training & Inference Scripts

## 🎯 Goal

Add end-to-end ML scripts that exercise the **entire platform stack**:
Postgres ↔ FastAPI ↔ MLflow ↔ MinIO.

After this phase you can run:

```bash
python -m backend.ml.train --experiment-name "synthetic-baseline" --run-name "rf-v1"
python -m backend.ml.predict --model-name "synthetic-baseline" --features 0.5 -0.2 1.1 0.3
```

…and watch a model get created, trained, logged, registered, and queried.

## 📂 What Was Created

```
backend/ml/
├── __init__.py        ← marks the folder as a Python package
├── README.md          ← how to install & use
├── requirements.txt   ← scikit-learn, pandas, numpy, mlflow, httpx, ...
├── sample_data.py     ← synthetic 3-class blobs dataset
├── train.py           ← full training + logging pipeline (CLI)
└── predict.py         ← inference CLI (calls /api/v1/predictions/predict)
```

Plus this build log: `phases/phase-8-ml.md`

## 🧠 Design Decisions

### 1. Separate `requirements.txt`

The main `backend/requirements.txt` is lean (FastAPI, SQLAlchemy, etc.).
ML training needs heavy deps (`scikit-learn`, `pandas`, `numpy`) that would
bloat the API image. We keep them in `backend/ml/requirements.txt` so the
API container can install only what it needs.

### 2. Synthetic dataset, no network

`sample_data.py` generates 3 isotropic Gaussian blobs — small enough to train
in <1s, deterministic (random_state=42), and zero network deps. The
`train.py` script imports it via `sys.path` manipulation so `python -m
backend.ml.train` works from the project root.

### 3. Dual logging (API + MLflow)

For every hyperparameter and metric we log to **both** the FastAPI backend
(Postgres is the system of record) and MLflow (rich time-series UI + model
registry). The router's `POST /runs/{id}/metrics` already forwards to
MLflow, so the API call is sufficient — but we also call `mlflow.log_params`
directly inside the `mlflow.start_run` block to keep training metrics
co-located with the model artifact.

### 4. `experiment_name` doubles as the registered model name

`mlflow.sklearn.log_model(..., registered_model_name=experiment_name)`
registers the model in the MLflow registry under the same name as our
Postgres experiment. After training you promote it to "Production" in the
MLflow UI, then `predict.py --model-name <experiment_name>` will find it
via the `get_latest_model_version` lookup in `mlflow_service.py`.

### 5. Failsafe finish

If anything in the training pipeline raises, we best-effort call
`finish_run(..., status="FAILED")` so the UI shows the error rather than
leaving the run stuck in `RUNNING`.

## 🔌 API Contract (consumed by the scripts)

All calls go to `http://localhost:8000/api/v1` with `X-API-Key: <key>` header.

| Step | Method | Path | Body |
|------|--------|------|------|
| 1. Find/create experiment | `GET`  | `/experiments/?search=<name>` | — |
| 1'. Create experiment    | `POST` | `/experiments/` | `{"name", "description"}` |
| 2. Create run            | `POST` | `/runs/`        | `{"experiment_id", "run_name", "status": "RUNNING"}` |
| 3. Log parameter         | `POST` | `/runs/{id}/parameters` | `{"key", "value"}` |
| 3. Log metric            | `POST` | `/runs/{id}/metrics`    | `{"key", "value", "step"?}` |
| 4. Log model to MLflow   | (direct `mlflow.sklearn.log_model`) | — |
| 5. Register model        | (direct `mlflow.register_model`) | — |
| 6. Finish run            | `POST` | `/runs/{id}/finish` | `{"status": "FINISHED", "final_metrics"}` |
| 7. Predict               | `POST` | `/predictions/predict` | `{"model_name", "stage", "features"}` |

## ▶️ Usage

```bash
# 1. Install the ML extras
pip install -r backend/ml/requirements.txt

# 2. Make sure the stack is running
#    (FastAPI on :8000, MLflow on :5000, MinIO on :9000, Postgres on :5432)

# 3. Train
python -m backend.ml.train \
    --experiment-name "synthetic-baseline" \
    --run-name "rf-v1" \
    --n-estimators 100 \
    --max-depth 5

# 4. Open http://localhost:5000 → click the run → "Register Model" was auto-done
#    Promote the new version to "Production"

# 5. Predict
python -m backend.ml.predict \
    --model-name "synthetic-baseline" \
    --features 0.5 -0.2 1.1 0.3
```

## 📊 What the Output Looks Like

`train.py` prints a final summary like:

```
============================================================
✅  Training run complete
============================================================
  experiment_id : 1
  run_id        : 1
  model_uri     : runs:/abc123/model
  mlflow_run_id : abc123
  metrics       : {'accuracy': 0.95, 'precision_macro': 0.95, ...}
============================================================
```

`predict.py` prints:

```
============================================================
✅  Prediction
============================================================
{
  "prediction": 2,
  "model_uri": "models:/synthetic-baseline/1",
  "model_name": "synthetic-baseline"
}
============================================================
```

## ✅ What This Phase Validates

- ✅ Auth: `X-API-Key` header is accepted by all routers
- ✅ Experiment uniqueness rule: `get_or_create_experiment` works for both new + existing names
- ✅ Run lifecycle: create → log params → log metrics → finish (FINISHED)
- ✅ MLflow integration: model artifact uploaded to MinIO, registered in registry
- ✅ Model registry → prediction pipeline: `/api/v1/predictions/predict` resolves the model
- ✅ Failure handling: if training fails, the run is marked `FAILED` not stuck in `RUNNING`

## ⏭️  Next Phase

Phase 9 — `backend/tests/`: pytest suite with fixtures for the API client
and MLflow mock. Now that we have a working end-to-end pipeline, we can
write tests that exercise it without requiring a live database.

---

## 🪦  Superseded by Phase 12

The `train.py` CLI built in this phase is still functional, but as of
**Phase 12** (`phases/phase-12-sdk.md`) the SDK rewrite at
`sdk/examples/train.py` is the recommended first-touch example. It uses
the `mltracker.run(...)` context manager, which collapses the 8 raw
`requests.post` calls and 4 helper functions in `train.py` into a single
`with` block.

If you landed here looking for "how do I train a model?", go to
`sdk/examples/train.py` instead. This file is kept as a no-deps fallback
and a historical reference for the raw-API style.
