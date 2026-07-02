# Phase 6 — `main.py` (FastAPI Application Entry Point)

## 🎯 What This Phase Did

Phase 6 is the **glue phase**. Every previous phase built an isolated piece:
- Phase 1 → database connection
- Phase 2 → tables
- Phase 3 → Pydantic schemas
- Phase 4 → business logic
- Phase 5 → HTTP handlers

`main.py` is the file that **ties them all into a running web server**. It's what `uvicorn` reads to start the API.

> 🎭 If the project is a restaurant, `main.py` is the **opening manager** — they unlock the door, turn on the lights, hand each guest a menu, and tell the kitchen when it's time to open. They don't cook, but without them nothing is reachable.

After this phase, you can do:

```bash
cd backend && uvicorn app.main:app --reload
# → API live at http://localhost:8000
# → Auto docs at http://localhost:8000/docs
```

---

## 📂 What Was Created

```
backend/app/
└── main.py        ← The only new file in this phase
```

That's it. Just one file — but it pulls in **everything from every previous phase**.

---

## ⭐ File: `main.py` — The Entry Point (244 lines)

The file is structured in **eight logical blocks**. Each has a single, focused responsibility.

### Block 1 — Imports

```python
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import Depends, FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import OperationalError, SQLAlchemyError

from backend.app.routers import (
    experiments_router, models_router, predictions_router, runs_router,
)
from backend.app.core.config import settings
from backend.app.core.security import get_current_user
from backend.app.database import Base, SessionLocal, engine

import backend.app.models  # noqa: F401  (side-effect import)
```

**The one tricky line is `import backend.app.models  # noqa: F401`.** It looks unused, but it's doing real work:

1. The `models/` package's `__init__.py` imports `Experiment` and `Run` from its submodules.
2. When those classes are imported, they call `Base.registry(...)` (or the older `Base = declarative_base()`) to register themselves with `Base.metadata`.
3. So `Base.metadata.create_all()` (called during startup) only knows about tables whose models have been **imported at least once**.

> 💡 Forget this import and your `experiments` and `runs` tables will silently **never be created** — your API will start fine, but every request to `/api/v1/experiments/` will 500 with `relation "experiments" does not exist`.

---

### Block 2 — The Lifespan Handler

```python
@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    # STARTUP (before yield)
    print(f"🚀 Starting {settings.APP_NAME} v{settings.APP_VERSION} ...")
    try:
        with SessionLocal() as db:
            db.execute(text("SELECT 1"))
        print("   ✅ Database connection OK")
    except OperationalError as exc:
        print(f"   ❌ Database connection FAILED: {exc}")

    try:
        Base.metadata.create_all(bind=engine)
        print(f"   ✅ Tables ensured: {sorted(Base.metadata.tables.keys())}")
    except SQLAlchemyError as exc:
        print(f"   ❌ create_all() FAILED: {exc}")

    yield   # ← server is now serving requests

    # SHUTDOWN (after yield)
    print("🛑 Shutting down — disposing DB engine")
    engine.dispose()
```

**What this does, step by step:**

1. **`@asynccontextmanager`** is the modern way to do startup/shutdown in FastAPI (replaces the deprecated `@app.on_event("startup")`).
2. **Before `yield`** = startup work:
   - Print a banner (so devs can see the app started).
   - Run `SELECT 1` to **fail fast** if Postgres is unreachable. We *log* the error instead of raising, so the server still boots and `/health` works even if the DB is down — load balancers can then take the pod out of rotation.
   - Call `Base.metadata.create_all(bind=engine)`. This is **idempotent** — it creates tables that don't exist, leaves existing ones alone.
3. **`yield`** = the server runs and serves requests.
4. **After `yield`** = shutdown work:
   - `engine.dispose()` cleanly closes the SQLAlchemy connection pool. Without this, you may see "Event loop closed" warnings when uvicorn reloads.

**Why `create_all()` and not Alembic?**
For an MVP / learning project, `create_all()` is fine. For production:
- Alembic lets you **migrate** existing tables (rename columns, change types, add indexes).
- `create_all()` only **creates** new tables — it never alters them.

Phase 7+ would introduce Alembic. The `alembic/` directory you see in the repo is already stubbed out for this.

---

### Block 3 — The `FastAPI()` Application

```python
app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    debug=settings.DEBUG,
    description="End-to-end ML training, tracking, and deployment platform. ...",
    lifespan=lifespan,
    openapi_tags=[
        {"name": "experiments", "description": "CRUD over experiment records."},
        {"name": "runs",        "description": "CRUD + metric/parameter logging for runs."},
        {"name": "predictions", "description": "Model inference endpoint."},
        {"name": "models",      "description": "Browse the MLflow model registry."},
        {"name": "health",      "description": "Liveness / readiness probes."},
    ],
)
```

**Every parameter does real work:**

| Param | What it does |
|---|---|
| `title` | Shows in Swagger UI header and OpenAPI spec |
| `version` | Same, plus sent in `X-API-Version` style headers |
| `debug` | If `True`, FastAPI shows detailed 500 error pages (don't enable in prod) |
| `description` | Rendered as Markdown on the `/docs` index page |
| `lifespan` | The startup/shutdown handler from Block 2 |
| `openapi_tags` | **The order in this list = the order groups appear in Swagger UI** |

The `description` field supports **Markdown** — that `**` makes "All endpoints (except `/health` and `/docs`) require an `X-API-Key` header" bold in the docs.

---

### Block 4 — CORS Middleware

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,    # ["http://localhost:3000", ...]
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

**CORS** = **C**ross-**O**rigin **R**esource **S**haring.

**The problem:** When the React app at `http://localhost:3000` makes a fetch to `http://localhost:8000/api/v1/experiments/`, the **browser** (not us, not the server) checks if the target origin is on an allow-list. If not, the browser blocks the response. The request never even gets to the server.

**Why does the browser do this?** Same-Origin Policy — a security feature that prevents a malicious site at `evil.com` from reading your email at `gmail.com` while you're logged in.

**What these parameters mean:**

- `allow_origins=["http://localhost:3000", ...]` — the browser will let responses flow to these frontend URLs. From `.env`'s `CORS_ORIGINS`.
- `allow_credentials=True` — allow cookies / auth headers to be sent cross-origin.
- `allow_methods=["*"]` — any HTTP method is fine.
- `allow_headers=["*"]` — any request header is fine (we need this for `X-API-Key`).

> ⚠️ In production, `allow_origins=["*"]` with `allow_credentials=True` is **forbidden by browsers** (it's a security hole). You must list explicit origins.

---

### Block 5 — Global Exception Handlers

```python
@app.exception_handler(ValueError)
async def value_error_handler(request: Request, exc: ValueError) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content={"detail": str(exc)},
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request, exc):
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={"detail": "Request validation failed", "errors": exc.errors()},
    )
```

**Why do we need a global `ValueError` handler?**

Services raise plain `ValueError("experiment name 'foo' already exists")`. Routers are *supposed* to catch them and convert to 400, but a developer could forget. Without this handler, an unhandled `ValueError` would bubble up to FastAPI's default handler, which returns a 500 ("Internal Server Error") — which is wrong (the client's input was bad, not the server's fault).

**This is a safety net.** It guarantees that **no** `ValueError` ever produces a 500.

**What the RequestValidationError handler does:**

Pydantic's auto-validation (e.g. for `EmailStr`, `Field(ge=0)`) raises `RequestValidationError` (a subclass of `ValidationError`). FastAPI already handles this with a 422 response, but we override it to:
- Wrap the message in a `detail` field (consistent with other errors)
- Expose the per-field errors so the frontend can highlight the bad field

**Other exception handlers** registered automatically by FastAPI itself (4 total at runtime):
- `HTTPException` — for `raise HTTPException(404, ...)`
- `RequestValidationError` — for Pydantic failures (we override)
- `WebSocketRequestValidationError` — for WebSocket payloads
- `ValueError` — for service-layer bugs (we add)

---

### Block 6 — The `/health` Endpoint

```python
@app.get("/health", tags=["health"], summary="Liveness / readiness check", ...)
def health() -> dict:
    return {
        "status": "ok",
        "app": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "debug": settings.DEBUG,
    }
```

**Three reasons this lives in `main.py` and not in a router:**

1. **No auth required** — load balancers can't easily send API keys. The auth dependency is applied at the **router** level, so `/health` is automatically exempt by being outside any router.
2. **No service layer** — it doesn't touch the DB or MLflow. Just returns metadata.
3. **No business logic** — a stable, always-200 contract that doesn't change as the app grows.

`include_in_schema=False` on the `/` endpoint (Block 8) is the same idea: keep the root out of the public API surface.

---

### Block 7 — Mounting the Routers

```python
api_v1_prefix = "/api/v1"

app.include_router(
    experiments_router,
    prefix=api_v1_prefix,
    dependencies=[Depends(get_current_user)],
)
app.include_router(runs_router,        prefix=api_v1_prefix, dependencies=[Depends(get_current_user)])
app.include_router(predictions_router, prefix=api_v1_prefix, dependencies=[Depends(get_current_user)])
app.include_router(models_router,      prefix=api_v1_prefix, dependencies=[Depends(get_current_user)])
```

**Three things are happening here, each with a purpose:**

#### a) `prefix="/api/v1"` — the API version

The full URL is `<prefix>/<router_prefix>/<route>`. The router's own internal prefix (`/experiments`) is preserved; we add `/api/v1` in front. So `GET /` in `experiments_router` becomes `GET /api/v1/experiments/`.

**Why `/api/v1`?** Versioning. If you ever need to make breaking changes, you can mount the same routers under `/api/v2` with different logic, and old clients keep working.

#### b) `dependencies=[Depends(get_current_user)]` — app-level auth

This is **app-level dependency injection**. Every route in this router will run `get_current_user` before its own code. If the dependency raises (e.g. `401 Unauthorized`), the route never even gets called.

**Why use app-level instead of decorating each route?**
Without this, you'd have to add `dependencies=[Depends(get_current_user)]` to **every single one of the 20 endpoints**. With it, you add it once per router. (The pattern works at the route level too — `dependencies=[...]` can go on `@app.get(...)` or `@router.get(...)`.)

#### c) The import path

```python
from backend.app.routers import (
    experiments_router, runs_router, predictions_router, models_router,
)
```

This is why Phase 5's `__init__.py` aliases the routers — `main.py` gets to use clean, unambiguous names without reaching into each individual file.

---

### Block 8 — The Root Endpoint + Dev Entrypoint

```python
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

if __name__ == "__main__":  # pragma: no cover
    import uvicorn
    uvicorn.run("backend.app.main:app", host="0.0.0.0", port=8000, reload=settings.DEBUG)
```

**`include_in_schema=False`** hides `/` from the Swagger UI — it's a friendly hello for humans hitting the URL directly, not a real API endpoint.

**The `if __name__ == "__main__":` block** lets you run `python -m backend.app.main` for a quick local dev, but **the canonical way to run is `uvicorn`** (shown in the docstring at the top of the file). The `pragma: no cover` tells coverage tools to ignore this block.

---

## 🧠 The Concepts You Should Understand

### 1. Middleware order

Middleware in Starlette/FastAPI runs in a **stack**. Requests flow **down** the stack (the last-added middleware runs first); responses flow **up**.

```
Request
  │
  ▼
CORS middleware   ← added 1st, runs LAST (outermost)
  │
  ▼
Exception middleware
  │
  ▼
Your route
  │
  ▼
Response
```

`CORSMiddleware` is outermost so CORS headers are added to **every** response — including error responses. If CORS were innermost, a 401 from `get_current_user` would have no CORS headers, and the browser would block the error message from reaching the frontend.

### 2. App-level vs. route-level dependencies

You can attach `Depends(...)` at three levels:

| Level | Example | Applies to |
|---|---|---|
| **App** | `app = FastAPI(dependencies=[...])` | Every route in the whole app |
| **Router** | `app.include_router(r, dependencies=[...])` | Every route in that router |
| **Route** | `@app.get("/", dependencies=[...])` | That one route |

We use **router-level** for `get_current_user` because `/health` and `/` should be public.

### 3. `Base.metadata.create_all()` vs. Alembic migrations

| | `create_all()` | Alembic |
|---|---|---|
| New table | ✅ Creates | ✅ Detected and migrated |
| Add column | ❌ Does nothing | ✅ `alembic revision --autogenerate` |
| Rename column | ❌ Does nothing | ✅ |
| Drop table | ❌ Does nothing | ✅ |
| Safe to run on prod | ✅ | ✅ (with care) |
| Reversible | ❌ | ✅ (`alembic downgrade -1`) |

**For an MVP learning project, `create_all()` is fine.** The `alembic/` directory is set up for the day you graduate to real migrations.

### 4. The `noqa: F401` and side-effect imports

```python
import backend.app.models  # noqa: F401  (side-effect import)
```

`# noqa: F401` tells the linter: "yes I know this looks unused, don't warn me". The import has a **side effect**: it loads the `models/` package, which imports `Experiment` and `Run`, which register themselves with `Base.metadata`. Without this side effect, `Base.metadata.create_all()` would create a database with **zero tables**.

### 5. The lifespan handler replaces `@app.on_event`

In old FastAPI:

```python
@app.on_event("startup")
async def startup(): ...
@app.on_event("shutdown")
async def shutdown(): ...
```

This is **deprecated** as of FastAPI 0.93+. The new way is the `lifespan` async context manager — one function with `yield` in the middle. It's strictly better because:
- Startup and shutdown are clearly **paired** (no risk of forgetting one)
- Resources opened in startup are **guaranteed** to be closed in shutdown (the `try`/`finally` is the `yield` itself)
- It composes nicely with other async libraries

### 6. Why masking credentials in the startup banner

```python
print(f"   Database: {settings.DATABASE_URL.split('@')[-1]}")   # mask creds
```

The full `DATABASE_URL` is `postgresql://user:password@host:5432/db`. The `split('@')[-1]` gives us `host:5432/db` — the part after the `@` — so we don't print the password to stdout. **In a real CI/CD log this is critical**: logs often end up in centralized systems with weaker access controls.

---

## 🔄 A Full Request Lifecycle (Phase 6 View)

```
GET /api/v1/experiments/   (X-API-Key: dev-key-12345)
   │
   ▼
┌──────────┐
│ CORS     │ ← Adds Access-Control-* headers to response
└────┬─────┘
     │
     ▼
┌──────────┐
│ Errors   │ ← Wraps in try/except, runs our ValueError handler if needed
└────┬─────┘
     │
     ▼
┌────────────────────────────┐
│ FastAPI routing            │
│  Matches /api/v1/experiments/
│  to experiments_router     │
└────┬───────────────────────┘
     │
     ▼
┌────────────────────────────┐
│ Router-level dependency:   │
│   Depends(get_current_user)│  ← Phase 2's APIKeyHeader
│   • Reads X-API-Key        │
│   • Validates against list │
│   • Returns APIUser        │
└────┬───────────────────────┘
     │ (now 401 short-circuits, or...)
     │
     ▼
┌────────────────────────────┐
│ list_experiments()         │  ← Phase 5's router
│   payload = Pydantic(...)  │  ← Phase 3
│   db = Depends(get_db)     │  ← Phase 1
│   service.list_experiments() │  ← Phase 4
│   return ExperimentResponse[] │  ← Phase 3
└────┬───────────────────────┘
     │
     ▼
  Response: 200 JSON
```

---

## ✅ How to Verify Phase 6 Works

**Test 1 — App imports:**

```python
>>> from backend.app.main import app
>>> app.title
'ML Experiment Tracker'
>>> len(app.routes)
26          # 20 API + /health + / + openapi + docs + redoc
```

**Test 2 — OpenAPI has 15 unique paths:**

```python
>>> spec = app.openapi()
>>> len(spec['paths'])
15          # /health + 14 API paths
```

**Test 3 — End-to-end via TestClient:**

```python
>>> from fastapi.testclient import TestClient
>>> client = TestClient(app)

>>> client.get('/health').json()
{'status': 'ok', 'app': 'ML Experiment Tracker', 'version': '0.1.0', 'debug': True}

>>> client.get('/api/v1/experiments/').status_code
401      # missing X-API-Key

>>> client.get('/api/v1/experiments/', headers={'X-API-Key': 'dev-key-12345'}).status_code
200 or 500    # 200 if DB is up; 500 if DB is down (auth passed either way)

>>> client.get('/api/v1/experiments/', headers={'X-API-Key': 'wrong'}).status_code
401      # invalid key
```

**Test 4 — Real server (requires Postgres running):**

```bash
cd backend && uvicorn app.main:app --reload
# → Visit http://localhost:8000/docs and try it interactively
```

---

## 🧩 Where Phase 6 Fits in the Big Picture

```
            main.py  (Phase 6)
                 │
                 │  constructs + wires
                 ▼
┌──────────────────────────────────────────┐
│           FastAPI Application            │
│  ┌────────────────────────────────────┐  │
│  │ CORS middleware                    │  │
│  │ Exception middleware               │  │
│  │ Lifespan (startup/shutdown)        │  │
│  │ Auth dependency (get_current_user) │  │
│  └────────────────────────────────────┘  │
│  ┌────────────────────────────────────┐  │
│  │ Routers (Phase 5)                  │  │
│  │  /experiments/*   /runs/*          │  │
│  │  /predictions/*   /models/*        │  │
│  └────────┬───────────────────────────┘  │
│           │ calls                          │
│  ┌────────▼───────────────────────────┐  │
│  │ Services (Phase 4)                 │  │
│  │  experiment_service                │  │
│  │  run_service                       │  │
│  │  prediction_service                │  │
│  │  mlflow_service                    │  │
│  └────────┬───────────────────────────┘  │
│           │ uses                           │
│  ┌────────▼───────────────────────────┐  │
│  │ Schemas (Phase 3) — Pydantic       │  │
│  │ Models (Phase 2) — SQLAlchemy      │  │
│  │ Database (Phase 1) — engine+session│  │
│  │ Config + Security (Phase 1-2)      │  │
│  └────────────────────────────────────┘  │
└──────────────────────────────────────────┘
                │
                ▼
        External systems
        ┌──────────┐ ┌────────┐ ┌────────┐
        │PostgreSQL│ │ MLflow │ │ MinIO  │
        └──────────┘ └────────┘ └────────┘
```

**Before Phase 6**, all the layers existed but nothing tied them together. **`main.py` is the conductor of the orchestra** — every section is ready, the conductor just cues the downbeat.

---

## 📊 The Complete Route Table (After Phase 6)

| Method | Path | Auth | Source |
|---|---|---|---|
| `GET` | `/` | ❌ | main.py |
| `GET` | `/health` | ❌ | main.py |
| `GET` | `/docs` | ❌ | FastAPI built-in |
| `GET` | `/openapi.json` | ❌ | FastAPI built-in |
| `GET` | `/api/v1/experiments/` | ✅ | routers/experiments.py |
| `GET` | `/api/v1/experiments/count` | ✅ | routers/experiments.py |
| `GET` | `/api/v1/experiments/{id}` | ✅ | routers/experiments.py |
| `POST` | `/api/v1/experiments/` | ✅ | routers/experiments.py |
| `PATCH` | `/api/v1/experiments/{id}` | ✅ | routers/experiments.py |
| `DELETE` | `/api/v1/experiments/{id}` | ✅ | routers/experiments.py |
| `GET` | `/api/v1/runs/` | ✅ | routers/runs.py |
| `GET` | `/api/v1/runs/count` | ✅ | routers/runs.py |
| `POST` | `/api/v1/runs/` | ✅ | routers/runs.py |
| `GET` | `/api/v1/runs/{id}` | ✅ | routers/runs.py |
| `PATCH` | `/api/v1/runs/{id}` | ✅ | routers/runs.py |
| `DELETE` | `/api/v1/runs/{id}` | ✅ | routers/runs.py |
| `POST` | `/api/v1/runs/{id}/metrics` | ✅ | routers/runs.py |
| `POST` | `/api/v1/runs/{id}/parameters` | ✅ | routers/runs.py |
| `POST` | `/api/v1/runs/{id}/finish` | ✅ | routers/runs.py |
| `POST` | `/api/v1/predictions/predict` | ✅ | routers/predictions.py |
| `GET` | `/api/v1/predictions/models` | ✅ | routers/predictions.py |
| `GET` | `/api/v1/models/` | ✅ | routers/models.py |
| `GET` | `/api/v1/models/{name}` | ✅ | routers/models.py |
| `GET` | `/api/v1/models/{name}/latest` | ✅ | routers/models.py |

**Total: 24 reachable paths, 20 protected API endpoints, 4 public utility endpoints.**

---

## 📋 Files Inventory

| File | Lines | Purpose |
|---|---|---|
| `backend/app/main.py` | 244 | The FastAPI app, CORS, exception handlers, /health, router mounting, lifespan |

**Phase 6 ships one file that touches everything.**

---

## 🚀 What's Next (Phase 7 — Auth + Tests + Frontend)

Three parallel tracks typically follow:

### 7a. Alembic migrations

Replace `Base.metadata.create_all()` with versioned migrations so you can change column types, rename tables, etc., without dropping data.

### 7b. Pytest test suite

Write unit tests for each service (no DB), integration tests for each router (test DB), and contract tests for the OpenAPI spec.

### 7c. Frontend integration

The React app at `frontend/src/` will start calling these 20 endpoints. CORS is already configured to allow `http://localhost:3000`, so the first call should "just work" once both servers are running.

### 7d. Documentation polish

- Add `BACKEND_README.md` with `curl` examples for each endpoint
- Add `DEPLOYMENT.md` with Docker + nginx config
- Generate a Postman collection from the OpenAPI spec

To run the server **right now**:

```bash
cd backend && uvicorn app.main:app --reload
# Then: open http://localhost:8000/docs
# Use header X-API-Key: dev-key-12345 (or whatever's in your .env)
```
