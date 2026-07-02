"""
predict.py: call the backend's /predictions/predict endpoint for inference.

This is a thin CLI wrapper around the API. It exists so you can validate the
end-to-end flow from the terminal without writing Python glue code.

Usage:
    python -m backend.ml.predict \\
        --model-name "synthetic-baseline" \\
        --features 0.5 -0.2 1.1 0.3

    # Or by direct MLflow URI:
    python -m backend.ml.predict \\
        --model-uri "runs:/abc123/model" \\
        --features 0.5 -0.2 1.1 0.3
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from pathlib import Path
from typing import List

import httpx
from dotenv import load_dotenv


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("backend.ml.predict")

# Load .env from the project root
load_dotenv(dotenv_path=Path(__file__).resolve().parents[2] / ".env")

API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000").rstrip("/")
API_KEY = os.getenv("API_KEY", os.getenv("API_KEYS", "dev-key-12345").split(",")[0].strip())
DEFAULT_STAGE = os.getenv("MLFLOW_STAGE", "Production")

HEADERS = {"X-API-Key": API_KEY, "Content-Type": "application/json"}


def predict(
    features: List[float],
    model_name: str | None = None,
    model_uri: str | None = None,
    stage: str = DEFAULT_STAGE,
) -> dict:
    """POST a prediction request to the backend and return the parsed JSON body."""
    if not model_name and not model_uri:
        raise ValueError("Provide either --model-name or --model-uri.")

    payload = {
        "features": features,
        "stage": stage,
    }
    if model_name:
        payload["model_name"] = model_name
    if model_uri:
        payload["model_uri"] = model_uri

    url = f"{API_BASE_URL}/api/v1/predictions/predict"
    logger.info("POST %s  payload=%s", url, {k: v for k, v in payload.items() if k != "features"})
    response = httpx.post(url, headers=HEADERS, json=payload, timeout=30.0)
    if response.status_code >= 400:
        logger.error("← %s %s: %s", response.status_code, response.reason_phrase, response.text)
        response.raise_for_status()
    return response.json()


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Call /predictions/predict on the running backend.")
    parser.add_argument("--model-name", default=None, help="Registered model name in MLflow.")
    parser.add_argument("--model-uri", default=None, help="Direct MLflow URI (overrides --model-name).")
    parser.add_argument("--stage", default=DEFAULT_STAGE, help="Model stage (default: Production).")
    parser.add_argument(
        "--features",
        nargs="+",
        type=float,
        required=True,
        help="Feature values for a single sample, space-separated (e.g. 5.1 3.5 1.4 0.2).",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    result = predict(
        features=args.features,
        model_name=args.model_name,
        model_uri=args.model_uri,
        stage=args.stage,
    )
    print("\n" + "=" * 60)
    print("✅  Prediction")
    print("=" * 60)
    print(json.dumps(result, indent=2))
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
