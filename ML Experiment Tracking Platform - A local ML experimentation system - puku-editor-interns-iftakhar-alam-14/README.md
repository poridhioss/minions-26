# 🧠 ML Experiment Tracking Platform

An **end-to-end ML training, tracking, and deployment platform** — similar in spirit to MLflow, Weights & Biases, or Neptune.ai. Train models, log experiments, compare runs, and serve predictions through a REST API and web UI.

> **Internship project** — built with FastAPI, PostgreSQL, MLflow, MinIO, React, and NGINX.

---

## � Screenshots

| | |
|:---:|:---:|
| ![Dashboard](image/01-dashboard.png) | ![Experiments](image/02-experiments.png) |
| **Dashboard** | **Experiments** |
| ![Runs](image/03-runs.png) | ![Models](image/04-models.png) |
| **Runs** | **Models** |
| ![Predictions](image/05-predictions.png) | |
| **Predictions** | |

---

## �📑 Table of Contents

1. [What Does This Project Do?](#-what-does-this-project-do)
2. [High-Level Architecture](#-high-level-architecture)
3. [Component Responsibilities](#-component-responsibilities)
4. [Folder Structure](#-folder-structure)
5. [Data Flow Walkthrough](#-data-flow-walkthrough)
6. [The Database Schema](#-the-database-schema)
7. [Tech Stack](#-tech-stack)
8. [Setup & Installation](#-setup--installation)
9. [Running the Project](#-running-the-project)
10. [Using the API](#-using-the-api)
11. [Using the Python SDK](#-using-the-python-sdk)
12. [Phase-by-Phase Build Log](#-phase-by-phase-build-log)
13. [Glossary](#-glossary)

---

## 🎯 What Does This Project Do?

Imagine a data scientist wants to build a model that predicts house prices. They might try:

| Run | Model | Learning Rate | Accuracy |
|---|---|---|---|
| 1 | Random Forest | — | 0.87 |
| 2 | XGBoost | 0.01 | 0.91 |
| 3 | XGBoost | 0.005 | 0.93 |

This platform gives them a **central place** to:
- 📝 Register these experiments and runs
- 📊 Log metrics and hyperparameters for each run
- 💾 Store the trained model files
- 🔍 Compare runs side-by-side
- 🚀 Serve the best model via a prediction API
- 👀 See everything in a web dashboard

---

## 🏛️ High-Level Architecture

```
                         ┌─────────────────────┐
                         │   USER INTERFACES   │
                         └─────────────────────┘
                          │                │
                  Browser │                │ Python code
                  (React) │                │ (SDK)
                          ▼                ▼
                ┌──────────────────────────────────────┐
                │           NGINX (port 80)            │
                │         Reverse proxy / static       │
                └──────────┬─────────────────┬─────────┘
                           │ /api/*         │ /*
                           ▼                ▼
              ┌──────────────────┐  ┌──────────────────┐
              │ FastAPI (8000)   │  │ React (built)    │
              │   THE BACKEND    │  │   THE FRONTEND   │
              └────────┬─────────┘  └──────────────────┘
                       │
        ┌──────────────┼────────────────┐
        │              │                │
        ▼              ▼                ▼
  ┌──────────┐  ┌──────────┐     ┌──────────┐
  │PostgreSQL│  │  MLflow  │────►│  MinIO   │
  │  (5432)  │  │  (5000)  │     │(9000/9001)│
  │ Metadata │  │ Metrics  │     │ Artifacts│
  └──────────┘  └──────────┘     └──────────┘
```

### 5 Big Pieces

| Piece | What It Does | Port |
|---|---|---|
| **NGINX** | Single public entry; routes `/api/*` to backend, everything else to React | 80 |
| **FastAPI** | Receives API calls, runs business logic, returns JSON | 8000 |
| **PostgreSQL** | Stores experiment/run metadata (our "system of record") | 5432 |
| **MLflow** | Specialized tracking for ML: metrics history, parameters, model versions | 5000 |
| **MinIO** | S3-compatible object storage for large files (model `.pkl`, plots, datasets) | 9000/9001 |

---

## 🧩 Component Responsibilities

### Backend (`backend/app/`)

```
app/
├── database.py          ← SQLAlchemy engine + session factory
│
├── models/              ← DB TABLES (how data is stored)
│   ├── experiment.py    ←   experiments table
│   └── run.py           ←   runs table
│
├── schemas/             ← API VALIDATION (how data travels in/out)
│   ├── experiment.py    ←   Pydantic models for experiment I/O
│   └── run.py           ←   Pydantic models for run I/O
│
├── core/                ← FOUNDATION (settings + security)
│   ├── config.py        ←   Loads .env, exposes typed Settings object
│   └── security.py      ←   API-key authentication
│
├── services/            ← BUSINESS LOGIC (the "brain")
│   ├── experiment_service.py  ← CRUD + rules for experiments
│   ├── run_service.py         ← CRUD + log metrics/params
│   ├── mlflow_service.py      ← Talks to MLflow server
│   └── prediction_service.py  ← Loads model + runs inference
│
├── routers/             ← URL ENDPOINTS (the "doors" of the API)
│   ├── experiments.py    ←   /api/v1/experiments
│   ├── runs.py           ←   /api/v1/runs
│   └── predictions.py    ←   /api/v1/predict
│
└── main.py              ← APP ENTRY POINT (wires everything together)
```

### Request Lifecycle (the "Router → Schema → Service → Model" pattern)

```
HTTP POST /api/v1/experiments
        │
        ▼
   ┌──────────┐
   │  Router  │  ← Matches URL, receives request
   └────┬─────┘
        │ ① Check X-API-Key header (security)
        ▼
   ┌──────────┐
   │ Security │  ← Returns APIUser or raises 401
   └────┬─────┘
        │ ② Pass JSON body to schema
        ▼
   ┌──────────┐
   │  Schema  │  ← Validates types; raises 422 on bad input
   └────┬─────┘
        │ ③ Call service with validated data
        ▼
   ┌──────────┐
   │ Service  │  ← Business rules, orchestrates DB + MLflow + MinIO
   └────┬─────┘
        │ ④ SQL query
        ▼
   ┌──────────┐
   │  Model   │  ← SQLAlchemy ORM writes to PostgreSQL
   └────┬─────┘
        │ ⑤ Return ORM object
        ▼
   ┌──────────┐
   │  Schema  │  ← Convert ORM → JSON via Pydantic
   └────┬─────┘
        ▼
   HTTP 201 Created + JSON body
```

---

## 📂 Folder Structure

```
ml-tracker/
├── backend/                        ← FastAPI backend
│   ├── requirements.txt            ← Python dependencies
│   ├── alembic/                    ← DB migration tool
│   │   └── versions/               ←   Individual migration scripts
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py                 ← FastAPI app entry point
│   │   ├── database.py             ← DB connection
│   │   ├── core/                   ← Config + security
│   │   ├── models/                 ← SQLAlchemy ORM models
│   │   ├── schemas/                ← Pydantic validation
│   │   ├── services/               ← Business logic
│   │   └── routers/                ← API endpoints
│   ├── ml/                         ← Training & inference scripts
│   └── tests/                      ← Pytest unit tests
│
├── frontend/                       ← React dashboard
│   └── src/
│       ├── api/                    ← HTTP client
│       ├── components/             ← Reusable UI
│       └── pages/                  ← Full pages
│
├── nginx/                          ← Reverse proxy config
│
├── sdk/
│   └── mltracker/                  ← Python client library
│
├── .env                            ← Secrets & config (NEVER commit!)
└── README.md                       ← This file
```

---

## 🔄 Data Flow Walkthrough

### Example A: Creating an Experiment (Write)

```
1. SDK:   mltracker.create_experiment("house-prices")
            │
2. SDK:   POST /api/v1/experiments
            body: {"name": "house-prices", "description": "..."}
            headers: {"X-API-Key": "dev-key-12345"}
            │
3. Router: experiments.create_experiment()
            │
4. Security: validates X-API-Key against .env → ✅
            │
5. Schema: ExperimentCreate validates body → name is required string ≤ 255 chars
            │
6. Service: experiment_service.create_experiment(db, payload)
            │
7. Model:  INSERT INTO experiments (name, description) VALUES (...)
            │
8. PostgreSQL: returns new row with id=1, created_at=...
            │
9. Response: 201 Created
             {"id": 1, "name": "house-prices", "created_at": "2026-06-08T..."}
```

### Example B: Logging a Metric (Write — with MLflow sync)

```
1. SDK:   run.log_metric("accuracy", 0.94, step=100)
            │
2. SDK:   POST /api/v1/runs/42/metrics
            body: {"key": "accuracy", "value": 0.94, "step": 100}
            │
3. Router: runs.log_metric_endpoint()
            │
4. Service: run_service.log_metric(db, 42, "accuracy", 0.94)
            │
            ├─► PostgreSQL: UPDATE runs SET metrics = '{"accuracy": 0.94}' WHERE id=42
            │
            └─► MLflow Server: POST /api/2.0/mlflow/runs/log-metric
                                 (records timestamped history for charting)
            │
5. Response: 200 OK
```

### Example C: Making a Prediction (Read — with model loading)

```
1. Browser: POST /api/v1/predict
             body: {"model_name": "rf-v1", "features": [3, 1500, 2]}
             │
2. Router: predictions.predict_endpoint()
             │
3. Service: prediction_service.predict(features, model_name="rf-v1")
             │
             ├─► MLflow Registry: "What's the latest version of rf-v1 in Production?"
             │     → returns: version 3, source "s3://bucket/3/model.pkl"
             │
             ├─► MinIO: download model.pkl (via MLflow)
             │
             ├─► Load: joblib.load(model.pkl) → sklearn model object
             │
             └─► Inference: model.predict([[3, 1500, 2]]) → [425000.0]
             │
4. Response: 200 OK
             {"prediction": 425000.0, "model_uri": "models:/rf-v1/3"}
```

---

## 🗄️ The Database Schema

```sql
CREATE TABLE experiments (
    id          SERIAL PRIMARY KEY,
    name        VARCHAR(255) UNIQUE NOT NULL,
    description TEXT,
    tags        TEXT,
    created_at  TIMESTAMPTZ DEFAULT NOW(),
    updated_at  TIMESTAMPTZ
);

CREATE TABLE runs (
    id            SERIAL PRIMARY KEY,
    experiment_id INTEGER REFERENCES experiments(id) ON DELETE CASCADE,
    run_name      VARCHAR(255),
    status        VARCHAR(50) DEFAULT 'RUNNING',     -- RUNNING | FINISHED | FAILED
    metrics       TEXT,                              -- JSON: {"accuracy": 0.94, ...}
    parameters    TEXT,                              -- JSON: {"lr": 0.01, ...}
    tags          TEXT,                              -- JSON
    artifact_uri  VARCHAR(500),                      -- s3://bucket/... or runs:/...
    start_time    TIMESTAMPTZ DEFAULT NOW(),
    end_time      TIMESTAMPTZ
);

-- One experiment → many runs (1:N)
```

**Why JSON in `TEXT` columns?** ML metrics/params are arbitrary key-value pairs. Storing them as JSON gives flexibility; PostgreSQL also has native `JSONB` for faster queries if needed later.

---

## 🛠️ Tech Stack

| Layer | Technology | Why |
|---|---|---|
| Backend framework | **FastAPI** | Async, auto-generates OpenAPI docs, fast |
| Validation | **Pydantic v2** | Type-safe schemas, integrates with FastAPI |
| ORM | **SQLAlchemy 2.0** | Industry standard, supports async |
| Database | **PostgreSQL** | Reliable, JSONB support, full-text search |
| ML tracking | **MLflow 3.x** | Purpose-built for ML experiments |
| Object storage | **MinIO** | S3-compatible, runs anywhere |
| Auth | **API Keys (X-API-Key header)** | Simple; can upgrade to JWT later |
| Frontend | **React + Vite** | Fast dev experience |
| Reverse proxy | **NGINX** | Industry standard, handles SSL |
| Containerization | **Docker + docker-compose** | One command to run everything |
| Migrations | **Alembic** | Version control for DB schema |

---

## ⚙️ Setup & Installation

### Prerequisites

- Python 3.10+
- Node.js 18+ (for frontend)
- PostgreSQL 14+ (or use Docker)
- Docker + docker-compose (recommended)

### 1. Clone & enter the project

```bash
cd "/path/to/ml-tracker"
```

### 2. Create a virtual environment

```bash
python -m venv venv
source venv/bin/activate          # Linux / macOS
# venv\Scripts\activate           # Windows
```

### 3. Install dependencies

```bash
pip install -r backend/requirements.txt
```

### 4. Configure environment

Edit the `.env` file at the project root. The defaults are:

```dotenv
DATABASE_URL=postgresql://mluser:mlpassword@localhost:5432/mltracker
SECRET_KEY=supersecretkey123-change-me-in-production
API_KEYS=dev-key-12345,test-key-67890
MLFLOW_TRACKING_URI=http://localhost:5000
MINIO_ENDPOINT=localhost:9000
MINIO_ACCESS_KEY=minioadmin
MINIO_SECRET_KEY=minioadmin
```

### 5. (Optional) Start supporting services with Docker

```bash
docker-compose up -d postgres minio mlflow
```

---

## 🚀 Running the Project

### Start the backend (development)

```bash
cd backend
uvicorn app.main:app --reload --port 8000
```

Visit:
- API: http://localhost:8000
- Interactive docs (Swagger UI): http://localhost:8000/docs
- Alternative docs (ReDoc): http://localhost:8000/redoc

### Start the frontend (development)

```bash
cd frontend
npm install
npm run dev
```

Visit http://localhost:3000

### Start everything with Docker (production-like)

```bash
docker-compose up
```

---

## 📡 Using the API

All endpoints require the `X-API-Key` header. Example with `curl`:

### Create an experiment

```bash
curl -X POST http://localhost:8000/api/v1/experiments \
  -H "X-API-Key: dev-key-12345" \
  -H "Content-Type: application/json" \
  -d '{"name": "house-prices", "description": "Predict house prices"}'
```

### List all experiments

```bash
curl http://localhost:8000/api/v1/experiments \
  -H "X-API-Key: dev-key-12345"
```

### Create a run

```bash
curl -X POST http://localhost:8000/api/v1/runs \
  -H "X-API-Key: dev-key-12345" \
  -H "Content-Type: application/json" \
  -d '{
    "experiment_id": 1,
    "run_name": "random-forest-v1",
    "parameters": {"n_estimators": 100, "max_depth": 10},
    "metrics": {"accuracy": 0.87}
  }'
```

### Make a prediction

```bash
curl -X POST http://localhost:8000/api/v1/predict \
  -H "X-API-Key: dev-key-12345" \
  -H "Content-Type: application/json" \
  -d '{
    "model_name": "rf-v1",
    "features": [3, 1500, 2]
  }'
```

---

## 🐍 Using the Python SDK

```python
from mltracker import Client

client = Client(api_key="dev-key-12345", base_url="http://localhost:8000")

# Create an experiment
exp = client.create_experiment("house-prices")

# Start a run
run = client.start_run(experiment_id=exp.id, run_name="rf-v1")

# Log hyperparameters
run.log_params({"n_estimators": 100, "max_depth": 10})

# Log metrics (multiple times during training)
for epoch in range(10):
    run.log_metric("loss", 0.1 / (epoch + 1), step=epoch)

# Finish
run.finish()

# Make a prediction
prediction = client.predict("rf-v1", features=[3, 1500, 2])
print(prediction)
```

---

## 📋 Phase-by-Phase Build Log

| Phase | What | Files | Status |
|---|---|---|---|
| 1 | Project skeleton + venv | `backend/`, `frontend/`, `.env` | ✅ |
| 2 | DB models | `models/experiment.py`, `models/run.py` | ✅ |
| 3 | API schemas | `schemas/experiment.py`, `schemas/run.py` | ✅ |
| 4 | Services (business logic) | `services/*.py` (4 files) | ✅ |
| 5 | Routers (API endpoints) | `routers/experiments.py`, `runs.py`, `predictions.py` | ✅ |
| 6 | FastAPI main app | `main.py` | ✅ |
| 7 | Alembic migrations | `alembic/versions/...` | ✅ |
| 8 | ML training scripts | `ml/train.py`, `ml/predict.py`, `ml/sample_data.py` | ✅ |
| 9 | Tests | `tests/conftest.py`, `tests/test_*.py` (47 tests) | ✅ |
| 10 | Docker | `Dockerfile`, `docker-compose.yml`, `nginx.conf`, `entrypoint.sh` | ✅ |
| 11 | React frontend | `frontend/src/...` | ✅ |
| 12 | Python SDK | `sdk/mltracker/...` | ✅ |

---

## 📖 Glossary

| Term | Meaning |
|---|---|
| **Experiment** | A named project (e.g. "house-prices") that groups related runs |
| **Run** | A single execution of training code, with its own params, metrics, and model |
| **Metric** | A number logged over time, e.g. accuracy, loss |
| **Parameter** | A hyperparameter set before training, e.g. learning_rate |
| **Artifact** | A file produced during training, e.g. `model.pkl`, `plot.png` |
| **MLflow** | A specialized tool for tracking ML experiments |
| **MinIO** | An S3-compatible object store for large files |
| **ORM** | Object-Relational Mapping — lets you use Python objects instead of raw SQL |
| **Schema** | In Pydantic: a class that defines the shape of API input/output |
| **Service** | The business-logic layer between routers and data |
| **Router** | Defines URL endpoints (e.g. `GET /experiments`) |
| **Migration** | A version-controlled change to the DB schema (like Git for databases) |
| **Singleton** | A pattern where only ONE instance of an object exists (e.g. `settings`) |
| **CORS** | Cross-Origin Resource Sharing — lets the frontend (port 3000) call the backend (port 8000) |

---

## 📜 License

This is an internship project — for educational purposes.

---

# 📖 Complete Operator Guide

A consolidated, copy-pasteable guide to the entire repository — quick start, the three ways to run an experiment, the three ways to track it, the SDK, the test suites, and troubleshooting.

## What this repo actually contains

| Path | What it does |
|---|---|
| `backend/` | FastAPI service exposing `/api/v1/...` for experiments, runs, models, predictions. Logs everything to MLflow; stores artifacts in MinIO. |
| `frontend/` | React + Vite + TypeScript dashboard for browsing experiments/runs/models and calling the predict endpoint. |
| `mlflow-image/` | Custom MLflow image with `psycopg2-binary` + `boto3` for the Postgres backend store + S3 artifact store. |
| `sdk/mltracker/` | Typed Python client that mirrors the API (`mltracker.experiments.list()`, `mltracker.predictions.predict(...)`). |
| `nginx/` | Production reverse proxy + static frontend host. |
| `phases/` | Build-phase notes for each subsystem. |

---

## 🚀 Quick start (TL;DR)

```bash
# 1. Clone & enter
cd ml-tracker

# 2. Configure env (defaults are fine for local dev)
cat .env

# 3. Bring up Postgres + MinIO + MLflow + Backend + Nginx
docker compose up -d --build

# 4. (Only once, per fresh MinIO data volume) create the artifacts bucket
docker compose exec minio mc alias set local http://localhost:9000 minioadmin minioadmin
docker compose exec minio mc mb local/artifacts || true

# 5. (Dev only) install frontend deps and start the dev server with hot reload
cd frontend
npm install
npm run dev
```

Open:

- React UI: **http://localhost:5173** (dev) or **http://localhost** (prod via nginx)
- FastAPI docs: **http://localhost:8000/docs**
- MLflow UI: **http://localhost:5000**
- MinIO console: **http://localhost:9001** (`minioadmin` / `minioadmin`)

---

## ⚙️ Setup & installation

### Prerequisites

- **Docker** + **docker compose** v2 (recommended — runs everything)
- Python 3.10+ (only if you want to run scripts on the host instead of inside containers)
- Node.js 18+ (only if you want the React dev server with hot reload)

### 1. Clone & enter the project

```bash
cd "/path/to/ml-tracker"
```

### 2. Configure environment

The `.env` file at the project root drives both the host scripts and the Docker containers. Defaults work for local dev:

```dotenv
DATABASE_URL=postgresql://mluser:mlpassword@localhost:5432/mltracker
SECRET_KEY=supersecretkey123-change-me-in-production
API_KEYS=dev-key-12345,test-key-67890
MLFLOW_TRACKING_URI=http://localhost:5000
MLFLOW_ARTIFACT_ROOT=s3://artifacts/
MINIO_ENDPOINT=localhost:9000
MINIO_ACCESS_KEY=minioadmin
MINIO_SECRET_KEY=minioadmin
MINIO_BUCKET=artifacts
MINIO_SECURE=false
CORS_ORIGINS=http://localhost:3000,http://localhost:5173
```

`API_KEYS` is a comma-separated allowlist. The first value is also what the frontend / SDK picks up when no `X-API-Key` is configured.

### 3. (Local dev only) Python + Node

```bash
python -m venv venv
source venv/bin/activate
pip install -r backend/requirements.txt

cd frontend
npm install
cd ..
```

---

## ▶️ Running the project

You have two options: run everything in Docker (production-like), or mix Docker infra with host-based dev servers for hot reload.

### Option A — Full Docker (production-like)

```bash
docker compose up -d --build
docker compose ps
```

This brings up:

| Service  | Container            | Port (host)       | Purpose                                       |
|----------|----------------------|-------------------|-----------------------------------------------|
| postgres | `mltracker-postgres` | `5432`            | Primary DB for experiments & runs             |
| minio    | `mltracker-minio`    | `9000` / `9001`   | S3-compatible artifact store (+ web console)  |
| mlflow   | `mltracker-mlflow`   | `5000`            | Tracking server + UI                          |
| backend  | `mltracker-backend`  | `8000` (internal) | FastAPI app, exposed via nginx only           |
| nginx    | `mltracker-nginx`    | `80`              | Reverse proxy + serves `frontend/dist/`       |

Then build the frontend bundle so nginx has files to serve:

```bash
cd frontend && npm install && npm run build && cd ..
docker compose restart nginx
```

Open **http://localhost**.

### Option B — Hybrid: Docker infra + host dev servers (day-to-day)

```bash
# 1. Start only the infra in Docker
docker compose up -d postgres minio mlflow

# 2. Backend on the host (with hot reload)
set -a; source .env; set +a
uvicorn app.main:app --reload --port 8000 --app-dir backend
# → http://localhost:8000

# 3. Frontend dev server on the host (Vite HMR + API proxy)
cd frontend
npm run dev
# → http://localhost:5173  (proxies /api/v1/* to :8000)
```

Stop everything:

```bash
# Host processes
pkill -f 'uvicorn app.main'   # backend
pkill -f 'vite'                # frontend

# Docker
docker compose down             # stop
docker compose down -v          # stop + delete volumes (wipes data)
```

---

## 🧪 Running an experiment

### A. From the CLI (`backend/ml/train.py`)

Trains a `RandomForestClassifier` on the Iris dataset, logs params + metrics to MLflow, uploads the pickled model to MinIO, and registers it in the Model Registry:

```bash
set -a; source .env; set +a
python -m backend.ml.train \
  --experiment-name iris-baseline \
  --run-name rf-v1 \
  --n-estimators 100 \
  --max-depth 5
```

What gets logged:

- **Params**: `n_estimators`, `max_depth`, `criterion`, … (sklearn auto-logging).
- **Metrics**: `accuracy`, `precision_macro`, `recall_macro`, `f1_macro`.
- **Artifact**: pickled model under `model/`.
- **Registry**: creates/updates `iris-baseline` → v1.

Predict with it:

```bash
python -m backend.ml.predict \
  --model-name iris-baseline \
  --features 5.1 3.5 1.4 0.2
# → {"model_name":"iris-baseline","model_version":1,"prediction":0,"confidence":0.95,...}
```

### B. From the Python SDK

```python
from mltracker import MLTrackerClient

client = MLTrackerClient(url="http://localhost:8000", api_key="dev-key-12345")

# List experiments
for exp in client.experiments.list():
    print(exp.id, exp.name)

# Inspect runs in an experiment
for run in client.runs.list(experiment_id=1):
    print(run.id, run.status, run.metrics)

# List registered models and their versions
for model in client.models.list():
    for v in client.models.versions(model.name):
        print(model.name, v.version, v.current_stage)

# Predict against the Production version
result = client.predictions.predict(
    features=[5.1, 3.5, 1.4, 0.2],
    model_name="iris-baseline",
    stage="Production",
)
print(result.prediction, result.confidence)
```

Or, equivalently, with the singleton helpers:

```python
import mltracker
mltracker.login("http://localhost:8000", api_key="dev-key-12345")
mltracker.experiments.list()
```

### C. From the REST API directly

All endpoints live under `http://localhost:8000/api/v1/` and require header `X-API-Key: <one of API_KEYS>`.

```bash
KEY=$(grep ^API_KEYS= .env | cut -d= -f2- | cut -d, -f1)

# List experiments
curl -H "X-API-Key: $KEY" http://localhost:8000/api/v1/experiments

# List runs in an experiment
curl -H "X-API-Key: $KEY" "http://localhost:8000/api/v1/runs/?experiment_id=1"

# List registered models + versions + stages
curl -H "X-API-Key: $KEY" http://localhost:8000/api/v1/models

# Predict (uses Production version by default)
curl -H "X-API-Key: $KEY" -H "Content-Type: application/json" \
  -d '{"model_name":"iris-baseline","features":[5.1,3.5,1.4,0.2]}' \
  http://localhost:8000/api/v1/predictions/predict
```

### D. From the React UI

1. Open **http://localhost:5173** (dev) or **http://localhost** (prod).
2. The first screen asks for an API key — paste `dev-key-12345` (or any value from `API_KEYS`).
3. The sidebar has four pages:

   | Page | What it shows |
   |---|---|
   | **Experiments** | All MLflow experiments with run counts. |
   | **Runs** | Runs in a chosen experiment; click a run → params/metrics/artifacts. |
   | **Models** | Registered models, versions, and their stage (Production highlighted). |
   | **Predictions** | Form: pick a model, type comma-separated features → calls `/predictions/predict`. |

---

## 🔍 Tracking experiments

The same data is visible in three places — pick whichever is most convenient.

### 1. MLflow UI — http://localhost:5000

Source of truth. Use it for:

- Comparing metrics across runs (parallel coordinates, scatter plots).
- Inspecting artifacts (pickled model, signature, conda env).
- Promoting a version to a stage: open a model version → **Stage** dropdown → `Production` / `Staging` / `Archived`.

### 2. MinIO console — http://localhost:9001

`minioadmin` / `minioadmin`. Browse the `artifacts/` bucket to see raw MLflow artifact uploads (models, plots, signature JSON, etc.).

### 3. React UI — http://localhost:5173 (or http://localhost)

Operator-friendly view of the same MLflow data, plus a one-click prediction form.

### Quick reference card

| Service        | URL                                                | Auth                          |
|----------------|----------------------------------------------------|-------------------------------|
| Frontend       | http://localhost:5173 (dev) / http://localhost (prod) | API key in `localStorage`     |
| Backend (API)  | http://localhost:8000                              | header `X-API-Key`            |
| Backend (docs) | http://localhost:8000/docs                         | none (Swagger UI)             |
| MLflow UI      | http://localhost:5000                              | none (local)                  |
| MinIO console  | http://localhost:9001                              | `minioadmin` / `minioadmin`   |
| Postgres       | `localhost:5432`                                   | `mluser` / `mlpassword` / `mltracker` |

---

## 🧑‍💻 Development workflow

### Run the test suites

```bash
# Backend
cd backend
PYTHONPATH=. pytest -q
PYTHONPATH=. pytest --cov=app tests/   # with coverage

# SDK
cd sdk
PYTHONPATH=. pytest -q
```

### Common dev tasks

| Task | Command |
|---|---|
| Rebuild a single service | `docker compose build backend && docker compose up -d backend` |
| Tail backend logs | `docker compose logs -f backend` |
| Open psql in postgres | `docker compose exec postgres psql -U mluser -d mltracker` |
| Open a shell in the backend container | `docker compose exec backend bash` |
| Reset everything (⚠️ deletes data) | `docker compose down -v` |
| New Alembic migration | `cd backend && alembic revision --autogenerate -m "msg"` |
| Apply migrations | `cd backend && alembic upgrade head` |

---

## 🛠️ Troubleshooting

**`botocore.exceptions.NoCredentialsError` when calling `/predictions/predict`**
The backend can't reach MinIO. Make sure you started it with the env vars from `.env` loaded (`set -a; source .env; set +a`) or via Docker Compose which does that for you.

**`NoSuchBucket: artifacts` from MLflow**
The MinIO bucket hasn't been created yet. Run the `mc mb local/artifacts` step from the Quick Start, or the next training run will create it via the SDK.

**Frontend shows "401 Unauthorized" everywhere**
You haven't set an API key yet. Open the UI's first screen and paste a value from `API_KEYS`, or call `mltracker.login(url, api_key=...)` from the SDK.

**Port conflicts**
`docker compose ps` shows what's bound. The defaults are `80` (nginx), `443`, `3000`, `5000` (MLflow), `5173` (Vite dev), `5432` (postgres), `8000` (backend), `9000`/`9001` (MinIO).

**Vite dev server can't reach the backend**
The dev server proxies `/api/v1/*` to `http://localhost:8000`. Make sure the backend is up there. With `vite preview` or the production nginx setup, the proxy path is different — prefer `npm run dev` for local development.
# ml-tracker
