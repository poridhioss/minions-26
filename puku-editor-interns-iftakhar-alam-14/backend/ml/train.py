"""
⚠️  DEPRECATED — prefer ``sdk/examples/train.py`` (Phase 12).

This file predates the Python SDK and still works, but the SDK rewrite is
~40 lines shorter, has no manual ``X-API-Key`` plumbing, and the run
lifecycle (FINISHED / FAILED) is handled by a single ``with`` block.
Kept around as a no-deps fallback and a reference for the original
``requests.post`` style. Will be removed in a future phase.

------------------------------------------------------------------------

train.py: train a scikit-learn model and log it through the full ML Tracker stack.

End-to-end flow:
    1. POST  /api/v1/experiments       → create (or reuse) an experiment
    2. POST  /api/v1/runs              → create a RUNNING run under that experiment
    3. mlflow.log_params + log_metrics → push hyperparameters + metrics
    4. mlflow.sklearn.log_model        → upload the model to MinIO via MLflow
    5. mlflow.register_model           → add it to the MLflow Model Registry
    6. POST  /api/v1/runs/{id}/finish  → mark the run as FINISHED in Postgres

Usage:
    python -m backend.ml.train \\
        --experiment-name "iris-baseline" \\
        --run-name "rf-v1" \\
        --n-estimators 100 \\
        --max-depth 5

Environment variables (loaded from .env automatically):
    API_BASE_URL      default: http://localhost:8000
    API_KEY           default: dev-key-12345
    MLFLOW_TRACKING_URI  default: http://localhost:5000
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, Optional

import httpx
import mlflow
import mlflow.sklearn
from dotenv import load_dotenv
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score, f1_score, precision_score, recall_score

# Make the dataset importable when running this file directly
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from backend.ml.sample_data import load_dataset  # noqa: E402


# ─── Config ────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("backend.ml.train")

# Load .env from the project root (ml-tracker/.env)
load_dotenv(dotenv_path=Path(__file__).resolve().parents[2] / ".env")

API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000").rstrip("/")
API_KEY = os.getenv("API_KEY", os.getenv("API_KEYS", "dev-key-12345").split(",")[0].strip())
MLFLOW_TRACKING_URI = os.getenv("MLFLOW_TRACKING_URI", "http://localhost:5000")

# Tell the MLflow SDK where the tracking server lives
mlflow.set_tracking_uri(MLFLOW_TRACKING_URI)

HEADERS = {"X-API-Key": API_KEY, "Content-Type": "application/json"}


# ─── HTTP helpers ──────────────────────────────────────────────────────
def _api(method: str, path: str, **kwargs) -> Dict[str, Any]:
    """
    Tiny wrapper around httpx that:
      • prefixes the path with /api/v1
      • raises a clean error if the response is not 2xx
      • returns the parsed JSON body
    """
    url = f"{API_BASE_URL}/api/v1{path}"
    logger.info("→ %s %s", method.upper(), url)
    response = httpx.request(method, url, headers=HEADERS, timeout=30.0, **kwargs)
    if response.status_code >= 400:
        logger.error("← %s %s: %s", response.status_code, response.reason_phrase, response.text)
        response.raise_for_status()
    return response.json() if response.content else {}


# ─── Pipeline steps ────────────────────────────────────────────────────
def get_or_create_experiment(name: str, description: Optional[str] = None) -> int:
    """
    Look up an experiment by name via the API; create it if it doesn't exist.
    Returns the experiment id.
    """
    matches = _api("GET", "/experiments/", params={"search": name, "limit": 200})
    for exp in matches:
        if exp.get("name") == name:
            logger.info("Found existing experiment '%s' (id=%s)", name, exp["id"])
            return int(exp["id"])

    logger.info("Creating experiment '%s'", name)
    payload = {"name": name, "description": description or f"Auto-created by train.py"}
    created = _api("POST", "/experiments/", json=payload)
    return int(created["id"])


def create_run(experiment_id: int, run_name: str) -> int:
    """Create a new RUNNING run under the given experiment. Returns the run id."""
    payload = {
        "experiment_id": experiment_id,
        "run_name": run_name,
        "status": "RUNNING",
        "parameters": {},
        "metrics": {},
    }
    created = _api("POST", "/runs/", json=payload)
    return int(created["id"])


def log_metric_to_api(run_id: int, key: str, value: float) -> None:
    """Forward a single metric to the backend (which mirrors it to MLflow)."""
    _api("POST", f"/runs/{run_id}/metrics", json={"key": key, "value": value})


def finish_run(run_id: int, final_metrics: Dict[str, float], status: str = "FINISHED") -> None:
    """Mark the run as finished via the backend."""
    _api("POST", f"/runs/{run_id}/finish", json={"status": status, "final_metrics": final_metrics})


# ─── Main training routine ─────────────────────────────────────────────
def train(
    experiment_name: str = "synthetic-baseline",
    run_name: str = "rf-default",
    n_estimators: int = 100,
    max_depth: int = 5,
    random_state: int = 42,
    n_samples: int = 300,
) -> Dict[str, Any]:
    """
    Run the full train + log + register pipeline.
    Returns a dict with experiment_id, run_id, model_uri, metrics.
    """
    logger.info("=" * 60)
    logger.info("ML Tracker — training run")
    logger.info("  experiment: %s", experiment_name)
    logger.info("  run:        %s", run_name)
    logger.info("  api:        %s", API_BASE_URL)
    logger.info("  mlflow:     %s", MLFLOW_TRACKING_URI)
    logger.info("=" * 60)

    # 1. Load data
    logger.info("Generating dataset (n_samples=%d, random_state=%d)", n_samples, random_state)
    X_train, X_test, y_train, y_test, feature_names, target_names = load_dataset(
        n_samples=n_samples, random_state=random_state
    )
    logger.info("  X_train: %s, X_test: %s, classes: %d", X_train.shape, X_test.shape, len(target_names))

    # 2. Train
    params = {
        "n_estimators": n_estimators,
        "max_depth": max_depth,
        "random_state": random_state,
        "model_type": "RandomForestClassifier",
    }
    logger.info("Training %s with params=%s", params["model_type"], {k: v for k, v in params.items() if k != "model_type"})
    model = RandomForestClassifier(
        n_estimators=n_estimators,
        max_depth=max_depth,
        random_state=random_state,
    )
    t0 = time.perf_counter()
    model.fit(X_train, y_train)
    train_seconds = time.perf_counter() - t0
    logger.info("Training took %.3fs", train_seconds)

    # 3. Evaluate
    y_pred = model.predict(X_test)
    metrics = {
        "accuracy": float(accuracy_score(y_test, y_pred)),
        "precision_macro": float(precision_score(y_test, y_pred, average="macro", zero_division=0)),
        "recall_macro": float(recall_score(y_test, y_pred, average="macro", zero_division=0)),
        "f1_macro": float(f1_score(y_test, y_pred, average="macro", zero_division=0)),
        "train_seconds": float(train_seconds),
    }
    logger.info("Metrics: %s", metrics)

    # 4. Create experiment + run in Postgres (via API)
    experiment_id = get_or_create_experiment(
        name=experiment_name,
        description=f"Synthetic-blobs classification, n_samples={n_samples}",
    )
    run_id = create_run(experiment_id=experiment_id, run_name=run_name)

    try:
        # 5. Log hyperparameters + metrics to BOTH the backend API and MLflow
        #    (Doing both gives us a queryable system of record in PG and rich
        #    time-series history in MLflow's UI.)
        for k, v in params.items():
            _api("POST", f"/runs/{run_id}/parameters", json={"key": k, "value": str(v)})
        for k, v in metrics.items():
            log_metric_to_api(run_id, k, v)

        # 6. Log the model to MLflow (artifact goes to MinIO)
        with mlflow.start_run(run_name=f"mlflow-{run_name}") as mlf_run:
            mlflow.log_params({k: v for k, v in params.items() if k != "model_type"})
            mlflow.log_metrics(metrics)
            model_info = mlflow.sklearn.log_model(
                sk_model=model,
                artifact_path="model",
                registered_model_name=experiment_name,  # register in the registry under the experiment name
            )
            model_uri = model_info.model_uri
            mlflow_run_id = mlf_run.info.run_id
            logger.info("Logged model to MLflow (run_id=%s, uri=%s)", mlflow_run_id, model_uri)

        # 7. Finish the Postgres-backed run
        finish_run(run_id, final_metrics=metrics, status="FINISHED")

    except Exception as exc:
        logger.exception("Training run failed: %s", exc)
        # Best-effort: mark the run as FAILED so the UI shows the error
        try:
            finish_run(run_id, final_metrics=metrics, status="FAILED")
        except Exception:
            pass
        raise

    return {
        "experiment_id": experiment_id,
        "run_id": run_id,
        "model_uri": model_uri,
        "mlflow_run_id": mlflow_run_id,
        "metrics": metrics,
        "params": params,
    }


# ─── CLI ───────────────────────────────────────────────────────────────
def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Train a model and log it to ML Tracker.")
    parser.add_argument("--experiment-name", default="synthetic-baseline", help="Experiment name in the backend.")
    parser.add_argument("--run-name", default="rf-default", help="Run name under the experiment.")
    parser.add_argument("--n-estimators", type=int, default=100, help="Number of trees in the forest.")
    parser.add_argument("--max-depth", type=int, default=5, help="Max depth of each tree.")
    parser.add_argument("--random-state", type=int, default=42, help="Random seed for reproducibility.")
    parser.add_argument("--n-samples", type=int, default=300, help="Total samples in the synthetic dataset.")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    result = train(
        experiment_name=args.experiment_name,
        run_name=args.run_name,
        n_estimators=args.n_estimators,
        max_depth=args.max_depth,
        random_state=args.random_state,
        n_samples=args.n_samples,
    )
    print("\n" + "=" * 60)
    print("✅  Training run complete")
    print("=" * 60)
    print(f"  experiment_id : {result['experiment_id']}")
    print(f"  run_id        : {result['run_id']}")
    print(f"  model_uri     : {result['model_uri']}")
    print(f"  mlflow_run_id : {result['mlflow_run_id']}")
    print(f"  metrics       : {result['metrics']}")
    print("=" * 60)
    print("Next steps:")
    print("  1. Open MLflow UI (http://localhost:5000) and promote the model to 'Production'.")
    print(f"  2. Run a prediction:")
    print(f"       python -m backend.ml.predict --model-name '{args.experiment_name}' --features 0.5 -0.2 1.1 0.3")
    return 0


if __name__ == "__main__":
    sys.exit(main())
