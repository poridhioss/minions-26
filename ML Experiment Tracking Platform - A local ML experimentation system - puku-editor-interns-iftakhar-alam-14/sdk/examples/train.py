"""
train.py: train a scikit-learn model and log it through the SDK.

This is the SDK-flavoured rewrite of ``backend/ml/train.py``. Compare the
two side-by-side and you should see:

  • ~40 fewer lines (no httpx, no X-API-Key plumbing, no JSON shaping)
  • All HTTP is funneled through ``mltracker.runs`` / ``mltracker.experiments``
  • The training loop is unchanged — we still do the same sklearn fit
  • MLflow logging is unchanged — the SDK only owns the *tracker* side

End-to-end flow:
    1. mltracker.login()                      → configure the singleton client
    2. mltracker.run(experiment_name=...)     → start a RUNNING run (the
                                                 context manager creates the
                                                 experiment on-demand)
    3. run.log_param / run.log_metric         → push hyperparameters + metrics
    4. mlflow.sklearn.log_model               → upload the model to MinIO
    5. mltracker.register(...) or context     → registered in the backend's
       exit auto-finishes the run              model registry view
    6. with-block exit                        → marks the run FINISHED in PG

Usage:
    python -m sdk.examples.train \\
        --experiment-name "iris-baseline" \\
        --run-name "rf-v1" \\
        --n-estimators 100 \\
        --max-depth 5

Environment variables (auto-loaded by the SDK):
    MLTRACKER_URL         default: http://localhost:8000
    MLTRACKER_API_KEY     default: (empty — set it in .env)
    MLFLOW_TRACKING_URI   default: http://localhost:5000
"""
from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path
from typing import Any, Dict, Optional

# Make the dataset importable when running this file directly. We add the
# project root to sys.path so ``backend.ml.sample_data`` resolves the
# same way it does in the original train.py.
PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv  # noqa: E402
from sklearn.ensemble import RandomForestClassifier  # noqa: E402
from sklearn.metrics import (  # noqa: E402
    accuracy_score,
    f1_score,
    precision_score,
    recall_score,
)

import mltracker  # noqa: E402  (after the path fix)
from backend.ml.sample_data import load_dataset  # noqa: E402

# Load .env from the project root — this populates MLTRACKER_URL /
# MLTRACKER_API_KEY *and* MLFLOW_TRACKING_URI.
load_dotenv(dotenv_path=PROJECT_ROOT / ".env")

import os  # noqa: E402

import mlflow  # noqa: E402
import mlflow.sklearn  # noqa: E402

# ─── Config ────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("sdk.examples.train")

# Tell the MLflow SDK where the tracking server lives.
mlflow.set_tracking_uri(os.getenv("MLFLOW_TRACKING_URI", "http://localhost:5000"))


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

    Notice how the bookkeeping (create experiment, create run, mark
    finished/FAILED) is one ``with`` block. Compare with the original
    train.py where the same bookkeeping spans 50 lines and 6 helper
    functions.
    """
    logger.info("=" * 60)
    logger.info("ML Tracker — training run (via SDK)")
    logger.info("  experiment: %s", experiment_name)
    logger.info("  run:        %s", run_name)
    logger.info("  url:        %s", os.getenv("MLTRACKER_URL", "http://localhost:8000"))
    logger.info("  mlflow:     %s", os.getenv("MLFLOW_TRACKING_URI", "http://localhost:5000"))
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
    logger.info(
        "Training %s with params=%s",
        params["model_type"],
        {k: v for k, v in params.items() if k != "model_type"},
    )
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

    # 4-5. Log to the backend via the SDK. The ``with`` block:
    #      • creates the experiment if missing
    #      • opens a RUNNING run
    #      • auto-marks FINISHED on clean exit, FAILED on exception
    experiment_id: Optional[int] = None
    run_id: Optional[int] = None
    model_uri: Optional[str] = None
    mlflow_run_id: Optional[str] = None

    # ``mltracker.login()`` is idempotent — it reads MLTRACKER_URL /
    # MLTRACKER_API_KEY from the environment (populated by load_dotenv
    # above). Calling it explicitly here makes the example self-contained
    # (you can paste it into a notebook without setting env vars first).
    mltracker.login()

    with mltracker.run(
        run_name=run_name,
        experiment_name=experiment_name,
        parameters={k: v for k, v in params.items() if k != "model_type"},
        tags={"framework": "scikit-learn", "model_type": params["model_type"]},
    ) as run:
        experiment_id = run.model.experiment_id
        run_id = run.id
        logger.info("Started run id=%s in experiment id=%s", run_id, experiment_id)

        # 5a. Log hyperparameters + metrics to the backend (which mirrors
        #     them to MLflow's tracking store).
        run.log_param("model_type", params["model_type"])
        run.log_metrics(metrics)

        # 5b. Log the model to MLflow (artifact goes to MinIO). We use a
        #     nested mlflow.start_run so the MLflow run_id lines up with
        #     the backend's run id; this is purely cosmetic and makes the
        #     UI navigation nicer.
        with mlflow.start_run(run_name=f"mlflow-{run_name}") as mlf_run:
            mlflow.log_params({k: v for k, v in params.items() if k != "model_type"})
            mlflow.log_metrics(metrics)
            model_info = mlflow.sklearn.log_model(
                sk_model=model,
                artifact_path="model",
                registered_model_name=experiment_name,
            )
            model_uri = model_info.model_uri
            mlflow_run_id = mlf_run.info.run_id
            logger.info("Logged model to MLflow (run_id=%s, uri=%s)", mlflow_run_id, model_uri)

    # At this point ``run.__exit__`` has run and the backend run is FINISHED.
    # The result is a complete row in Postgres + a registered model in MLflow.

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
    parser = argparse.ArgumentParser(description="Train a model and log it to ML Tracker (via SDK).")
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
    print(f"       python -m sdk.examples.predict --model-name '{args.experiment_name}' --features 0.5 -0.2 1.1 0.3")
    return 0


if __name__ == "__main__":
    sys.exit(main())
