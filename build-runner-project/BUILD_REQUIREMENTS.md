# Build Requirements — What your repo must contain

The build runner does `docker build <repo-root>` and then redeploys the resulting
image on port `8080` (mapped to host port `DEMO_PORT`, e.g. `8080`). If anything
in the chain is missing or wrong, the job ends with `status: failed` and an
error message in the `message` field.

## ✅ Minimum required

| Item | Where | Why | Example |
|---|---|---|---|
| `Dockerfile` | **repo root** (not subfolder) | `docker_builder.py:48` rejects if missing | `/Dockerfile` |
| Working `Dockerfile` | — | `docker build` must exit 0 | See below |
| App that listens on **port 8080** | Inside the image | Worker runs `docker run -p 8080:8080` | `EXPOSE 8080` + `CMD` |

### Minimal working `Dockerfile` (Python example)

```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY app.py .
EXPOSE 8080
CMD ["python", "-m", "http.server", "8080"]
```

Repo: [github.com/iftakhar-323/demo-app](https://github.com/iftakhar-323/demo-app) —
this is the verified working example.

## ❌ What will fail (and what message you'll see)

| # | Problem | Stage | Status | Error message |
|---|---|---|---|---|
| 1 | Repo is **private** (or token missing read access) | `clone_repo` | `failed` | `git clone error: Authentication failed for ...` |
| 2 | Repo URL is **404** / wrong owner | `clone_repo` | `failed` | `git clone error: Could not resolve host` or `not found` |
| 3 | **No `Dockerfile` in repo root** | `build_image` | `failed` | `Build failed: Dockerfile not found in repo` |
| 4 | `Dockerfile` exists but `docker build` fails (bad syntax, missing file in `COPY`, network during `pip install`, etc.) | `build_image` | `failed` | `Build failed: <last docker error line>` |
| 5 | Image is too large / build hits Docker daemon memory limit | `build_image` | `failed` | `Build failed: <OOM message>` |
| 6 | `docker push` to ghcr.io fails (token expired / wrong scope) | `push_and_deploy` | `failed` | `push failed: <ghcr error>` |
| 7 | App inside image does **not listen on 8080** | `deploy` (still `success`!) | `success` ⚠️ | Container starts, but `curl :8080` returns nothing — your app must bind `0.0.0.0:8080` |

> **Note on #7:** The build runner treats `docker run` exit 0 as success. If your
> app crashes inside the container, the job will show `success` but the
> container will be unhealthy. Check `docker logs demo-app` to diagnose.

## 🔒 Optional / situational

- **Public repo** — required (worker only has your personal `GITHUB_PAT`, not
  arbitrary user tokens). Private repos work *only* if your PAT has access.
- **Subfolder Dockerfile** — **not supported**. The runner only looks at
  `<repo-root>/Dockerfile`. If your app is in `my-backend/`, move the
  Dockerfile to the root or symlink it.
- **`.dockerignore`** — recommended (excludes `.git`, `node_modules`, etc.),
  but optional.
- **Build context size** — anything over ~1 GB will likely time out
  (the worker enforces a 30 min `docker build` timeout in `docker_builder.py`).

## 🧪 Quick test matrix

| Repo | Has Dockerfile? | App on 8080? | Result |
|---|---|---|---|
| `iftakhar-323/demo-app` | ✅ | ✅ | ✅ `success` — `Hello v1 from build runner!` |
| `shihad323/Lather` | ❌ | n/a | ❌ `failed` — `Dockerfile not found in repo` |
| `docker/welcome-to-docker` | ✅ | ✅ | ✅ `success` |
| Any repo with `Dockerfile` in subfolder only | ❌ (in root) | n/a | ❌ `failed` — `Dockerfile not found in repo` |

## 🛠️ Common fixes

1. **"Dockerfile not found"** → add a `Dockerfile` to repo root, commit, push,
   re-trigger build.
2. **"Cannot find module X" during `pip install`** → your `requirements.txt` is
   incomplete. Add the missing package and rebuild.
3. **"Port 8080 already in use"** → another container is using `DEMO_PORT`.
   Run `docker ps` to find it, then `docker rm -f <name>`.
4. **"denied: permission to X/Y.git" during push** → your `GITHUB_PAT` doesn't
   have `write:packages` scope for that org. Regenerate the PAT with the right
   scopes (or use a PAT scoped to your own org).
5. **Build succeeds but `curl :8080` hangs** → your app is binding `127.0.0.1`
   instead of `0.0.0.0`. Change `CMD` to listen on `0.0.0.0`.
