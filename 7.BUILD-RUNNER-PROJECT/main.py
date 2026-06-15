"""FastAPI server for the Build Runner.

Endpoints:
  GET  /              health
  POST /build         submit a build job   (header: X-API-Key)
  GET  /status/{id}   poll job status
  WS   /logs/{id}     stream live logs (build output + status) for a job
  POST /webhook/github   receive a `push` event and auto-queue a build
"""
import asyncio
import hashlib
import hmac
import json
import os
import uuid

import redis
import redis.asyncio as aioredis
from fastapi import (
    FastAPI,
    Header,
    HTTPException,
    Request,
    WebSocket,
    WebSocketDisconnect,
    status,
)
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

app = FastAPI(title="Build Runner")

REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
API_KEY = os.getenv("API_KEY", "")
GITHUB_WEBHOOK_SECRET = os.getenv("GITHUB_WEBHOOK_SECRET", "")

# sync redis for endpoint handlers (FastAPI runs sync routes in a threadpool)
r = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True)

# async redis used by the WebSocket handler
ar = aioredis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True)

LOG_KEY = "logs:{}"
JOB_KEY = "job:{}"
BUILD_QUEUE = "build_queue"
HISTORY_LIMIT = 50


# serve the static frontend (index.html, app.js, style.css)
STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
os.makedirs(STATIC_DIR, exist_ok=True)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


# ---------- helpers ---------------------------------------------------------

def _check_api_key(x_api_key: str = Header(default="")) -> None:
    """Reject requests without a valid API key (skip when API_KEY is unset)."""
    if not API_KEY:  # dev mode: no key configured -> open
        return
    if not hmac.compare_digest(x_api_key or "", API_KEY):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid or missing API key")


def _enqueue(job_id: str, github_url: str) -> None:
    job = {"job_id": job_id, "github_url": github_url, "status": "queued"}
    r.set(JOB_KEY.format(job_id), json.dumps(job))
    r.lpush(BUILD_QUEUE, json.dumps({"job_id": job_id, "github_url": github_url}))


# ---------- routes ----------------------------------------------------------

@app.get("/")
def home():
    """Serve the minimal frontend (falls back to JSON if static dir is empty)."""
    index = os.path.join(STATIC_DIR, "index.html")
    if os.path.exists(index):
        return FileResponse(index)
    return {"message": "Build Runner System is alive!"}


@app.get("/requirements")
def requirements_doc():
    """Serve the BUILD_REQUIREMENTS.md doc as plain text."""
    md_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "BUILD_REQUIREMENTS.md")
    if not os.path.exists(md_path):
        raise HTTPException(404, "BUILD_REQUIREMENTS.md not found")
    return FileResponse(md_path, media_type="text/markdown")


@app.get("/history")
def history():
    """List recent jobs (newest first) by scanning the job:* keys in Redis."""
    jobs = []
    for key in r.scan_iter(match="job:*", count=200):
        raw = r.get(key)
        if not raw:
            continue
        try:
            job = json.loads(raw)
        except Exception:
            continue
        # newest first; jobs created later will overwrite the same key, so
        # use the job_id timestamp prefix (uuid4 has time-based component)
        jobs.append(job)
    # sort by job_id (uuid1-ish) descending; fall back to original order
    jobs.sort(key=lambda j: j.get("job_id", ""), reverse=True)
    return {"jobs": jobs[:HISTORY_LIMIT]}


@app.post("/build")
def start_build(github_url: str, x_api_key: str = Header(default="")):
    _check_api_key(x_api_key)
    if not github_url.startswith(("http://", "https://")):
        raise HTTPException(400, "github_url must be http(s)")

    job_id = str(uuid.uuid4())
    _enqueue(job_id, github_url)
    return {"job_id": job_id, "status": "queued"}


@app.get("/status/{job_id}")
def get_status(job_id: str):
    raw = r.get(JOB_KEY.format(job_id))
    if not raw:
        raise HTTPException(404, "job not found")
    return json.loads(raw)


@app.post("/webhook/github")
async def github_webhook(request: Request):
    """Verify the GitHub HMAC-SHA256 signature, then queue a build on push."""
    body = await request.body()
    signature = request.headers.get("X-Hub-Signature-256", "")
    event = request.headers.get("X-GitHub-Event", "")

    if not GITHUB_WEBHOOK_SECRET:
        raise HTTPException(503, "GITHUB_WEBHOOK_SECRET not configured")
    if not signature.startswith("sha256="):
        raise HTTPException(400, "missing sha256 signature")
    expected = "sha256=" + hmac.new(
        GITHUB_WEBHOOK_SECRET.encode(), body, hashlib.sha256
    ).hexdigest()
    if not hmac.compare_digest(signature, expected):
        raise HTTPException(401, "invalid signature")

    if event != "push":
        return {"ignored": event}

    payload = json.loads(body or b"{}")
    repo = payload.get("repository", {}).get("clone_url") or payload.get(
        "repository", {}
    ).get("html_url")
    ref = payload.get("ref", "")
    # only build the default branch (refs/heads/main or refs/heads/master)
    if not repo:
        raise HTTPException(400, "no repo in payload")
    if not ref.endswith(("/main", "/master")):
        return {"ignored": f"ref={ref}"}

    job_id = str(uuid.uuid4())
    _enqueue(job_id, repo)
    return {"queued": job_id, "repo": repo, "ref": ref}


# ---------- websocket: live log + status feed -------------------------------

@app.websocket("/logs/{job_id}")
async def websocket_logs(websocket: WebSocket, job_id: str):
    await websocket.accept()
    last_log_count = 0
    try:
        while True:
            # status update
            raw = await ar.get(JOB_KEY.format(job_id))
            if raw:
                job = json.loads(raw)
                await websocket.send_text(json.dumps({"type": "status", **job}))

                # replay any new log lines since last tick
                lines = await ar.lrange(LOG_KEY.format(job_id), 0, -1)
                # LRANGE returns newest first; we only send ones we haven't sent
                if lines:
                    new_count = len(lines)
                    if new_count > last_log_count:
                        # the list grew -> send the new tail (still newest-first)
                        for line in lines[: new_count - last_log_count]:
                            await websocket.send_text(
                                json.dumps({"type": "log", "line": line})
                            )
                        last_log_count = new_count
                    elif new_count < last_log_count:
                        # list was trimmed/capped, reset
                        last_log_count = new_count

                if job.get("status") in ("success", "failed"):
                    break
            else:
                await websocket.send_text(
                    json.dumps({"type": "error", "message": "job not found"})
                )
                break

            await asyncio.sleep(0.5)
    except WebSocketDisconnect:
        pass
    finally:
        try:
            await websocket.close()
        except Exception:
            pass