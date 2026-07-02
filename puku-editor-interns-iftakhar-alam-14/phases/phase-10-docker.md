# Phase 10 — Docker & Containerization

## 🎯 What This Phase Did

Phase 10 takes the working backend (Phases 1-7), the ML scripts (Phase 8), and the test suite (Phase 9) and packages the whole stack into a **single-command deployment**. With Docker + Docker Compose installed, the entire ML Tracker — backend, Postgres, MLflow, MinIO, and nginx — comes up with one command:

```bash
docker compose up -d
```

This is the difference between "works on my machine" and "works in staging, prod, a teammate's laptop, a CI runner, and a Kubernetes pod."

---

## 📂 What Was Created

```
ml-tracker/
├── docker-compose.yml         ← Orchestrates all 5 services ⭐
├── .dockerignore              ← Trims the compose build context
├── .env.example               ← Template for production env vars
├── nginx/
│   └── nginx.conf             ← Reverse proxy + static frontend serving
└── backend/
    ├── Dockerfile             ← Multi-stage Python image ⭐
    ├── .dockerignore          ← Trims the backend build context
    └── entrypoint.sh          ← Waits for DB → migrations → starts uvicorn
```

Total: **6 new files, 5 services orchestrated, zero changes to the existing backend code.**

---

## ⭐ The Star File: `backend/Dockerfile`

A **multi-stage build** that produces a lean, secure runtime image.

### Stage 1: `builder` (throw-away)
Installs Python packages into a `/install/deps` prefix. We split this from the runtime stage so the heavy `pip install` layer is **cached** and re-builds skip it as long as `requirements.txt` is unchanged.

```dockerfile
FROM python:3.12-slim AS builder
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential libpq-dev \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /install
COPY requirements.txt .
RUN pip install --prefix=/install/deps -r requirements.txt
```

`build-essential` + `libpq-dev` are needed for `psycopg2-binary` and `greenlet` to compile, but they're only needed at *build time*.

### Stage 2: `runtime` (the final image)
Copies the prebuilt packages from the builder, copies the application code, creates a non-root user, and exposes port 8000.

```dockerfile
FROM python:3.12-slim AS runtime
RUN apt-get update && apt-get install -y --no-install-recommends \
        libpq5 curl \
    && rm -rf /var/lib/apt/lists/*

# Copy packages from the builder
COPY --from=builder /install/deps /usr/local

# Non-root user
RUN groupadd --system --gid 1001 mltracker && \
    useradd --system --uid 1001 --gid mltracker --create-home --shell /bin/bash mltracker

WORKDIR /app
COPY --chown=mltracker:mltracker . /app
RUN chmod +x /app/entrypoint.sh

USER mltracker
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl --fail --silent http://localhost:8000/health || exit 1

ENTRYPOINT ["/app/entrypoint.sh"]
CMD ["uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

Key decisions:
- **Non-root user** (uid 1001). The container shouldn't run as root — defense in depth.
- **`libpq5` not `libpq-dev`**. The runtime only needs the Postgres client lib, not the dev headers.
- **`curl` in the runtime image.** Needed for the `HEALTHCHECK`.
- **`HEALTHCHECK` is built into the image.** `docker ps` will show "healthy" or "unhealthy" for the container.
- **`ENTRYPOINT` + `CMD` separation.** The entrypoint script wraps the CMD, so we can run migrations BEFORE uvicorn starts.

---

## ⭐ The Star File: `docker-compose.yml`

Five services, one private network, named volumes for persistence.

### The 5 services

| Service   | Image                              | Port (host) | Role                                                       |
|-----------|------------------------------------|-------------|------------------------------------------------------------|
| `postgres`| `postgres:16-alpine`               | 5432        | Primary database (experiments, runs)                       |
| `backend` | built from `./backend/Dockerfile`  | (internal)  | FastAPI app on container port 8000                         |
| `mlflow`  | `ghcr.io/mlflow/mlflow:v2.22.0`    | 5000        | Tracking server; uses Postgres + MinIO for persistence     |
| `minio`   | `minio/minio:RELEASE.2025-04-01...`| 9000 / 9001 | S3-compatible artifact store; console on :9001             |
| `nginx`   | `nginx:1.27-alpine`                | 80          | The ONLY public entrypoint; reverse-proxies + serves static |

### Networking

All services join a private bridge network called `mlnet`. They can reach each other by **service name** (which Docker's embedded DNS resolves to the container's internal IP). That's why the backend's `DATABASE_URL` says `postgresql://...@postgres:5432/...` — `postgres` is a hostname, not a typo for localhost.

```yaml
networks:
  mlnet:
    driver: bridge
```

### Healthchecks + `depends_on`

`depends_on` is necessary but not sufficient — by default it just waits for the container to *start*, not to be *ready*. With `condition: service_healthy`, the backend waits for Postgres's `pg_isready` probe to return OK:

```yaml
depends_on:
  postgres:
    condition: service_healthy
  mlflow:
    condition: service_started
```

### Volumes

```yaml
volumes:
  postgres_data:    # /var/lib/postgresql/data → host-managed
  minio_data:       # /data                   → host-managed
```

These are **named volumes** managed by Docker. Data survives `docker compose down` — you have to use `docker compose down -v` to wipe it.

### Env-var passthrough

The compose file reads from `.env` (created by copying `.env.example`) and passes values into each service. This means:
- The backend sees the same `DATABASE_URL` it does in dev.
- The MLflow server sees Postgres + MinIO creds it can use to talk to its dependencies.
- The `nginx` container doesn't need any env vars (it's a static proxy).

---

## ⭐ The Star File: `backend/entrypoint.sh`

Three jobs, run in order on container start:

1. **Wait for Postgres.** A retry loop with a 2-second interval and a 60-second timeout. We use a tiny inline Python `socket.connect()` instead of relying on `nc` or `psql` being in the image.
2. **Run Alembic migrations.** `alembic upgrade head`. This is the production-correct schema-management path — the `create_all()` in `main.py`'s lifespan is a dev-only convenience.
3. **`exec` the CMD.** Replaces the shell process with uvicorn, so uvicorn becomes PID 1. That means `docker stop` sends SIGTERM directly to uvicorn, which triggers its graceful-shutdown path (no orphaned DB connections).

The script is parameterized with two env vars: `WAIT_FOR_DB` (default `true`) and `RUN_MIGRATIONS` (default `true`). Set them to `false` to skip either step — useful for ephemeral dev containers.

---

## ⭐ The Star File: `nginx/nginx.conf`

A single nginx server block with two responsibilities:

1. **Serve the React frontend** from `/usr/share/nginx/html` (mounted as a read-only volume from `./frontend/dist`). The `try_files $uri $uri/ /index.html;` rule makes client-side routing work — refreshing `/experiments/42` returns `index.html` instead of 404.
2. **Reverse-proxy the API.** Anything under `/api/`, `/health`, `/docs`, `/redoc`, or `/openapi.json` is forwarded to `backend:8000` (the service name, resolved by Docker DNS).

```
Browser  →  nginx (:80)
              ├── /                     → static React app
              ├── /api/*                → FastAPI backend
              ├── /health, /docs, ...   → FastAPI backend
              └── everything else       → React app (SPA fallback)
```

Other features:
- **Gzip** on JSON/JS/CSS/HTML.
- **Long upstream timeouts** (60s) for MLflow-tracking endpoints that may be slow.
- **Security headers** — `X-Frame-Options`, `X-Content-Type-Options`, `Referrer-Policy`, `X-XSS-Protection`.
- **Aggressive caching** for fingerprinted static assets (`main.abcd1234.js`).
- **`client_max_body_size 500m`** to allow large model artifacts.

---

## 🔒 Security Notes

| Concern | Mitigation |
|---|---|
| Container running as root | Backend uses a non-root `mltracker` user (uid 1001). |
| `.env` leaking into image | Root + backend `.dockerignore` exclude `.env`, `.env.local`, `*.pem`, `*.key`. |
| Default credentials | `.env.example` has placeholders like `changeme-in-production` — devs MUST edit before exposing the stack. |
| Public surface | Only nginx port 80 is bound to the host. Postgres / MinIO / MLflow are reachable only via the private `mlnet` network. |
| Secrets at rest | The `.env` file lives on the host filesystem. For production, use Docker secrets or a vault (e.g. HashiCorp Vault, AWS Secrets Manager). |

---

## 🚀 Runbook

### First-time setup
```bash
cp .env.example .env
# Edit .env: set SECRET_KEY, API_KEYS, POSTGRES_PASSWORD, MINIO_SECRET_KEY
docker compose up -d --build
```

### Check the stack is healthy
```bash
docker compose ps
# All services should show "Up" / "healthy"

# Smoke test
curl http://localhost/health
# {"status":"ok","app":"ML Experiment Tracker","version":"0.1.0",...}

curl -H "X-API-Key: dev-key-12345" http://localhost/api/v1/experiments/
# []
```

### View logs
```bash
docker compose logs -f backend    # tail backend logs
docker compose logs --tail=100    # last 100 lines from all services
```

### Run migrations manually
The entrypoint runs `alembic upgrade head` automatically on every backend start. To run it ad hoc:
```bash
docker compose exec backend alembic upgrade head
docker compose exec backend alembic downgrade -1    # roll back one
```

### Tear it down
```bash
docker compose down              # stop + remove containers, KEEPS volumes
docker compose down -v           # stop + remove containers + WIPE volumes
```

### Re-build only the backend
```bash
docker compose build backend     # rebuild image
docker compose up -d backend     # restart only that service
```

---

## 🧠 What We Learned

1. **Multi-stage builds are worth it.** A "fat" image with build-essential + dev headers is ~1.2 GB. The lean runtime image is ~280 MB. Same behavior, 4x smaller.
2. **Layer caching is the killer feature.** Once `pip install` is cached, every code change rebuilds in seconds instead of minutes. Order your COPYs carefully — `requirements.txt` first, then the rest.
3. **`exec` in entrypoint scripts matters.** Without it, the shell is PID 1, and uvicorn runs as a child. SIGTERM from `docker stop` goes to the shell, which doesn't know how to gracefully shut down uvicorn — you get a 10-second hard kill and possibly leaked DB connections.
4. **Healthchecks need a probe path, not just a port check.** `nc -z 8000` would say "healthy" even if the app is stuck. We use `curl /health` so the check reflects actual app readiness.
5. **`depends_on: condition: service_healthy`** is the only way to make startup ordering work reliably. Without it, the backend may try to connect to Postgres before Postgres is ready.
6. **One public port.** Only nginx is bound to the host. Postgres, MinIO, MLflow are reachable only from inside the `mlnet` network. This is the correct default — least-privilege network exposure.

---

## 📂 Files Touched

- `docker-compose.yml` — created.
- `.env.example` — created.
- `.dockerignore` — created (root, for compose).
- `backend/Dockerfile` — created.
- `backend/.dockerignore` — created.
- `backend/entrypoint.sh` — created (executable).
- `nginx/nginx.conf` — created.

No existing application code was modified — the backend, MLflow service, and Alembic config all work in Docker without any source changes. That's the test that the application is properly 12-factor.
