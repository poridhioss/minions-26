# Job Orchestrator

A self-hosted, container-isolated job runner. Submit a Docker image + shell
command through the web UI or REST API; a worker pulls the image, runs the
command inside a hardened container, streams the output back live, and persists
the full log to disk for later retrieval.

Built as an internship project (Puku / Poridhi). Two services, one queue:

- **API + UI** — Express 5 + ws, serves the React frontend and the REST/WS API.
- **Worker** — BullMQ consumer, talks to the Docker daemon via `/var/run/docker.sock`.
- **Redis** — BullMQ queue, pub/sub log channel, cancel/delete intent keys.

![alt text](<images/Untitled Diagram.drawio (1).png>)

---

## Table of contents

1. [Features](#features)
2. [Tech stack](#tech-stack)
3. [Project structure](#project-structure)
4. [Architecture](#architecture)
5. [Quick start (Docker, recommended)](#quick-start-docker-recommended)
6. [Local development (no Docker)](#local-development-no-docker)
7. [Configuration](#configuration)
8. [REST API](#rest-api)
9. [WebSocket log stream](#websocket-log-stream)
10. [Security model](#security-model)
11. [Testing](#testing)
12. [Troubleshooting](#troubleshooting)
13. [License](#license)

---

## Features

- **One-shot container jobs.** Submit `{ image, command }` → the worker pulls
  the image, runs `sh -c <command>`, captures stdout/stderr, and reports the
  exit code.
- **Live log streaming.** WebSocket per-job channel replays persisted log
  history first, then forwards new events as they happen.
- **Cancel / delete.** Cancel stops a running container; delete tears the
  container down + removes the queue entry + deletes the log file. Both
  are idempotent and survive a stuck worker (the API talks to Docker
  directly, not just to the worker).
- **Bulk delete.** `POST /jobs/delete` with `{ "ids": [...] }`.
- **Hardened container defaults.** Read-only rootfs, all-caps dropped,
  `no-new-privileges`, 256 MB memory cap, 0.5 CPU, 64 PIDs, `network=none`.
- **API key auth.** `x-api-key` header for every `/jobs/*` route; the
  `/healthz` endpoint is open.
- **Per-write rate limits.** 30 writes/min, 60 deletes/min per API key.
- **Path-traversal hardened.** Every `:id` is regex-validated *and* the raw
  URL is decoded before being checked, so `%2F..%2Fetc%2Fpasswd`-style
  attacks can't sneak past Express's path normalization.
- **Structured JSON logs** on stdout (request id, duration, status, jobId).
- **Retry with exponential backoff** (BullMQ, 3 attempts).
- **Job timeout** (default 5 min) — kills the container and forces a retry.

## Tech stack

| Layer        | Choice                                          |
|--------------|-------------------------------------------------|
| API          | Node 20, Express 5, ws                          |
| Queue        | BullMQ on Redis 7                               |
| Worker       | Node 20, dockerode                              |
| Container    | Docker (mounted `/var/run/docker.sock`)         |
| Frontend     | React 19, Vite 8, Tailwind 4                    |
| Tests        | `node:test` (built-in, no Jest/Mocha)            |

## Project structure

```
.
├── backend/                  # Node API + worker
│   ├── Dockerfile            # multi-stage: builds frontend then Node image
│   ├── package.json
│   ├── src/
│   │   ├── server.js         # http + ws bootstrap, signal handling
│   │   ├── app.js            # Express routes, validation, rate limits
│   │   ├── queue/jobQueue.js # BullMQ Queue (shared connection settings)
│   │   ├── services/
│   │   │   ├── jobStore.js   # status / cancel / delete / list (talks to BullMQ + Docker + Redis)
│   │   │   └── logStore.js   # NDJSON-on-disk, SAFE_ID path-traversal guard
│   │   ├── worker/jobWorker.js   # BullMQ consumer: pull image, run container, stream logs
│   │   ├── middleware/
│   │   │   ├── auth.js       # x-api-key check
│   │   │   └── csp.js        # CSP header (dev-friendly)
│   │   └── lib/
│   │       ├── logger.js     # JSON-on-stdout + request-id middleware
│   │       ├── rateLimit.js  # in-memory fixed-window limiter
│   │       └── safeEqual.js  # constant-time string compare
│   └── test/
│       ├── api.test.js       # e2e (requires running worker)
│       ├── jobStore.test.js  # unit (BullMQ/Redis stubs)
│       ├── logStore.test.js  # unit (tmp dir)
│       ├── parseNdjson.test.js
│       ├── __bullmq_stub.js  # generated at test time
│       ├── __ioredis_stub.js # generated at test time
│       └── runE2E.js         # spawns the docker compose test-runner
├── frontend/                 # React UI (Vite)
│   ├── src/
│   │   ├── App.jsx           # layout, hydration, polling, banners
│   │   ├── api.js            # fetch helpers + WebSocket log streamer
│   │   ├── components/       # Header, JobList, JobDetail, JobForm, LogView, StatusPill, ConfirmModal
│   │   └── hooks/useJobStream.js
│   ├── public/               # static assets (favicon, hero image)
│   ├── index.html
│   ├── vite.config.js
│   └── package.json
├── docker-compose.yml        # redis + server + worker + test-runner
├── .env.example              # template for root .env
└── README.md                 # this file
```

## Architecture

### Request lifecycle (submit → run → finish)

1. Browser POSTs `/jobs` with `{ image, command }`. The server validates
   both (length caps + a regex on `image` that rejects shell metacharacters
   and path traversal) and enqueues a BullMQ job on the `container-jobs`
   queue.
2. The worker picks the job up, checks `job-cancel:<id>` and
   `job-delete:<id>` Redis keys (early-exit if set), then publishes a
   `start` event on `bull:container-jobs:<jobId>` and appends it to
   `logs/<jobId>.log`.
3. The worker pulls the image (idempotent — `docker.pull` is a no-op when
   the image is local) and creates a container with the hardened
   `HostConfig` (read-only rootfs, no caps, no network, no new
   privileges, ulimits, etc.).
4. `container.logs({ follow: true, stdout, stderr })` is demuxed through
   a line-buffered writer so a chunk split mid-line still produces whole
   lines. Each line is published on the pub/sub channel *and* appended to
   the on-disk NDJSON log.
5. The worker `await`s `container.wait()`, racing a 500 ms poll that
   checks the cancel/delete keys (and a hard `JOB_TIMEOUT_MS` timer that
   force-kills the container if it overruns).
6. On exit the worker publishes `exit` with `{ statusCode, timedOut }` and
   returns the status code to BullMQ. BullMQ's `removeOnComplete` /
   `removeOnFail` policies garbage-collect the queue entry; the on-disk
   log stays until explicitly deleted via the API.

### Cancel vs delete

| Intent  | What it does                                                                                    |
|---------|-------------------------------------------------------------------------------------------------|
| Cancel  | Force-kills the container (via Docker, not the worker), `moveToFailed`'s the BullMQ job, surfaces as `state: "cancelled"`. Log file is preserved. |
| Delete  | Same container kill + `queue.remove` + unlink `logs/<id>.log`. Idempotent — returns `ok: true` even when the job has already been TTL'd. |

Both flows go through `forceStopContainer`, which reads the container id
out of Redis (`job-container:<id>`, written by the worker when it creates
the container) and talks straight to Docker. That means a stuck worker
can't keep a job alive after the user cancels it.

### Log persistence

Every event is a single JSON object on its own line in `logs/<jobId>.log`.
Corrupted lines are silently skipped on read (`parseNdjson`), so a partial
write never breaks `GET /jobs/:id/logs`.

---

## Quick start (Docker, recommended)

### 1. Clone with sparse-checkout

This repo is large and most of it isn't the project itself — use sparse
checkout to pull only the directories you need:

```bash
git clone --filter=blob:none --sparse https://github.com/poridhioss/minions-26

# Enable sparse checkout
git sparse-checkout set Fawaj_Suraim/puku-editor-interns-Fawaj_Suraim-4

# Fetch the contents
git pull origin main
```

After this you'll have `backend/`, `frontend/`, `docker-compose.yml`, and etc.

### 2. Prerequisites

- **Docker Engine 24+** with the Compose v2 plugin (`docker compose`).
- **Docker daemon reachable from the worker container** — the `worker`
  service mounts `/var/run/docker.sock`. The host's `docker` group GID
  must match `1002` (the GID used by `docker-compose.yml`); if it
  doesn't, edit the `user: "1000:1002"` line under `worker:` and run
  `getent group docker` to find your host's GID.
- **~1 GB free RAM** for a cold pull of `alpine` plus the Node images.
- Ports `3000` (server) reachable from your browser.

### 3. Configure environment

```bash
cd Fawaj_Suraim/puku-editor-interns-Fawaj_Suraim-4
cp .env.example .env
# Edit .env and set API_KEY to something long & random:
#   API_KEY=$(openssl rand -hex 32)
```

`docker compose` auto-loads `.env` from the project root and forwards it
to every service. The same key is also baked into the frontend bundle at
build time (via `VITE_API_KEY`) so the UI works on first load without
the user pasting the key into the header.

### 4. Bring up the stack

```bash
docker compose up --build -d
```

That gives you:

| Service       | Port (host) | Purpose                                  |
|---------------|-------------|------------------------------------------|
| `redis`       | (internal)  | Queue + pub/sub + cancel/delete keys     |
| `server`      | `3000`      | Express API + static frontend + WS       |
| `worker`      | —           | BullMQ consumer, runs containers         |

Watch the worker come up:

```bash
docker compose logs -f worker
```

Then open **http://localhost:3000**.

### 5. Submit your first job

From the UI: keep the `alpine` preset and click **Run Job**.

From the CLI:

```bash
curl -X POST http://localhost:3000/jobs \
  -H "Content-Type: application/json" \
  -H "x-api-key: $API_KEY" \
  -d '{"image":"alpine","command":"echo hi && sleep 1 && echo bye"}'
# → {"jobId":"<uuid>"}
```

Then poll:

```bash
curl -s http://localhost:3000/jobs/<jobId> -H "x-api-key: $API_KEY" | jq .
```

### 6. Tear down

```bash
docker compose down            # keep volumes
docker compose down -v         # also wipe Redis data
```

### 7. Scale workers

```bash
docker compose up -d --scale worker=4
```

Each replica competes for BullMQ jobs. The API is stateless and can be
scaled the same way (`docker compose up -d --scale server=3`).

---

## Local development (no Docker)

Useful for iterating on the backend without a container build loop. You
still need Redis and the Docker daemon on the host.

### 1. Same clone as above (sparse checkout works for dev too).

### 2. Install deps

```bash
cd backend && npm install
cd ../frontend && npm install
```

### 3. Start Redis

```bash
docker run -d --rm -p 6379:6379 --name jo-redis redis:7-alpine
# or, if you already have redis-server installed:
redis-server --daemonize yes
```

### 4. Configure `backend/.env`

```bash
cd backend
cp .env.example .env
# Edit .env:
#   API_KEY=<something>
#   REDIS_URL=redis://127.0.0.1:6379
#   PORT=3000
```

### 5. Run the API and the worker in two terminals

```bash
# Terminal 1 — API server (nodemon auto-reloads on save)
cd backend && npm run dev:server

# Terminal 2 — Worker (also nodemon)
cd backend && npm run dev:worker
```

### 6. Run the frontend dev server

```bash
cd frontend
# Vite reads VITE_API_KEY from .env / .env.production / .env.local
# (or shell env at start time). For local dev, create a .env.local:
echo "VITE_API_KEY=<your-api-key>" > .env.local
npm run dev
```

Open **http://localhost:5173**. The Vite dev server proxies nothing — the
frontend calls the API directly at `http://localhost:3000` via
`location.host`-relative URLs, so when you open the UI from Vite the
requests go to port 5173 instead. Set `VITE_API_KEY` so the bundle ships
with your key, or paste it into the header input on first load.

### 7. Production-style frontend build

```bash
cd frontend && npm run build
# Outputs to frontend/dist, which backend/src/app.js will auto-serve
# if it finds a frontend/index.html relative to the repo root.
```

Then restart the API (`npm run dev:server` or `npm run start:server`) and
hit `http://localhost:3000` to use the production-style bundle.

---

## Configuration

All knobs live in environment variables. The defaults are sensible for a
single-host dev box.

| Variable                      | Default                | Where it's read     | Notes                                                                                       |
|-------------------------------|------------------------|---------------------|---------------------------------------------------------------------------------------------|
| `API_KEY`                     | *(unset = auth off)*   | server, worker      | Sent as `x-api-key` on every `/jobs/*` request; required for `wss` upgrade (`?token=...`). |
| `VITE_API_KEY`                | *(unset)*              | frontend build      | Baked into the JS bundle at build time so the UI works on first load.                       |
| `PORT`                        | `3000`                 | server              |                                                                                             |
| `REDIS_URL`                   | *(required)*           | server + worker     | e.g. `redis://127.0.0.1:6379`. The compose file sets `redis://redis:6379`.                   |
| `LOG_LEVEL`                   | `info`                 | server + worker     | `debug` enables per-request logs and worker event-level logs.                               |
| `WORKER_CONCURRENCY`          | `2`                    | worker              | BullMQ `concurrency` — number of jobs a worker processes in parallel.                       |
| `JOB_TIMEOUT_MS`              | `300000` (5 min)       | worker              | Hard kill + retry trigger.                                                                  |
| `WRITE_RATE_LIMIT_PER_MIN`    | `30`                   | server              | Per-key cap on `POST /jobs`.                                                                |
| `DELETE_RATE_LIMIT_PER_MIN`   | `60`                   | server              | Per-key cap on `DELETE /jobs/:id` and `POST /jobs/delete`.                                  |
| `ALLOWED_WS_ORIGINS`          | *(allow all)*          | server              | Comma-separated origin allowlist for WebSocket upgrades. Empty = allow any origin (dev).    |
| `STATIC_DIR`                  | *(auto-detect)*        | server              | Override the static-file root. By default the server picks the first existing `frontend/`, `public/`, or `../public/` containing an `index.html`. |
| `JOB_USER`                    | *(unset)*              | worker              | Set to a UID:GID string to run the command as that user. Skip for minimal images (no UID 1000 user). |
| `WORKER_RUNNING`              | *(unset)*              | tests               | Set to `1` to enable the e2e test suite. See [Testing](#testing).                          |

---

## REST API

All `/jobs/*` routes require the `x-api-key` header. `/healthz` does not.
Every response is JSON unless noted.

| Method | Path                  | Body                              | Response                                                              |
|--------|-----------------------|-----------------------------------|-----------------------------------------------------------------------|
| `GET`  | `/healthz`            | —                                 | `{ "status": "ok" }`                                                  |
| `GET`  | `/jobs`               | —                                 | `{ "jobs": [ { jobId, image, command, state, ... }, ... ] }`         |
| `POST` | `/jobs`               | `{ "image": "...", "command": "..." }` | `202 { "jobId": "<uuid>" }`                                     |
| `GET`  | `/jobs/:id`           | —                                 | `{ jobId, state, image, command, exitCode, queuedAt, startedAt, finishedAt, durationMs, attemptsMade, failedReason }` |
| `DELETE` | `/jobs/:id`         | —                                 | `{ ok: true, reason?: "..." }`                                        |
| `POST` | `/jobs/delete`        | `{ "ids": ["...", "..."] }`       | `{ deleted: <n>, results: [...] }`                                    |
| `POST` | `/jobs/:id/cancel`    | —                                 | `{ ok: true, reason?: "..." }` (409 on hard failure)                  |
| `GET`  | `/jobs/:id/logs`      | —                                 | `{ jobId, lines: [ { type, ... }, ... ] }` (NDJSON, newest-last)     |

### Validation

`POST /jobs` rejects:

- Missing `image` or `command` (`400 image and command are required`).
- Non-string `image` or `command` (`400 ... must be strings`).
- `image` longer than 256 chars or `command` longer than 64 KB
  (`400 ... exceeds max length`).
- `image` not matching `^[a-z0-9][a-z0-9._/-]*(:[a-z0-9._-]{1,128})?(@sha256:[a-f0-9]{64})?$`
  (`400 image must match [registry/]name[:tag][@sha256:...]`). This blocks
  shell-metacharacter payloads like `alpine; rm -rf /` and path traversal
  like `../etc/passwd`.

`GET/DELETE /jobs/:id` (and any other `:id`-bearing route) reject any id
that doesn't match `^[A-Za-z0-9_-]+$` — the raw URL is decoded before
checking, so URL-encoded `%2F`/`%2E` are still caught.

### Error shape

```json
{ "error": "<machine-readable-code>", "reason"?: "..." }
```

Common codes: `unauthorized`, `rate_limited`, `invalid_id`, `not_found`,
`no_logs`, `cancel_failed`, `delete_failed`, `list_failed`.

### Example: full lifecycle

```bash
export API_KEY=changeme
export BASE=http://localhost:3000

# 1) Submit
JOB=$(curl -s -X POST $BASE/jobs \
  -H "Content-Type: application/json" \
  -H "x-api-key: $API_KEY" \
  -d '{"image":"alpine","command":"echo hi && sleep 2 && echo bye"}' \
  | jq -r .jobId)
echo "submitted $JOB"

# 2) Poll status until terminal
until curl -s $BASE/jobs/$JOB -H "x-api-key: $API_KEY" \
        | jq -e '.state | IN("completed","failed","cancelled","deleted")' >/dev/null; do
  sleep 1
done

# 3) Read full log
curl -s $BASE/jobs/$JOB/logs -H "x-api-key: $API_KEY" | jq .

# 4) Cancel a long-running job
curl -s -X POST $BASE/jobs/$JOB/cancel -H "x-api-key: $API_KEY"

# 5) Delete it (kills container, removes queue entry, deletes log)
curl -s -X DELETE $BASE/jobs/$JOB -H "x-api-key: $API_KEY"
```

---

## WebSocket log stream

```
ws://<host>/?jobId=<id>&token=<API_KEY>
```

The server replays the full persisted log first (so a client that
connects after the job already produced output still catches up), then
forwards every new event published on `bull:container-jobs:<jobId>`.

Each frame is a single JSON event. Common shapes:

```jsonc
{ "type": "start",   "jobId": "...", "image": "...", "command": "..." }
{ "type": "log",     "stream": "stdout" | "stderr" | "system", "data": "line\n" }
{ "type": "exit",    "jobId": "...", "statusCode": 0, "timedOut": false }
{ "type": "error",   "data": "<message>" }
{ "type": "connected", "jobId": "..." }
```

Auth checks:

- `token` query param must match `API_KEY` (if `API_KEY` is set).
- The `Origin` header is checked against `ALLOWED_WS_ORIGINS` when that
  env var is set; empty = allow any origin (dev).

The frontend's `streamLogs(id, onEvent)` helper in `frontend/src/api.js`
opens this socket and parses frames into the same shape the
`useJobStream` hook consumes.

---

## Security model

### What the worker isolates

Every job runs inside a Docker container with:

- `NetworkMode: 'none'` — no network access at all. Flip to `bridge` in
  `backend/src/worker/jobWorker.js` if you need egress.
- `ReadonlyRootfs: true` + two `tmpfs` mounts (`/tmp` 64 MB, `/run` 16 MB).
- `CapDrop: ['ALL']`, `SecurityOpt: ['no-new-privileges:true']`.
- Hard ulimits: `nofile=1024`, `nproc=64`.
- Resource caps: 256 MB memory, 0.5 CPU, 64 PIDs.
- `AutoRemove: true` — container is reaped on exit so a runaway job
  can't leave a zombie.

### What the API isolates

- API-key auth on `/jobs/*` (constant-time compare, no auth on
  `/healthz`).
- Per-key rate limits on write/delete.
- Strict regex on `image` (no whitespace, no shell metas).
- 64 KB cap on `command`.
- 128 KB JSON body cap (`express.json({ limit: '128kb' })`).
- Raw-URL traversal check before route handlers run (defense in depth on
  top of Express's path normalization).
- CSP header on every response (`default-src 'self'`, `ws:` allowed for
  log streaming).

### What's still your problem

- This project is not multi-tenant. A leaked `API_KEY` lets the holder
  submit jobs, cancel jobs, delete logs, and (via the worker) spawn
  containers with network access if you've flipped `NetworkMode`.
- The `worker` service mounts `/var/run/docker.sock`. A container escape
  would compromise the host. For real production, replace this with
  [tecnativa/docker-socket-proxy](https://github.com/Tecnativa/docker-socket-proxy)
  and put the proxy behind the same network policy as the worker.
- Log files are written to the worker container's filesystem. If you
  need log retention, mount a host volume (compose already does this via
  `./backend/logs:/app/logs`) and ship them off-host.

---

## Testing

The test suite uses Node's built-in `node:test` runner — no Jest, no
Mocha. There are three layers.

### Layer 1 — Pure unit tests (no Redis, no Docker)

```bash
cd backend
npm run test:unit
```

Runs `jobStore.test.js`, `logStore.test.js`, `parseNdjson.test.js`.
`jobStore.test.js` stubs out BullMQ and ioredis in-memory; `logStore`
runs against a fresh tmp directory. Safe to run anywhere, anytime.

Covers:
- `parseNdjson`: empty input, blank lines, corrupted lines.
- `logStore`: round-trip, `read` returns `null` on missing, `pathFor`
  rejects path-traversal ids, `remove` is idempotent.
- `jobStore`: status shape (exitCode / timestamps / duration), unknown
  ids, cancelled-by-user mapping for both worker versions, deleted
  state via the delete key, idempotent cancel/delete, BullMQ-lock-race
  fall-through for delete.

### Layer 2 — End-to-end API tests

These spin up the Express app on a real HTTP server (no listen), submit
a job, poll until completion, and assert the response shape and
persisted logs. **Requires a running Redis and a running worker.**

```bash
# Option A: run the whole stack and the test-runner via Docker
docker compose up -d        # bring up redis + server + worker
npm run test:e2e            # spawns the ephemeral test-runner container

# Option B: run the tests directly (no Docker), if Redis + a worker
# are already running on the host
cd backend
WORKER_RUNNING=1 npm test
```

`runE2E.js` (`npm run test:e2e`) shells out to `docker compose run
--rm --no-deps test-runner`, which runs `node --test
test/api.test.js` inside an ephemeral container with `WORKER_RUNNING=1`
and `API_KEY=test-key`. The test container shares `backend/logs` with
the worker so it can read the worker's on-disk log files.

The suite auto-skips itself if `WORKER_RUNNING` isn't set, so plain
`npm test` stays green in CI without Docker.

Covers (against a real worker pulling `alpine`):
- `/healthz` returns ok.
- `POST /jobs` validation (missing fields, non-strings, oversized
  command, shell metas / path traversal in `image`, accepted image
  refs).
- `POST /jobs` returns `202 + jobId` on valid input.
- `POST /jobs` returns `401` without `x-api-key`.
- `GET /jobs/:id` returns shaped result with `exitCode`,
  `startedAt`/`finishedAt`, `durationMs`, `attemptsMade`.
- `GET /jobs/:id/logs` returns persisted NDJSON lines.
- `GET /jobs/:id/logs` tolerates corrupted lines.
- `GET /jobs/:id` returns `404` for unknown id.
- `GET /jobs/:id/logs` and `DELETE /jobs/:id` reject path-traversal ids
  with `400 invalid_id`.
- `GET /jobs` returns the submitted job in its list.

### Layer 3 — Linting the frontend

```bash
cd frontend
npm run lint
```

### Running *everything*

```bash
# Backend unit
cd backend && npm run test:unit

# End-to-end (requires the Docker stack)
docker compose up -d
cd backend && npm run test:e2e

# Frontend
cd ../frontend && npm run lint
```

---

## Troubleshooting

### The sidebar shows "API key rejected"

Either `API_KEY` isn't set in `.env`, or the frontend isn't sending it.
The frontend reads the key in this order:

1. `localStorage.getItem('apiKey')` (set via the header input).
2. `import.meta.env.VITE_API_KEY` (baked in at build time).
3. Empty → every request 401s.

Fix: paste the correct `API_KEY` into the header input and press Save.
For a permanent fix, set `VITE_API_KEY` and rebuild the frontend
(`docker compose build server` will rebuild and rebake).

### The sidebar shows "Server is down"

The backend isn't reachable. Check:

```bash
docker compose ps
docker compose logs server
curl -s http://localhost:3000/healthz
```

### `docker compose up` fails with "API_KEY must be set"

`docker-compose.yml` has `${API_KEY:?...}` for both `server` and
`worker`. You need a `.env` at the repo root with `API_KEY=...` — see
[Step 3](#3-configure-environment).

### Worker says `EACCES` on `/var/run/docker.sock`

Your host's `docker` group GID isn't `1002`. Find it:

```bash
getent group docker
# → docker:x:998:fawaj_suraim
```

Then edit `docker-compose.yml`, change the worker `user:` line from
`"1000:1002"` to `"1000:<your-docker-gid>"`, and `docker compose up
--build -d`.

### Worker says `permission denied` writing log files

The server runs as `1000:1000` and the worker as `1000:1002` by
default. Both should be able to read/write `backend/logs/` on the host
as long as your local UID is 1000. If it's not, override the
`user:` lines in `docker-compose.yml`.

### A job stays `active` forever

Either the worker crashed mid-job, or the container is hanging past
`JOB_TIMEOUT_MS`. The timeout force-kills the container; if the worker
itself is wedged, hit `DELETE /jobs/:id` — the API talks to Docker
directly so it can clean up even when the worker isn't responding.

### Logs endpoint returns `no_logs`

The log file is written to the worker's filesystem. In Docker, the
worker mounts `./backend/logs:/app/logs`, so `GET /jobs/:id/logs`
should find it as long as the API is also using the same compose
stack. If you've split the stack across hosts, mount the log directory
on both.

### Frontend build doesn't pick up the API key

`VITE_API_KEY` is read from `.env.production` *in the frontend root at
build time*. The multi-stage `backend/Dockerfile` writes that file
from the `VITE_API_KEY` build arg, which `docker-compose.yml` forwards
from the root `.env`. If you've overridden `STATIC_DIR` to serve a
pre-built `frontend/dist` from somewhere else, make sure that build was
done with `VITE_API_KEY` set.

---

## License

ISC (matches `backend/package.json`). See `LICENSE` if present.