# 🚀 Build Runner

> Paste a GitHub URL → get a Docker image on `ghcr.io` and a running container on port 8080.
> A self-hosted, mini-CI that clones, builds, pushes, and deploys in one click.

![Build Runner Dashboard](docs/screenshot.png)
*(Replace `docs/screenshot.png` with a screenshot of the React UI at <http://localhost:5173>.)*

---

## Table of Contents
1. [What is this?](#what-is-this)
2. [Features](#features)
3. [Architecture](#architecture)
4. [Data Flow](#data-flow)
5. [Project Structure](#project-structure)
6. [Prerequisites](#prerequisites)
7. [Quick Start](#quick-start)
8. [Environment Variables](#environment-variables)
9. [API Reference](#api-reference)
10. [Frontend (React + Vite)](#frontend-react--vite)
11. [How a Build Works (Internals)](#how-a-build-works-internals)
12. [Repo Requirements for Builds](#repo-requirements-for-builds)
13. [Troubleshooting](#troubleshooting)
14. [Roadmap](#roadmap)

---

## What is this?

**Build Runner** is a lightweight, self-hosted Continuous Integration (CI) system.
It exposes a tiny REST + WebSocket API and a React dashboard. You give it a
GitHub repository URL, and a background worker:

1. **Clones** the repo (with your GitHub PAT embedded in the URL).
2. **Builds** a Docker image from the repo's `Dockerfile`.
3. **Pushes** the image to GitHub Container Registry (`ghcr.io`).
4. **Redeploys** the running container with the fresh image on port 8080.

You watch every step live in the browser via a WebSocket log stream.

It's small enough to read in one sitting (~600 lines of Python + 200 lines of
React) and powerful enough to demonstrate the full CI/CD pipeline locally
without GitHub Actions, Jenkins, or any cloud account.

---

## Features

- ✅ **REST API** for submitting builds and querying job history.
- ✅ **WebSocket log streaming** for real-time build output.
- ✅ **React + Vite dashboard** with live status, live logs, and clickable history.
- ✅ **Redis-backed job queue** — `LPUSH` / `BRPOP` for durable enqueue.
- ✅ **Docker-in-Docker** build isolation per job.
- ✅ **Auto-redeploy** — stops the old container, runs the new one, with `--restart always`.
- ✅ **Optional API key auth** (skipped in dev when `API_KEY` is empty).
- ✅ **GitHub webhook receiver** for `push` events on `main`/`master`.
- ✅ **Image auto-prune** after a TTL so disk doesn't fill up.

---

## Architecture

```
┌──────────────────────────────────────────────────────────────────────────┐
│                           USER'S BROWSER                                 │
│              React + Vite dashboard  (port 5173)                         │
│  ┌────────────┐  ┌────────────────┐  ┌───────────────────────────────┐   │
│  │ BuildForm  │  │  ActiveBuild   │  │  History (clickable list)    │   │
│  └─────┬──────┘  └────────┬───────┘  └──────────────┬────────────────┘   │
└────────┼──────────────────┼──────────────────────────┼──────────────────┘
         │ POST /build      │ WS /logs/{id}            │ GET /history
         ▼                  ▼                          ▼
┌──────────────────────────────────────────────────────────────────────────┐
│                  FastAPI  (uvicorn, port 8000)                           │
│  ┌────────────┐  ┌────────────┐  ┌────────────┐  ┌────────────────────┐  │
│  │ /build     │  │ /status    │  │ /history   │  │ /logs (WebSocket)  │  │
│  │ /webhook/* │  │ /requirem. │  │ / (static) │  │ /api/* (dev proxy) │  │
│  └─────┬──────┘  └─────┬──────┘  └─────┬──────┘  └─────┬──────────────┘  │
│        │               │               │                │                 │
│        └───────────────┴───────┬───────┴────────────────┘                 │
│                                │                                          │
│                      Redis (sync + async)                                │
│        ┌───────────────────────┴────────────────────────┐                 │
│        │  job:{uuid}    →  JSON {status, message, ...}  │                 │
│        │  logs:{uuid}   →  LIST of log lines  (capped)  │                 │
│        │  build_queue   →  LIST of pending jobs (FIFO)  │                 │
│        └───────────────────────┬────────────────────────┘                 │
└────────────────────────────────┼─────────────────────────────────────────┘
                                 │ BRPOP
                                 ▼
┌──────────────────────────────────────────────────────────────────────────┐
│                  WORKER  (worker.py, long-running)                       │
│                                                                          │
│   1. clone_repo  ──►  git clone (PAT injected)                           │
│   2. build_image ──►  docker build (docker_sdk)  ──► image:tag           │
│   3. push_image  ──►  docker push  ghcr.io/owner/repo:latest             │
│   4. redeploy    ──►  docker stop+rm+run  on :8080                       │
│                                                                          │
│   On every step:  update_status(job_id, status, message)                 │
│                   + _push_log(line)  →  Redis LPUSH logs:{uuid}          │
└──────────────────────────────────────────────────────────────────────────┘
                                 │
                                 ▼
┌──────────────────────────────────────────────────────────────────────────┐
│                       DOCKER DAEMON                                     │
│   • local image cache  (build-runner/{uuid}:latest)                      │
│   • remote registry    (ghcr.io/{owner}/{repo}:latest)                  │
│   • running container  (demo-app  →  host :8080)                        │
└──────────────────────────────────────────────────────────────────────────┘
```

### Components at a glance

| Component | Tech | Role |
|---|---|---|
| **Frontend** | React 18 + Vite | User-facing dashboard |
| **API server** | FastAPI + Uvicorn | HTTP + WebSocket endpoints |
| **Queue** | Redis 7 | Job state, log buffer, work queue |
| **Worker** | Python + `docker` SDK + `subprocess` | Build/push/deploy pipeline |
| **Build target** | Docker daemon | `docker build`, `docker push`, `docker run` |
| **External** | GitHub (`github.com`), GHCR (`ghcr.io`) | Source code + image registry |

---

## Data Flow

End-to-end path of a single build, from "User clicks Trigger" to "Container serves traffic":

```
[1] USER submits URL
        │
        │  POST /api/build?github_url=...
        │  Header: X-API-Key: <key>
        ▼
[2] FastAPI  start_build()
        │
        │  • validate URL
        │  • generate uuid4 → job_id
        │  • _enqueue(): SET job:{id} {status:queued} + LPUSH build_queue
        │  • return {"job_id": ..., "status": "queued"}
        ▼
[3] React  receives job_id
        │
        │  • setActiveJob({job_id, status:"queued", ...})
        │  • openLogSocket(job_id)  →  WS ws://.../api/logs/{id}
        ▼
[4] WORKER  BRPOP build_queue
        │
        │  • json.loads → (job_id, github_url)
        │  • update_status("running", "Job started")
        ▼
[5] WORKER  clone_repo()
        │
        │  • git clone https://x-access-token:<PAT>@github.com/owner/repo
        │  • strips token from stderr to avoid leak
        │  • update_status("cloning", "...")
        ▼
[6] WORKER  build_image()  (docker_builder.py)
        │
        │  • assert Dockerfile exists in repo root
        │  • client.images.build(path=clone_dir, tag=build-runner/{id}:latest)
        │  • each streamed chunk → _push_log()  →  LPUSH logs:{id}
        │  • update_status("building", ...)
        │  ◄── React WS tail sees each log line and appends to <pre>
        ▼
[7] WORKER  push_and_deploy()
        │
        │  • docker tag build-runner/{id}  ghcr.io/owner/repo:latest
        │  • docker push ghcr.io/owner/repo:latest
        │  • update_status("pushing", "...")
        │  • docker stop demo-app; docker rm -f demo-app
        │  • docker run -d --name demo-app -p 8080:8080 ghcr.io/owner/repo:latest
        │  • update_status("success", "Image: ...")
        ▼
[8] React  receives status:"success" over WS
        │
        │  • setActiveJob(...success...)
        │  • refreshHistory()  →  /api/history now shows this job
        │  • badge turns green, last log line is "Container started on :8080"
        ▼
[9] USER  opens http://localhost:8080
        │
        │  → fresh build serving traffic ✅
```

### Why Redis?

- **`job:{uuid}` (STRING / JSON)** — single source of truth for status, message,
  image tag. FastAPI and worker both read/write it; no locks needed because each
  status update is an atomic `SET`.
- **`logs:{uuid}` (LIST, capped at 5000)** — append-only log buffer. The
  WebSocket handler does `LRANGE` and ships the new tail to the client every
  500 ms. Older lines fall off automatically.
- **`build_queue` (LIST)** — classic producer/consumer. FastAPI `LPUSH`es a
  JSON payload, worker `BRPOP`s (blocking, atomic). Multiple workers can run
  in parallel safely.

### Why WebSocket?

`POST /build` returns in ~10 ms (just enqueue). The actual build takes 30-180 s.
We can't make HTTP wait that long (timeouts, no streaming). WebSocket solves
this with a long-lived duplex connection:

- Server pushes each status change (`{type:"status", ...}`) and each new log
  line (`{type:"log", line:"..."}`) as they happen.
- Client can disconnect at any time and reconnect by `job_id` (history cards
  re-subscribe to old jobs).

---

## Project Structure

```
build-runner-project/
├── main.py                  # FastAPI app (HTTP + WebSocket)
├── worker.py                # Background job processor
├── docker_builder.py        # `docker build` wrapper with live log streaming
├── redis_helper.py          # Redis client factory + key constants
├── notifier.py              # Optional post-build notifications
├── requirements.txt         # Python deps (fastapi, redis, docker, …)
├── Dockerfile               # Image that runs the worker + API in container
├── docker-compose.yml       # Local dev stack (Redis + app)
├── .env                     # Secrets: API_KEY, GITHUB_PAT, REDIS_*, …
│
├── frontend/                # React + Vite dashboard
│   ├── package.json
│   ├── vite.config.js       # /api → :8000 proxy (with ws:true)
│   ├── index.html
│   └── src/
│       ├── main.jsx         # React entry
│       ├── App.jsx          # Root component (state + WS)
│       ├── api.js           # fetch() wrapper + openLogSocket()
│       ├── styles.css       # Dark theme
│       └── components/
│           ├── BuildForm.jsx
│           ├── ActiveBuild.jsx
│           └── History.jsx
│
├── docs/
│   └── screenshot.png       # (add your own dashboard screenshot here)
│
├── BUILD_REQUIREMENTS.md    # What your repo must contain to build
├── test_websocket.py        # Manual WebSocket test client
└── README.md                # ← you are here
```

---

## Prerequisites

You need these installed on the host:

| Tool | Min version | Check | Install hint |
|---|---|---|---|
| **Python** | 3.11 | `python3 --version` | `apt install python3` or pyenv |
| **pip + venv** | bundled | `python3 -m venv --help` | `apt install python3-venv` |
| **Docker Engine** | 24.x | `docker --version` | <https://docs.docker.com/engine/install/> |
| **Redis** | 6.x | `redis-cli ping` | `apt install redis-server` *or* `docker run -d -p 6379:6379 redis:alpine` |
| **Node.js** | 18.x | `node --version` | <https://nodejs.org/> |
| **npm** | 9.x | `npm --version` | bundled with Node 18+ |
| **GitHub PAT** | classic, scopes: `repo`, `read:packages`, `write:packages` | — | <https://github.com/settings/tokens> |

> **Linux post-install:** your user must be in the `docker` group
> (`sudo usermod -aG docker $USER`) so `worker.py` can call `docker push` /
> `docker run` without `sudo`.

---

## Quick Start

### 1. Clone & enter

```bash
git clone https://github.com/poridhioss/minions-26.git
cd minions-26/build-runner-project
```

### 2. Create `.env`

```bash
cat > .env <<'EOF'
# Redis
REDIS_HOST=localhost
REDIS_PORT=6379

# API auth (leave empty to disable auth in dev)
API_KEY=devsecret123

# GitHub PAT (needs repo + write:packages)
GITHUB_TOKEN=ghp_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx

# Image that will be pushed to ghcr.io and run on :8080
GHCR_OWNER=your-gh-username
GHCR_REPO=demo-app
DEMO_IMAGE=ghcr.io/your-gh-username/demo-app:latest
DEMO_CONTAINER=demo-app
DEMO_PORT=8080

# Auto-redeploy on success? (true/false)
DEPLOY_ENABLED=true
EOF
```

### 3. Install Python deps

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 4. Start Redis (if not already running)

```bash
# Option A: native
redis-server --daemonize yes
redis-cli ping            # → PONG

# Option B: Docker
docker run -d -p 6379:6379 --name redis redis:alpine
```

### 5. Start the FastAPI server

```bash
uvicorn main:app --host 0.0.0.0 --port 8000
```

### 6. Start the worker (new terminal)

```bash
source venv/bin/activate
python -u worker.py
```

### 7. Start the React dashboard (new terminal)

```bash
cd frontend
cp ../.env .env                  # mirror API_KEY → VITE_API_KEY
# (or: grep API_KEY= ../.env | sed 's/^API_KEY=/VITE_API_KEY=/' > .env)
npm install
npm run dev                      # → http://localhost:5173
```

### 8. Open the dashboard

Visit **<http://localhost:5173>**, paste a GitHub URL that has a
`Dockerfile` at its root (try `https://github.com/iftakhar-323/demo-app`),
and click **⚡ Trigger Build**.

You should see:

1. The "Active Build" card appear with a yellow `running` badge.
2. Live log lines stream into the dark log box (each line color-coded).
3. The badge cycles: `queued → running → cloning → building → pushing → deploying → success` (green).
4. A new entry appears at the top of "Recent Builds" — click it to re-subscribe
   to its logs.

### 9. Hit the deployed app

```bash
curl http://localhost:8080/
# → Hello v1 from build runner!
```

---

## Environment Variables

All variables are loaded by `python-dotenv` at process start.

| Variable | Used by | Default | Purpose |
|---|---|---|---|
| `REDIS_HOST` | api, worker | `localhost` | Redis hostname |
| `REDIS_PORT` | api, worker | `6379` | Redis port |
| `API_KEY` | api | `""` | If non-empty, requires `X-API-Key` header on `POST /build` |
| `GITHUB_WEBHOOK_SECRET` | api | `""` | HMAC-SHA256 secret for `/webhook/github` |
| `GITHUB_TOKEN` / `GITHUB_PAT` | worker | `""` | PAT injected into `git clone` URL |
| `DEMO_IMAGE` | worker | `""` | `ghcr.io/owner/repo:latest` — tag used for push & run |
| `DEMO_CONTAINER` | worker | `demo-app` | Container name for `docker run --name` |
| `DEMO_PORT` | worker | `8080` | Host port mapped to container's `8080` |
| `DEPLOY_ENABLED` | worker | `true` | If `false`, worker stops after `docker push` |
| `JOB_TTL` | worker | `3600` | Seconds before a built image is pruned |
| `VITE_API_KEY` | frontend | `""` | Sent as `X-API-Key` from the React app |

---

## API Reference

Base URL (dev, through Vite proxy): **`http://localhost:5173/api`**
Base URL (prod, direct):           **`http://localhost:8000`**

### `GET /`

Health check. If the React `dist/` is mounted, serves the SPA. Otherwise returns
`{"message": "Build Runner System is alive!"}`.

### `POST /build`

Submit a new build job.

```http
POST /api/build?github_url=https://github.com/owner/repo
X-API-Key: devsecret123
```

**Response 200**
```json
{ "job_id": "bf55e0b4-...", "status": "queued" }
```

**Response 401** — missing or wrong `X-API-Key`
**Response 400** — `github_url` is not `http(s)://...`

### `GET /status/{job_id}`

Poll a single job (use this if you don't want WebSocket).

**Response 200**
```json
{
  "job_id": "bf55e0b4-...",
  "github_url": "https://github.com/iftakhar-323/demo-app",
  "status": "success",
  "message": "Image: ghcr.io/iftakhar-323/demo-app:latest"
}
```

`status` is one of: `queued`, `running`, `cloning`, `building`, `pushing`,
`deploying`, `success`, `failed`.

### `GET /history`

List the last 50 jobs (newest first).

**Response 200**
```json
{
  "jobs": [
    { "job_id": "...", "github_url": "...", "status": "success", "message": "..." },
    ...
  ]
}
```

### `WS /logs/{job_id}`

Stream live status updates and log lines for a job.

**Server → Client messages**

```json
{ "type": "status", "job_id": "...", "status": "building", "message": "..." }
{ "type": "log",    "line": "Step 1/3 : FROM python:3.12-slim" }
{ "type": "error",  "message": "job not found" }
```

The socket closes automatically when the job reaches `success` or `failed`.

### `POST /webhook/github`

Receive GitHub `push` events and auto-queue a build for the default branch.

Headers:
- `X-GitHub-Event: push`
- `X-Hub-Signature-256: sha256=<hmac>`

Body: the standard GitHub webhook JSON payload.

### `GET /requirements`

Returns the contents of [`BUILD_REQUIREMENTS.md`](./BUILD_REQUIREMENTS.md) as
`text/markdown`. Linked from the React BuildForm hint.

---

## Frontend (React + Vite)

### Dev mode

```bash
cd frontend
npm install
npm run dev    # → http://localhost:5173
```

Vite proxies everything under `/api/*` to `http://localhost:8000/*`
(including WebSocket) — see `frontend/vite.config.js`. This way the React app
can use relative URLs like `fetch('/api/build')` and never sees CORS errors.

### Production build

```bash
cd frontend
npm run build      # → frontend/dist/
```

In `main.py` the static mount can be flipped to serve `frontend/dist/` instead
of the empty `static/` directory, so the entire app (API + UI) lives on
**port 8000** in production.

### Component tree

```
App.jsx                       (state: activeJob, logs, history)
├── BuildForm.jsx             (URL input → onSubmit)
├── ActiveBuild.jsx           (status badge + auto-scrolling <pre>)
│   └── logs.map(line => ...)  (color-coded by classify())
└── History.jsx               (clickable past jobs)
```

State is intentionally flat — no Redux, no React Query. A 5-second
`setInterval` polls `/api/history` so the list updates even for jobs you
didn't trigger in this tab.

---

## How a Build Works (Internals)

The worker is a single Python process running an infinite `BRPOP` loop:

```python
while True:
    _, raw = r.brpop("build_queue", timeout=5)
    if not raw:
        continue
    payload = json.loads(raw)
    process_job(payload["job_id"], payload["github_url"])
```

`process_job()` runs four sequential steps, each updating Redis on success
or failure so the API/WebSocket layer can stream the state.

### Step 1: `clone_repo(job_id, github_url)`

- Uses `GIT_TERMINAL_PROMPT=0` + `GIT_ASKPASS=/bin/echo` so git never blocks
  on a password prompt.
- Embeds the PAT in the URL: `https://x-access-token:<PAT>@github.com/...`
- Scrubs the token out of stderr before logging (security).
- Updates status: `running` → `cloning` (or `failed` on error/timeout).

### Step 2: `build_image(job_id, clone_dir, redis_client)`

- Asserts `Dockerfile` exists at repo root (else `failed: "Dockerfile not found in repo"`).
- Uses the official `docker` Python SDK: `client.images.build(path=..., tag=..., rm=True)`.
- Iterates the streaming build-log generator and pushes each chunk to
  `logs:{job_id}` via `LPUSH` + `LTRIM` (capped at 5000 lines).
- Returns `(True, image_tag)` on success or `(False, error_message)`.

### Step 3: `push_and_deploy(job_id, built_image)`

This is one Python function with four sub-steps:

```
1. docker login ghcr.io -u <user> -p <PAT>      (skipped if creds already cached)
2. docker tag  <built_image>  <DEMO_IMAGE>
3. docker push <DEMO_IMAGE>
4. if DEPLOY_ENABLED:
     docker stop  <DEMO_CONTAINER>
     docker rm -f <DEMO_CONTAINER>
     docker run -d --name <DEMO_CONTAINER> --restart always
                -p <DEMO_PORT>:8080 <DEMO_IMAGE>
```

Each sub-step has its own `try/except` and `update_status("failed", ...)` so
partial progress is observable.

### Step 4: `cleanup_clone(clone_dir)`

Removes the local checkout (`/tmp/build-{job_id}`) to keep disk usage flat.

A `threading.Timer` schedules `prune_image(image_tag)` after `JOB_TTL` seconds
(default 1 hour) so old local images don't accumulate.

---

## Repo Requirements for Builds

See **[`BUILD_REQUIREMENTS.md`](./BUILD_REQUIREMENTS.md)** for the full guide.
TL;DR:

| Must have | Consequence if missing |
|---|---|
| `Dockerfile` at **repo root** | `Build failed: Dockerfile not found in repo` |
| App listens on **port 8080** | Build/deploy succeed but `:8080` returns nothing |
| Repo is public, or PAT has access | `git clone error: Authentication failed` |

Working example: **<https://github.com/iftakhar-323/demo-app>**

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `PONG` missing on `redis-cli ping` | Redis not running | `redis-server --daemonize yes` *or* `docker run -d -p 6379:6379 redis:alpine` |
| `401 Unauthorized` from React | `VITE_API_KEY` not set | `cp .env frontend/.env` and restart Vite |
| `Build failed: Dockerfile not found in repo` | Repo has no root `Dockerfile` | Add one, commit, re-trigger |
| `git clone error: Authentication failed` | PAT missing/invalid | Regenerate PAT with `repo` + `write:packages` scopes |
| `denied: permission to X/Y.git` on push | PAT lacks `write:packages` for the target org | Use a PAT scoped to your own user/org |
| Vite shows `Network: http://10.x.x.x:5173` but you can't reach it | Host firewall | Use `http://localhost:5173` from the same machine |
| Worker dies silently | Check `/tmp` for old `worker.log` *or* run `python -u worker.py` in foreground | — |
| `docker: permission denied` from worker | User not in `docker` group | `sudo usermod -aG docker $USER` then re-login |
| Build succeeds but `curl :8080` hangs | App binds `127.0.0.1` not `0.0.0.0` | Change `CMD` to listen on `0.0.0.0:8080` |

---

## Roadmap

- [ ] Build cache across jobs (currently each build starts from `docker build` cold)
- [ ] Per-job CPU/memory limits in `docker build`
- [ ] Subfolder `Dockerfile` support (`-f` flag)
- [ ] Build cancellation endpoint (`DELETE /build/{id}`)
- [ ] Persistent log storage (move from Redis LIST to disk or S3)
- [ ] Multi-tenant API key (per-user, not single shared key)
- [ ] React: cancel button, log filtering (grep), build re-trigger from history
- [ ] Production static serve: mount `frontend/dist/` from FastAPI on `/`

---

## License

MIT — do whatever you want, no warranty. See repo for details.
