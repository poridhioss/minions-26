# `backend/ml/` — Training & Inference Scripts

> ⚠️  These scripts are **legacy** as of Phase 12. The canonical first-touch
> example is now **`sdk/examples/train.py`** (and **`sdk/examples/predict.py`**)
> which uses the `mltracker` Python SDK. You can still run the commands in
> this README — they work — but new code should target the SDK.

These scripts exercise the **full end-to-end ML lifecycle** against the running
backend, MLflow tracking server, and MinIO artifact store.

## Files

| File | Purpose |
|------|---------|
| `sample_data.py` | Generates a tiny synthetic classification dataset (no network needed). |
| `train.py`       | Trains a `RandomForestClassifier`, logs params/metrics/model to MLflow + MinIO, creates a Postgres-backed experiment+run via the API. |
| `predict.py`     | Calls the backend's `/api/v1/predictions/predict` endpoint for inference. |

## Setup

```bash
# from the ml-tracker/ project root, with the venv active:
pip install -r backend/ml/requirements.txt
```

## Usage

```bash
# 1. Make sure backend, MLflow, MinIO, and Postgres are running
#    (see ../README.md for docker-compose up)

# 2. Train a model (creates experiment + run, logs everything)
python -m backend.ml.train \
    --experiment-name "iris-baseline" \
    --run-name "rf-v1" \
    --n-estimators 100 \
    --max-depth 5

# 3. Promote the model in MLflow UI (http://localhost:5000) to "Production"

# 4. Run a prediction
python -m backend.ml.predict --model-name "iris-baseline" --features 5.1 3.5 1.4 0.2
```

## What `train.py` does

1. Generates (or loads) a small classification dataset.
2. Splits it 80/20 into train/test.
3. Trains a `RandomForestClassifier` with the given hyperparameters.
4. Computes accuracy + per-class precision/recall.
5. POSTs to the backend to:
   - Create an experiment (or reuse the existing one).
   - Create a run under that experiment.
   - Log hyperparameters and final metrics.
   - Log the model to MLflow (artifact goes to MinIO).
   - Register the model in the MLflow registry.
   - Mark the run as `FINISHED`.
6. Prints a summary with the new experiment ID, run ID, and registered model name.

## What `predict.py` does

1. Reads `--features` from the CLI.
2. POSTs to `/api/v1/predictions/predict` with the model name and features.
3. Prints the prediction (class label) and the model URI that was used.
