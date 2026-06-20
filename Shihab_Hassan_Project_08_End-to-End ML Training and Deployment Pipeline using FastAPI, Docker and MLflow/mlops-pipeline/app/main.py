"""
main.py
=======
Purpose : FastAPI application exposing the churn-prediction service.

Endpoints
---------
GET  /health       -> liveness + model status
POST /predict      -> score one or more customers
POST /train        -> retrain the model on the current data
GET  /docs         -> interactive Swagger UI (built-in)
GET  /redoc        -> ReDoc documentation (built-in)

Run locally:
    uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
"""

from __future__ import annotations

import logging
import os
import sys
from contextlib import asynccontextmanager
from typing import Any, Dict

from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware

# Make the project root and src/ importable regardless of how we run uvicorn.
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)
sys.path.insert(0, os.path.join(PROJECT_ROOT, "src"))

from app import schemas  # noqa: E402
from src import train as train_module  # noqa: E402
from src.predict import ChurnPredictor  # noqa: E402

# ---------------------------------------------------------------------------
# Logging — keep it simple; uvicorn configures its own handlers at runtime.
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger("mlops-pipeline")

# ---------------------------------------------------------------------------
# App state container
# ---------------------------------------------------------------------------
class AppState:
    """Holds the currently loaded predictor so we can hot-reload after /train."""
    predictor: ChurnPredictor | None = None


state = AppState()


def _load_predictor() -> ChurnPredictor:
    """Try to load the trained model; raise a clear error if missing."""
    try:
        return ChurnPredictor()
    except FileNotFoundError as e:
        logger.warning("Model not found: %s", e)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "No trained model is available. POST /train to create one, "
                "or run: python -m src.train"
            ),
        )


@asynccontextmanager
async def lifespan(app: FastAPI):
    """FastAPI lifespan hook: load the model on startup."""
    logger.info("Starting up — attempting to load trained model...")
    try:
        state.predictor = ChurnPredictor()
        logger.info("Loaded model: %s", state.predictor.model_name)
    except FileNotFoundError:
        state.predictor = None
        logger.warning(
            "No trained model found. Use POST /train to create one."
        )
    yield
    logger.info("Shutting down.")


# ---------------------------------------------------------------------------
# FastAPI app instance
# ---------------------------------------------------------------------------
app = FastAPI(
    title="Customer Churn ML Pipeline",
    description=(
        "End-to-end MLOps demo: trains Scikit-learn models, tracks them "
        "with MLflow, and serves predictions through FastAPI."
    ),
    version="0.1.0",
    lifespan=lifespan,
)

# CORS — wide open for the internship demo. Tighten this in production.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# GET /health
# ---------------------------------------------------------------------------
@app.get("/health", response_model=schemas.HealthResponse, tags=["health"])
def health() -> schemas.HealthResponse:
    """Liveness probe — also reports whether a trained model is loaded."""
    loaded = state.predictor is not None
    return schemas.HealthResponse(
        status="ok" if loaded else "degraded",
        model_loaded=loaded,
        model_name=state.predictor.model_name if loaded else "",
    )


# ---------------------------------------------------------------------------
# POST /predict
# ---------------------------------------------------------------------------
@app.post("/predict", response_model=schemas.PredictResponse, tags=["prediction"])
def predict(req: schemas.PredictRequest) -> schemas.PredictResponse:
    """Score one or more customers against the trained model.

    Accepts a batch of customers in a single call so frontends can
    submit uploads or a list of rows efficiently.
    """
    if state.predictor is None:
        # Try loading lazily in case training happened after startup.
        state.predictor = _load_predictor()

    # Convert pydantic models -> plain dicts for the predictor.
    records: list[Dict[str, Any]] = [inst.model_dump() for inst in req.instances]
    try:
        results = state.predictor.predict_with_proba(records)
    except ValueError as e:
        # Bad input shape (e.g. unknown column)
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        # Anything else is a server fault.
        logger.exception("Prediction failed")
        raise HTTPException(status_code=500, detail=f"Prediction failed: {e}")

    return schemas.PredictResponse(
        model=state.predictor.model_name,
        count=len(results),
        predictions=[schemas.PredictionItem(**r) for r in results],
    )


# ---------------------------------------------------------------------------
# POST /train
# ---------------------------------------------------------------------------
@app.post("/train", response_model=schemas.TrainResponse, tags=["training"])
def train(req: schemas.TrainRequest | None = None) -> schemas.TrainResponse:
    """Retrain both candidate models and reload the best one into memory.

    Useful for keeping the served model in sync with fresh data, or as
    a quick way to bootstrap the service before any /predict call.
    """
    csv_path = (req.csv_path if req and req.csv_path else None)
    logger.info("Retraining models (csv=%s)...", csv_path or "<default>")

    try:
        summary = train_module.train_all(csv_path=csv_path) if csv_path else train_module.train_all()
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.exception("Training failed")
        raise HTTPException(status_code=500, detail=f"Training failed: {e}")

    # Hot-swap the predictor so subsequent /predict calls use the new model.
    state.predictor = ChurnPredictor()
    logger.info("Hot-reloaded predictor: %s", state.predictor.model_name)

    return schemas.TrainResponse(
        best_model=summary["best_model"],
        best_run_id=summary["best_run_id"],
        best_metrics=schemas.ModelMetrics(**summary["best_metrics"]),
        all_runs=[schemas.RunSummary(**r) for r in summary["all_runs"]],
        model_artifact=train_module.BEST_MODEL_PATH,
    )


# ---------------------------------------------------------------------------
# Entry point for `python -m app.main`
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
