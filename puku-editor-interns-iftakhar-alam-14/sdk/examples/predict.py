"""
predict.py: hit the prediction endpoint via the SDK.

A trimmed-down CLI for the original ``backend/ml/predict.py``. The full
batch-prediction logic (loading the registered model, scoring a CSV)
lives there; here we focus on the *single* prediction path that the
SDK exposes as :func:`mltracker.predict`.

Usage:
    python -m sdk.examples.predict \\
        --model-name "iris-baseline" \\
        --stage Production \\
        --features 0.5 -0.2 1.1 0.3

Or with a JSON object (for non-vector features):
    python -m sdk.examples.predict \\
        --model-name "iris-baseline" \\
        --features-json '{"sepal_length": 5.1, "sepal_width": 3.5}'
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from pathlib import Path
from typing import Any, Sequence, Union

import mltracker
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(dotenv_path=PROJECT_ROOT / ".env")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("sdk.examples.predict")


def _parse_features(args: argparse.Namespace) -> Union[Sequence[Any], dict]:
    """
    Resolve the ``--features`` / ``--features-json`` flags into the
    shape the backend expects (list OR dict — see ``PredictIn.features``).
    """
    if args.features_json:
        try:
            return json.loads(args.features_json)
        except json.JSONDecodeError as e:
            raise SystemExit(f"--features-json is not valid JSON: {e}")
    if args.features:
        # Coerce to float — the backend takes a list of numbers for
        # vector models, which is the common case.
        return [float(x) for x in args.features]
    raise SystemExit("Provide either --features (list) or --features-json (object).")


def main() -> int:
    parser = argparse.ArgumentParser(description="Call /predictions/predict via the SDK.")
    parser.add_argument("--model-name", required=True, help="Registered model name (e.g. 'iris-baseline').")
    parser.add_argument("--model-uri", help="Direct MLflow URI (e.g. 'models:/iris-baseline/1'). Overrides --model-name.")
    parser.add_argument("--stage", default="Production", choices=["Production", "Staging", "Archived", "None"])
    parser.add_argument("--features", nargs="*", help="Feature vector as space-separated floats.")
    parser.add_argument("--features-json", help="Feature dict as a JSON string.")
    args = parser.parse_args()

    # Configure the singleton client. Idempotent — safe to call even if
    # the user has already called mltracker.login() elsewhere.
    mltracker.login()

    features = _parse_features(args)
    logger.info("Predicting model=%s stage=%s features=%s", args.model_name, args.stage, features)

    try:
        result = mltracker.predict(
            features=features,
            model_name=args.model_name,
            model_uri=args.model_uri,
            stage=args.stage,
        )
    except mltracker.NotFoundError:
        logger.error(
            "Model '%s' (stage=%s) not found. "
            "Did you promote a version to %s in the MLflow UI?",
            args.model_name, args.stage, args.stage,
        )
        return 2
    except mltracker.AuthenticationError as e:
        logger.error("Auth failed — check MLTRACKER_API_KEY: %s", e)
        return 3
    except mltracker.APIError as e:
        logger.error("Backend error: %s", e)
        return 1

    print("\n" + "=" * 60)
    print("✅  Prediction")
    print("=" * 60)
    print(f"  model_name    : {result.model_name}")
    print(f"  model_version : {result.model_version}")
    print(f"  model_stage   : {result.model_stage}")
    print(f"  predictions   : {result.predictions}")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
