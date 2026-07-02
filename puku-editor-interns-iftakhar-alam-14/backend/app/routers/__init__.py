"""
Routers package: HTTP layer for the ML Tracker backend.

Each module in this package defines an `APIRouter` for one resource:
  • experiments.py → /experiments/*
  • runs.py        → /runs/*        (incl. /runs/{id}/metrics, /finish)
  • predictions.py → /predictions/* (model inference)
  • models.py      → /models/*      (MLflow model registry browser)

We re-export the four `router` objects here so `main.py` (Phase 6) can
import them in one line and mount them in one line each:

    from app.routers import experiments_router, runs_router, predictions_router, models_router

    app.include_router(experiments_router, prefix="/api/v1")
    app.include_router(runs_router,        prefix="/api/v1")
    app.include_router(predictions_router, prefix="/api/v1")
    app.include_router(models_router,      prefix="/api/v1")

This keeps the wiring in one file (main.py) without main.py having to
know the internal layout of the routers package.
"""
from backend.app.routers.experiments import router as experiments_router
from backend.app.routers.runs import router as runs_router
from backend.app.routers.predictions import router as predictions_router
from backend.app.routers.models import router as models_router


__all__ = [
    "experiments_router",
    "runs_router",
    "predictions_router",
    "models_router",
]
