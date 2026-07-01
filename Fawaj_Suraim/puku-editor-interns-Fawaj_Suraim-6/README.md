# Replit — Browser-Based IDE Stack

A small, self-hosted "Replit-style" IDE: a React + Vite editor in the browser
talks over Socket.IO to a Node orchestration server, which spawns and manages
ephemeral Docker sandbox containers where the user's code actually runs.

```
+-----------------------------+       +-----------------------------+
|  Browser (React + Vite)     |       |  Host Docker engine         |
|                             |       |                             |
|  - Monaco editor            |  HTTP |  replit-backend             |
|  - xterm.js terminals       +------>+    - dockerode              |
|  - Socket.IO client         |  WSS  |    - spawns sandboxes       |
+-----------------------------+       |    - exec into PTYs         |
                                      |    - file read/write        |
                                      +-------------+---------------+
                                                    | dockerode
                                                    v
                                      +-----------------------------+
                                      |  replit-sandbox (per user)  |
                                      |    - non-root `developer`   |
                                      |    - bash + node + python    |
                                      |    - /workspace as cwd      |
                                      +-----------------------------+
```

## Repository layout

| Path | What it is |
|---|---|
| `backend/` | Node + Express + Socket.IO orchestration server |
| `backend/Dockerfile` | Image for the orchestrator (runs as `node` user) |
| `backend/Dockerfile.sandbox` | Image for the per-user workspace container |
| `frontend/` | React + Vite SPA (Monaco editor, xterm.js, Socket.IO client) |
| `frontend/Dockerfile` | Multi-stage Vite build served by Nginx |
| `frontend/nginx.conf` | Nginx config: serves the SPA and reverse-proxies `/api` + `/socket.io` |
| `docker-compose.yml` | Production stack: `replit-backend` + `replit-frontend` on `replit-net` |
| `Makefile` | Convenience targets (`up`, `down`, `sandbox`, `dev`, ...) |
| `.dockerignore` | Excludes `.replit*` host state from the build context |

## Prerequisites

- Docker Engine 24+ with the Compose plugin
- Node.js 20+ and npm (only required for the native `make dev` workflow)
- Linux host user must be in the `docker` group, or you'll need root to talk
  to `/var/run/docker.sock`

Verify with:

```bash
docker --version
docker compose version
docker ps
```

If `docker ps` requires `sudo`, add yourself to the `docker` group and re-login:

```bash
sudo usermod -aG docker $USER
newgrp docker
```

## Quick start (Docker, the recommended path)

```bash
# 1. Build the sandbox image (one-time, and any time you change
#    backend/Dockerfile.sandbox). `make up` does this for you too.
make sandbox

# 2. Build + start the full stack.
make up

# 3. Open the editor.
open http://localhost:8080        # macOS
xdg-open http://localhost:8080    # Linux
```

`make up` automatically detects the gid of your host's `/var/run/docker.sock`
and injects it into the backend container via `group_add:` so the in-container
`node` user can talk to the daemon. You should see this on stdout:

```
Host docker socket group gid: 1002
```

The first browser request hits `POST /api/containers`, the backend spawns a
fresh `replit-sandbox` container running as the unprivileged `developer` user,
and the editor attaches to its bash PTY.

### Useful Make targets

| Command | Effect |
|---|---|
| `make help` | List all targets with one-line descriptions |
| `make up` | Build the sandbox image and bring the compose stack up |
| `make down` | Stop the stack (keeps images and containers' filesystems) |
| `make restart` | `down` then `up` |
| `make logs` | Tail logs from both services |
| `make ps` | Show the running containers |
| `make sandbox` | Build only the `replit-sandbox` image |
| `make sandbox-rebuild` | Rebuild `replit-sandbox` from scratch (no cache) |
| `make dev` | Hint to run `npm run dev` in `backend/` and `frontend/` |
| `make verify` | Smoke-check that compose config parses and frontend builds |
| `make clean` | Stop the stack, remove sandboxes, remove images |

### Equivalent direct `docker compose` flow

If you'd rather skip the Makefile:

```bash
docker build -f backend/Dockerfile.sandbox -t replit-sandbox backend/
docker compose build
docker compose up
```

> **Linux gotcha:** when invoking Compose directly, pass the docker socket
> gid so the in-container `node` user can read the socket:
>
> ```bash
> DOCKER_GID=$(stat -c '%g' /var/run/docker.sock) docker compose up
> ```
>
> `make up` does this for you. On macOS / Windows the socket is a named
> pipe and `group_add` is silently ignored, so it's safe to set either way.

## Quick start (native dev mode, no Docker)

For faster iteration on either side, run them directly on the host:

```bash
# Terminal 1
cd backend
npm install
npm run dev                       # nodemon on :3001

# Terminal 2
cd frontend
npm install
npm run dev                       # Vite on :5173
```

The Vite dev server proxies `/api` and `/socket.io` to `http://localhost:3001`
(see `frontend/vite.config.js`). In this mode the backend uses the host's
Docker daemon directly (via `/var/run/docker.sock`), so the same docker-group
membership requirement applies.

## How it works

### Frontend (`frontend/src/`)

- `App.jsx` boots the Socket.IO client and wires it to the editor + terminal.
- `components/Editor.jsx` mounts a Monaco editor instance.
- `components/Terminal.jsx` mounts an xterm.js terminal that talks xterm
  escape sequences over a Socket.IO terminal namespace.
- `components/FileTree.jsx` is the workspace file browser.
- `services/socket.js` is the single Socket.IO connection; everything else
  subscribes to its events.

User preferences (theme, font size, etc.) persist in `localStorage` under
the key `replit.editor`.

### Backend (`backend/src/`)

- `server.js` is the Express + Socket.IO entry point. Wires the routes,
  the socket handlers, and the graceful-shutdown container cleanup.
- `config/index.js` is the dependency-free configuration module
  (`PORT`, `SANDBOX_IMAGE`, `SANDBOX_USER`, `AUTO_CLEANUP`, ...).
- `services/docker.js` is the dockerode wrapper. Resolves the sandbox
  image (with a `node:20-slim` fallback for first-boot), creates
  containers, and destroys them.
- `services/sandbox-fs.js` is the in-container file API. Reads/writes
  files by shelling into the running sandbox as the `developer` user.
- `services/terminal.js` is the PTY bridge. Streams xterm escape codes
  between the browser and `docker exec`.
- `state/registry.js` is the in-memory map of container id → dockerode
  handle. Used by the socket disconnect handler to reap sandboxes.
- `routes/` contains the HTTP endpoints (`/api/containers`,
  `/api/files`, `/api/health`).

### Sandboxing model

- Every user gets a fresh container from the `replit-sandbox` image.
- The container runs as the unprivileged `developer` user (not root).
- The container has its own filesystem (no host bind-mounts), so a
  `rm -rf ~` in the user's shell can only nuke the sandbox.
- `Memory: 512 MB`, `NanoCpus: 500_000_000` (0.5 CPU) are set by
  `createSandbox` to cap noisy-neighbor impact.
- `AutoRemove: true` means the Docker daemon reaps the container when
  it stops, so a crashed orchestrator never leaves orphans behind.
- The browser socket's `disconnect` event also triggers explicit
  `destroySandbox` to free resources eagerly.

To keep a sandbox alive after disconnect (useful for debugging), set
`AUTO_CLEANUP=false` in `backend/src/config/index.js` (or pass
`AUTO_CLEANUP=false` in the environment).

## Configuration

All knobs live in `backend/src/config/index.js` and can be overridden
via environment variables (which is how `docker-compose.yml` passes them):

| Env var | Default | Meaning |
|---|---|---|
| `PORT` | `3001` | HTTP port the backend listens on |
| `SANDBOX_IMAGE` | `replit-sandbox` | Image the orchestrator spawns |
| `SANDBOX_USER` | `developer` | In-container user for `docker exec` |
| `AUTO_CLEANUP` | `true` | Reap the sandbox on socket disconnect |
| `DOCKER_SOCKET_PATH` | `/var/run/docker.sock` | Host docker daemon socket |
| `FRONTEND_PORT` (compose) | `8080` | Host port for the Nginx frontend |

## Troubleshooting

### `POST /api/containers` returns 500 with `EACCES /var/run/docker.sock`

The in-container `node` user can't read the host's docker socket. This
means `DOCKER_GID` wasn't propagated into the backend container.

- If you used `make up`, your host user probably isn't in the `docker`
  group; run `sudo usermod -aG docker $USER` and re-login.
- If you used `docker compose` directly, prepend
  `DOCKER_GID=$(stat -c '%g' /var/run/docker.sock)`.
- As a last resort, `sudo chmod 666 /var/run/docker.sock` (revert after
  debugging — it's a security regression).

### `Docker image 'replit-sandbox' not found, falling back to 'node:20-slim'` and then `not available`

You skipped `make sandbox` (or the build failed — see below). Run
`make sandbox` and retry.

### `make sandbox` fails with `GID '1000' already exists`

This is a base-image quirk: recent `node:20-slim` images ship with
`node:x:1000` already, so pinning `--gid 1000` collides. The
`backend/Dockerfile.sandbox` deliberately does NOT pin the id; it lets
`useradd` pick the next free one and dumps the assigned ids to
`/etc/profile.d/developer-ids.sh`. The orchestrator passes the user by
name, so this is transparent.

### Frontend shows the Vite dev page instead of the editor

You probably opened the native dev server (`:5173`) but the backend
isn't running on `:3001`, so the socket connection failed. Either run
`cd backend && npm run dev` in another terminal, or use `:8080` where
everything is bundled.

### Dozens of `puku-sandbox` containers are still running

These are orphans from the pre-rename codebase that don't have
`AutoRemove` enabled. Clean them up with:

```bash
docker ps -aq --filter "ancestor=puku-sandbox" | xargs -r docker rm -f
docker rmi -f puku-sandbox
```

## Development conventions

- `cd backend && npm run dev` (nodemon) for backend iteration.
- `cd frontend && npm run dev` (Vite HMR) for frontend iteration.
- `make verify` runs `docker compose config` + a smoke-boot of the
  backend + a production `vite build`. Run it before pushing.
- Backend files are pure CommonJS; no transpilation step.
- Frontend uses the modern Vite + React (JSX, no TypeScript yet).

## License

This project is intended for local self-hosting. Pick a license that
matches your distribution model before publishing.

## Publishing to Docker Hub

The three service images (`replit-sandbox`, `replit-backend`,
`replit-frontend`) are built to be publishable as-is. The full sequence
is:

```bash
# One-time: create an access token at
#   https://hub.docker.com/settings/security
# and use it as the password below.
docker login

# Build each image locally and push to your namespace.
export DH_USER=your-dockerhub-username   # e.g. suraim001

make sandbox                               # builds replit-sandbox
docker compose build                       # builds replit-{backend,frontend}

for img in replit-sandbox replit-backend replit-frontend; do
  docker tag  $img:latest ${DH_USER}/$img:latest
  docker push ${DH_USER}/$img:latest
done
```

### Running a fresh host against the published images

Once the images are in your Docker Hub namespace, a clean host with no
source tree (just a copy of `docker-compose.yml` +
`docker-compose.published.yml`) can pull and run them with:

```bash
# Same overrides as the local path — picks up DOCKER_GID automatically.
make up-published          # defaults to DH_USER=suraim001
# or with your own namespace:
make up-published DH_USER=yourname
# or one-off:
DH_USE_HUB=true DH_USER=yourname make up
```

Under the hood, `up-published` layers `docker-compose.published.yml`
on top of `docker-compose.yml`. The override uses Compose's `!reset null`
extension tag to drop the `build:` blocks and point both services at
`${DH_USER}/replit-*` images, and rewrites the backend's
`SANDBOX_IMAGE` env var so the orchestrator spawns from the published
sandbox image too.

### What the override does

```yaml
# docker-compose.published.yml (excerpt)
services:
  backend:
    build: !reset null                  # drop the build: block
    image: ${DH_USER:-suraim001}/replit-backend:latest
    environment:
      SANDBOX_IMAGE: ${DH_USER:-suraim001}/replit-sandbox:latest
  frontend:
    build: !reset null
    image: ${DH_USER:-suraim001}/replit-frontend:latest
```

`!reset null` is the documented Compose extension tag that removes a
key from the merged config — it lets the override completely replace
`build:` with `image:` without copying every other key.

### Multi-arch notes

The images built by the included Dockerfiles are `linux/amd64` only.
To publish for both amd64 and arm64 (e.g. Apple Silicon servers,
Raspberry Pi clusters), swap `docker build` / `docker push` for
`docker buildx build --platform linux/amd64,linux/arm64 --push …`:

```bash
docker buildx create --use
docker buildx build --platform linux/amd64,linux/arm64 \
  -f backend/Dockerfile.sandbox \
  -t ${DH_USER}/replit-sandbox:latest --push backend/
docker buildx build --platform linux/amd64,linux/arm64 \
  -f backend/Dockerfile \
  -t ${DH_USER}/replit-backend:latest --push backend/
docker buildx build --platform linux/amd64,linux/arm64 \
  -f frontend/Dockerfile \
  -t ${DH_USER}/replit-frontend:latest --push frontend/
```
