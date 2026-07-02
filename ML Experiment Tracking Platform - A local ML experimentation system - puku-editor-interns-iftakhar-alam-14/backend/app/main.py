"""
FastAPI application entry point — the heart of the backend.

This is the file uvicorn runs:

    cd backend && uvicorn app.main:app --reload

Responsibilities:
  1. Construct the FastAPI() instance with title/version from settings
  2. Mount CORS middleware (so the React frontend at :3000 can call us)
  3. Register the 4 routers under /api/v1
  4. Protect ALL routes with the X-API-Key dependency (app-level)
  5. Register a /health endpoint (no auth, for load balancers)
  6. Register startup/shutdown events (DB table creation, connection test)
  7. Register a global exception handler so unhandled ValueErrors → 400
     instead of a 500
"""
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import Depends, FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import OperationalError, SQLAlchemyError

# Routers — Phase 5
from backend.app.routers import (
    experiments_router,
    models_router,
    predictions_router,
    runs_router,
)

# Database + settings + auth — Phases 1 & 2
from backend.app.core.config import settings
from backend.app.core.security import get_current_user
from backend.app.database import Base, SessionLocal, engine

# Import model modules so SQLAlchemy's metadata.register() knows about them
# (otherwise Base.metadata.create_all() would create an EMPTY database)
import backend.app.models  # noqa: F401  (side-effect import)


# ════════════════════════════════════════════════════════════════════════
#  Lifespan: startup + shutdown
# ════════════════════════════════════════════════════════════════════════
@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """
    Modern FastAPI lifespan handler (replaces deprecated @app.on_event).

    Code BEFORE `yield` runs at startup.
    Code AFTER  `yield` runs at shutdown.

    Startup:  test the DB connection, create tables (idempotent).
    Shutdown: close the engine's connection pool cleanly.
    """
    # ── STARTUP ────────────────────────────────────────────────────────
    print(f"🚀 Starting {settings.APP_NAME} v{settings.APP_VERSION} (debug={settings.DEBUG})")
    print(f"   Database: {settings.DATABASE_URL.split('@')[-1]}")   # mask creds
    print(f"   MLflow:   {settings.MLFLOW_TRACKING_URI}")
    print(f"   CORS:     {settings.cors_origins_list}")

    # Test the DB connection — fail fast if Postgres is unreachable
    try:
        with SessionLocal() as db:
            db.execute(text("SELECT 1"))
        print("   ✅ Database connection OK")
    except OperationalError as exc:
        print(f"   ❌ Database connection FAILED: {exc}")
        # We don't raise here — let the server start so /health still works
        # and dev can see the error. In prod you'd raise to abort startup.

    # Schema management is done by Alembic (see backend/alembic/).
    # In production, you should always run `alembic upgrade head` before
    # starting the app — NEVER rely on `create_all` for production schemas.
    #
    # We keep `create_all` here as a dev-only convenience: if a developer
    # spins up the app against a fresh, empty database, tables will be
    # created automatically so they can hit the API immediately. In
    # production, the Alembic-managed tables will already exist, and
    # `create_all` will be a no-op for them (it only adds tables that
    # don't exist; it never alters or drops).
    try:
        Base.metadata.create_all(bind=engine)
        print(f"   ✅ Tables ensured via create_all (dev convenience): "
              f"{sorted(Base.metadata.tables.keys())}")
        print("   ℹ️  Production: run `alembic upgrade head` instead")
    except SQLAlchemyError as exc:
        print(f"   ❌ create_all() FAILED: {exc}")

    yield   # ← server is now running and serving requests

    # ── SHUTDOWN ───────────────────────────────────────────────────────
    print("🛑 Shutting down — disposing DB engine")
    engine.dispose()


# ════════════════════════════════════════════════════════════════════════
#  The FastAPI application
# ════════════════════════════════════════════════════════════════════════
app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    debug=settings.DEBUG,
    description=(
        "End-to-end ML training, tracking, and deployment platform. "
        "Similar in spirit to MLflow / Weights & Biases.\n\n"
        "**All endpoints (except `/health` and `/docs`) require an `X-API-Key` header.**"
    ),
    lifespan=lifespan,
    # OpenAPI tag ordering in Swagger UI
    openapi_tags=[
        {"name": "experiments", "description": "CRUD over experiment records."},
        {"name": "runs",        "description": "CRUD + metric/parameter logging for runs."},
        {"name": "predictions", "description": "Model inference endpoint."},
        {"name": "models",      "description": "Browse the MLflow model registry."},
        {"name": "health",      "description": "Liveness / readiness probes."},
    ],
)


# ════════════════════════════════════════════════════════════════════════
#  Middleware: CORS
# ════════════════════════════════════════════════════════════════════════
# Middleware runs OUTSIDE the route — every request passes through it.
# CORS = "Cross-Origin Resource Sharing": when the browser at localhost:3000
# calls us at localhost:8000, the browser first asks "is this allowed?".
# Without these headers, the browser would block the response.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,    # from .env
    allow_credentials=True,                       # allow cookies / auth headers
    allow_methods=["*"],                          # GET, POST, PATCH, DELETE, ...
    allow_headers=["*"],                          # X-API-Key, Content-Type, ...
)


# ════════════════════════════════════════════════════════════════════════
#  Global exception handler — catch unhandled ValueErrors
# ════════════════════════════════════════════════════════════════════════
# Services raise plain ValueError. Routers usually catch them, but if one
# slips through, we don't want a 500 — we want a clean 400.
@app.exception_handler(ValueError)
async def value_error_handler(request: Request, exc: ValueError) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content={"detail": str(exc)},
    )


# ─── Also normalize FastAPI's request-validation errors (422 → friendlier) ─
# Pydantic raises 422 for bad shapes. We keep that, but we ADD the field
# path so the client knows which field was wrong.
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    request: Request,
    exc: RequestValidationError,
) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "detail": "Request validation failed",
            "errors": exc.errors(),     # list of {loc, msg, type, ...}
        },
    )


# ════════════════════════════════════════════════════════════════════════
#  Health endpoint — NO auth, used by load balancers / Docker healthcheck
# ════════════════════════════════════════════════════════════════════════
@app.get(
    "/health",
    tags=["health"],
    summary="Liveness / readiness check",
    description=(
        "Returns 200 if the process is running. Does NOT check downstream "
        "dependencies (DB, MLflow) — that's the job of a deeper readiness probe."
    ),
)
def health() -> dict:
    return {
        "status": "ok",
        "app": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "debug": settings.DEBUG,
    }


# ════════════════════════════════════════════════════════════════════════
#  Protected sub-app — all real API routes live under here
# ════════════════════════════════════════════════════════════════════════
# We use app.include_router(..., dependencies=[Depends(get_current_user)])
# to enforce X-API-Key on EVERY route in that router, so we don't have to
# repeat the dependency on every endpoint individually.
#
# Note: prefix="/api/v1" is the API VERSION. Keeping it in main.py (not in
# the router) lets us mount the same router under /api/v2 later if needed.
api_v1_prefix = "/api/v1"

app.include_router(
    experiments_router,
    prefix=api_v1_prefix,
    dependencies=[Depends(get_current_user)],
)
app.include_router(
    runs_router,
    prefix=api_v1_prefix,
    dependencies=[Depends(get_current_user)],
)
app.include_router(
    predictions_router,
    prefix=api_v1_prefix,
    dependencies=[Depends(get_current_user)],
)
app.include_router(
    models_router,
    prefix=api_v1_prefix,
    dependencies=[Depends(get_current_user)],
)


# ════════════════════════════════════════════════════════════════════════
#  Root endpoint — friendly hello + link to docs
# ════════════════════════════════════════════════════════════════════════
@app.get("/", include_in_schema=False)
def root() -> dict:
    return {
        "message": f"Welcome to {settings.APP_NAME}",
        "version": settings.APP_VERSION,
        "docs": "/docs",
        "openapi": "/openapi.json",
        "health": "/health",
        "api": api_v1_prefix,
    }


# ════════════════════════════════════════════════════════════════════════
#  Local dev entrypoint
# ════════════════════════════════════════════════════════════════════════
# Running this file directly:
#     python -m backend.app.main
# won't work — uvicorn is the proper runner. But we expose this so an IDE
# can launch the file in "debug" mode if needed.
if __name__ == "__main__":  # pragma: no cover
    import uvicorn
    uvicorn.run(
        "backend.app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.DEBUG,
    )
