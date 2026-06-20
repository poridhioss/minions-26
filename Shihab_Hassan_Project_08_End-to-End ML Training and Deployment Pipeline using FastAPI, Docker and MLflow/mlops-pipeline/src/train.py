"""
train.py
========
Purpose : Train multiple Scikit-learn models, log every experiment to MLflow,
          keep the best model (by F1 score), and persist it to disk with joblib.

Why     : This is the heart of the MLOps pipeline. Every step is captured
          by MLflow so we can compare runs, audit results, and reproduce
          any model just by re-running its run_id.

Run from project root:
    python -m src.train
or:
    cd src && python train.py
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import warnings
from typing import Any, Dict

import joblib
import mlflow
import mlflow.sklearn
import numpy as np
from mlflow.models.signature import infer_signature
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    accuracy_score,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)
from sklearn.pipeline import Pipeline

warnings.filterwarnings(
    "ignore",
    message=".*Inferred schema contains integer column.*",
    category=UserWarning,
)
# We persist the deployable model with joblib on disk; the MLflow log is
# for experiment tracking only. Silence the pickle-format caution that
# the mlflow.sklearn logger emits via the logging module.
logging.getLogger("mlflow.sklearn").setLevel(logging.ERROR)
# Silence dependency-mismatch warnings from requirements_utils (we
# pin pip_requirements explicitly below to match the environment).
logging.getLogger("mlflow.utils.requirements_utils").setLevel(logging.ERROR)

# Make sibling modules importable when this file is run directly.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import preprocess as pp  # noqa: E402

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MLRUNS_DIR = os.path.join(PROJECT_ROOT, "mlruns")
BEST_MODEL_PATH = os.path.join(PROJECT_ROOT, "models", "best_model.joblib")
METRICS_PATH = os.path.join(PROJECT_ROOT, "models", "best_metrics.json")

# MLflow experiment name. Switch to a remote tracking URI here if you have
# an MLflow server, e.g. mlflow.set_tracking_uri("http://localhost:5000").
EXPERIMENT_NAME = "customer_churn"

# MLflow 3.x removed the file-store backend by default. We still want a
# zero-config local tracking experience for the project, so opt back in.
# Set MLFLOW_USE_SQLITE=0 to fall back to the legacy file store instead.
USE_SQLITE_BACKEND = os.environ.get("MLFLOW_USE_SQLITE", "1") == "1"


# ---------------------------------------------------------------------------
# Model registry
# ---------------------------------------------------------------------------
def get_models() -> Dict[str, Dict[str, Any]]:
    """Return the candidate models with their parameter grids."""
    return {
        "logistic_regression": {
            "estimator": LogisticRegression(
                max_iter=1000,
                solver="liblinear",  # robust on small/medium datasets
                class_weight="balanced",  # handle ~11% churn imbalance
                random_state=42,
            ),
            "params": {
                "C": 1.0,
                "penalty": "l1",
                "solver": "liblinear",
                "class_weight": "balanced",
            },
        },
        "random_forest": {
            "estimator": RandomForestClassifier(
                n_estimators=200,
                max_depth=10,
                min_samples_split=4,
                class_weight="balanced",  # handle imbalance
                n_jobs=-1,
                random_state=42,
            ),
            "params": {
                "n_estimators": 200,
                "max_depth": 10,
                "min_samples_split": 4,
                "class_weight": "balanced",
            },
        },
    }


def evaluate(y_true, y_pred, y_proba) -> Dict[str, float]:
    """Compute the four headline metrics (plus ROC-AUC as a bonus)."""
    metrics = {
        "accuracy": float(accuracy_score(y_true, y_pred)),
        "precision": float(precision_score(y_true, y_pred, zero_division=0)),
        "recall": float(recall_score(y_true, y_pred, zero_division=0)),
        "f1": float(f1_score(y_true, y_pred, zero_division=0)),
    }
    try:
        metrics["roc_auc"] = float(roc_auc_score(y_true, y_proba))
    except ValueError:
        # Happens only if a test fold has a single class.
        metrics["roc_auc"] = float("nan")
    return metrics


def train_and_log(model_name: str, model_cfg: Dict[str, Any],
                  X_train, X_test, y_train, y_test,
                  preprocessor) -> Dict[str, Any]:
    """Train one model, log everything to MLflow, return a summary dict."""
    estimator = model_cfg["estimator"]
    params = model_cfg["params"]

    # Wrap preprocessor + model in a single Pipeline so the artifact
    # we save is self-contained and can score raw input at inference.
    pipeline = Pipeline(steps=[
        ("preprocessor", preprocessor),
        ("model", estimator),
    ])

    with mlflow.start_run(run_name=model_name) as run:
        # ----- Tag the run for easy filtering in the UI -----
        mlflow.set_tag("model_name", model_name)
        mlflow.set_tag("dataset", "customer_churn")

        # ----- Log parameters -----
        mlflow.log_param("model_type", model_name)
        for k, v in params.items():
            mlflow.log_param(f"model__{k}", v)

        # ----- Fit + predict -----
        pipeline.fit(X_train, y_train)
        y_pred = pipeline.predict(X_test)
        # Some models expose predict_proba; for ones that don't, fall back
        # to the decision function or a zero array.
        if hasattr(pipeline, "predict_proba"):
            y_proba = pipeline.predict_proba(X_test)[:, 1]
        else:
            y_proba = np.zeros_like(y_pred, dtype=float)

        # ----- Log metrics -----
        metrics = evaluate(y_test, y_pred, y_proba)
        for k, v in metrics.items():
            mlflow.log_metric(k, v)

        # ----- Log the model artifact (pickleable sklearn pipeline) -----
        signature = infer_signature(X_train, pipeline.predict(X_train))
        # Suppress the integer/NaN schema warning: our dataset has no NaNs,
        # so the warning is not actionable. The capture context manager
        # keeps it from polluting the training log.
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", UserWarning)
            # NOTE: passing an explicit pip_requirements list tells MLflow
            # to skip its automatic inference (which spawns a `pip` subprocess
            # to introspect the model's environment, and that subprocess can
            # hang indefinitely on some Windows / Python 3.12 setups).
            # The model itself is deployed via joblib, so the requirements
            # list is informational only; we pin to the actual installed
            # versions so MLflow doesn't warn about a "mismatch".
            mlflow.sklearn.log_model(
                sk_model=pipeline,
                name="model",  # MLflow 3.x: 'name' replaces 'artifact_path'
                signature=signature,
                input_example=X_train.head(3),
                pip_requirements=[
                    "scikit-learn==1.9.0",
                    "joblib==1.5.3",
                    "numpy>=1.26,<3.0",
                    "pandas==2.3.3",
                ],
            )

        return {
            "run_id": run.info.run_id,
            "model_name": model_name,
            "metrics": metrics,
            "pipeline": pipeline,
        }


def train_all(csv_path: str = pp.DEFAULT_CSV) -> Dict[str, Any]:
    """Train every candidate model, pick the best by F1, persist it.

    Returns the summary of the winning run.
    """
    # 1) MLflow tracking: SQLite is the recommended backend in MLflow 3.x
    #    and works without any extra services. Set MLFLOW_USE_SQLITE=0 to
    #    fall back to the legacy file store instead.
    os.makedirs(MLRUNS_DIR, exist_ok=True)
    if USE_SQLITE_BACKEND:
        db_path = os.path.join(MLRUNS_DIR, "mlflow.db")
        mlflow.set_tracking_uri(f"sqlite:///{db_path}")
    else:
        # Opt into the deprecated file store for users that want it.
        os.environ.setdefault("MLFLOW_ALLOW_FILE_STORE", "true")
        mlflow.set_tracking_uri(f"file:{MLRUNS_DIR}")
    mlflow.set_experiment(EXPERIMENT_NAME)

    # 2) Load + split
    X_train, X_test, y_train, y_test, preprocessor = pp.preprocess_for_training(
        csv_path=csv_path
    )

    # 3) Train & log each candidate
    results = []
    for name, cfg in get_models().items():
        print(f"\n=== Training: {name} ===")
        result = train_and_log(
            model_name=name,
            model_cfg=cfg,
            X_train=X_train,
            X_test=X_test,
            y_train=y_train,
            y_test=y_test,
            preprocessor=preprocessor,
        )
        results.append(result)
        m = result["metrics"]
        print(f"  accuracy={m['accuracy']:.4f}  precision={m['precision']:.4f}  "
              f"recall={m['recall']:.4f}  f1={m['f1']:.4f}  roc_auc={m['roc_auc']:.4f}")

    # 4) Pick the best by F1 (good balance for imbalanced classification)
    best = max(results, key=lambda r: r["metrics"]["f1"])
    print(f"\n>>> Best model: {best['model_name']}  (F1={best['metrics']['f1']:.4f})")

    # 5) Persist best pipeline (already fitted) so FastAPI can load it.
    os.makedirs(os.path.dirname(BEST_MODEL_PATH), exist_ok=True)
    joblib.dump(best["pipeline"], BEST_MODEL_PATH)

    # Also keep the preprocessor separately (in case you want to inspect it).
    pp.save_preprocessor(preprocessor)

    # 6) Save metrics summary for the /train response
    summary = {
        "best_model": best["model_name"],
        "best_run_id": best["run_id"],
        "best_metrics": best["metrics"],
        "all_runs": [
            {"model": r["model_name"], "run_id": r["run_id"], **r["metrics"]}
            for r in results
        ],
    }
    with open(METRICS_PATH, "w") as f:
        json.dump(summary, f, indent=2)

    print(f"[OK] Saved best pipeline -> {BEST_MODEL_PATH}")
    print(f"[OK] Saved metrics       -> {METRICS_PATH}")
    return summary


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Train churn models and log to MLflow.")
    p.add_argument("--csv", default=pp.DEFAULT_CSV, help="Path to the training CSV.")
    return p.parse_args()


if __name__ == "__main__":
    args = parse_args()
    train_all(csv_path=args.csv)
