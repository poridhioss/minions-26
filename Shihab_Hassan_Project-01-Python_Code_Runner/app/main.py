"""Secure Python Code Runner — backend.

A single-file FastAPI app designed to be easy to read for an
internship review. It contains:

  * Pydantic request/response models
  * SQLite-based execution history
  * A small in-memory rate limiter (per IP)
  * A code validator that rejects obviously dangerous patterns
  * A DockerService that runs untrusted code in a hardened container
  * REST endpoints: /api/run, /api/history, /api/health

Run locally (with Docker installed):
    uvicorn app.main:app --reload
"""

from __future__ import annotations

import os
import re
import time
import uuid
import base64
import sqlite3
import logging
from contextlib import contextmanager
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Optional

import docker
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

# ──────────────────────────────────────────────────────────────────────
# Configuration
# ──────────────────────────────────────────────────────────────────────

DOCKER_IMAGE     = os.getenv("DOCKER_IMAGE", "code-runner:latest")
DOCKER_TIMEOUT   = int(os.getenv("DOCKER_TIMEOUT", "10"))    # seconds
DOCKER_MEMORY    = os.getenv("DOCKER_MEMORY", "128m")
DOCKER_CPU_QUOTA = float(os.getenv("DOCKER_CPU_QUOTA", "0.5"))  # 1.0 = 1 CPU
MAX_CODE_LENGTH  = int(os.getenv("MAX_CODE_LENGTH", "10000"))
RATE_LIMIT_PER_M = int(os.getenv("RATE_LIMIT_PER_MIN", "30"))
DB_PATH          = os.getenv("DB_PATH", "data/history.db")

Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger("code-runner")


# ──────────────────────────────────────────────────────────────────────
# Database — a tiny SQLite wrapper (no ORM, plain SQL for clarity)
# ──────────────────────────────────────────────────────────────────────

def init_db() -> None:
    """Create the executions table if it does not exist yet."""
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS executions (
                id           TEXT PRIMARY KEY,
                code         TEXT    NOT NULL,
                stdout       TEXT,
                stderr       TEXT,
                exit_code    INTEGER,
                duration_ms  INTEGER,
                status       TEXT,
                created_at   TEXT
            )
            """
        )
        conn.commit()


@contextmanager
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


# ──────────────────────────────────────────────────────────────────────
# Security helpers
# ──────────────────────────────────────────────────────────────────────

# Patterns we refuse to run. The sandbox would block them too, but
# rejecting early saves a container and makes intent obvious.
DANGEROUS_PATTERNS = [
    r"\bos\.system\b",
    r"\bsubprocess\b",
    r"\beval\s*\(",
    r"\bexec\s*\(",
    r"\b__import__\b",
    r"\bopen\s*\([^)]*['\"]\w['\"],[^)]*['\"]w['\"]",   # open(..., 'w')
    r"\bshutil\b",
    r"\bsocket\b",
    r"\brequests\b",
    r"\burllib\b",
]
DANGER_RE = re.compile("|".join(DANGEROUS_PATTERNS))


def validate_code(code: str) -> Optional[str]:
    """Return an error message if the code is invalid, else None."""
    code = code.strip()
    if not code:
        return "Code is empty."
    if len(code) > MAX_CODE_LENGTH:
        return f"Code too long ({len(code)} > {MAX_CODE_LENGTH} chars)."
    if DANGER_RE.search(code):
        return "Code contains a blocked construct (network, fs write, eval, ...)."
    return None


class RateLimiter:
    """Naive per-IP sliding-window rate limiter. Good enough for demo."""

    def __init__(self, max_requests: int, window_seconds: int = 60):
        self.max = max_requests
        self.window = window_seconds
        self.hits: dict[str, list[float]] = {}

    def check(self, key: str) -> bool:
        now = time.time()
        bucket = [t for t in self.hits.get(key, []) if now - t < self.window]
        if len(bucket) >= self.max:
            self.hits[key] = bucket
            return False
        bucket.append(now)
        self.hits[key] = bucket
        return True


limiter = RateLimiter(RATE_LIMIT_PER_M)


# ──────────────────────────────────────────────────────────────────────
# Pydantic models
# ──────────────────────────────────────────────────────────────────────

class RunRequest(BaseModel):
    code:  str = Field(..., min_length=1, max_length=MAX_CODE_LENGTH)
    stdin: str = Field(default="")


class RunResponse(BaseModel):
    id:          str
    stdout:      str
    stderr:      str
    exit_code:   int
    duration_ms: int
    status:      str   # SUCCESS | ERROR | TIMEOUT


# ──────────────────────────────────────────────────────────────────────
# Docker sandbox
# ──────────────────────────────────────────────────────────────────────

@dataclass
class ExecResult:
    stdout:      str
    stderr:      str
    exit_code:   int
    duration_ms: int
    status:      str


# A tiny bootstrap script that runs inside the sandbox. It pulls the
# user code + stdin from environment variables, decodes them, and
# exec()s the code. We pass the user payload via env vars (not
# stdin / not filesystem) because:
#   * docker SDK 7+ removed `stdin=` from containers.run()
#   * the rootfs is read-only so we can't `put_archive` user code
#   * the network is disabled so we can't fetch code from a URL
# The code never touches the host's disk and never escapes the
# container.
SANDBOX_BOOTSTRAP = """
import os, sys, base64, io
code     = base64.b64decode(os.environ.pop('CODE_B64', '')).decode('utf-8')
stdin_dt = base64.b64decode(os.environ.pop('STDIN_B64', '')).decode('utf-8')
sys.stdin = io.StringIO(stdin_dt)
exec(compile(code, '<user>', 'exec'))
"""


class DockerService:
    """Run untrusted Python code inside a hardened Docker container."""

    def __init__(self):
        self.client: Optional[docker.DockerClient] = None
        try:
            self.client = docker.from_env()
            self.client.ping()
            log.info("Connected to Docker daemon.")
        except Exception as e:
            log.error("Docker not reachable: %s", e)

    def run(self, code: str, stdin: str = "",
            timeout: int = DOCKER_TIMEOUT) -> ExecResult:
        if not self.client:
            return ExecResult("", "Docker daemon not reachable.",
                               -1, 0, "ERROR")

        start = time.time()
        container = None
        try:
            # We use the lower-level create+start+exec_run path. The
            # container just runs `sleep` so the namespace stays alive
            # long enough to exec into it. All real work is done by
            # the `python -c <bootstrap>` exec call below.
            container = self.client.containers.create(
                image=DOCKER_IMAGE,
                command=["sleep", "30"],
                detach=True,
                # ── Defense in depth ──────────────────────────────────
                network_mode="none",            # no network access
                read_only=True,                  # read-only root FS
                user="nobody",                   # unprivileged user
                mem_limit=DOCKER_MEMORY,         # hard memory cap
                memswap_limit=DOCKER_MEMORY,     # no swap
                cpu_quota=int(DOCKER_CPU_QUOTA * 100_000),
                cpu_period=100_000,
                pids_limit=64,                   # no fork-bomb
                security_opt=["no-new-privileges"],
                cap_drop=["ALL"],                # drop all capabilities
                tmpfs={"/tmp": "size=10m,noexec"},
                environment={"PYTHONUNBUFFERED": "1"},
            )
            container.start()

            code_b64   = base64.b64encode(code.encode("utf-8")).decode("ascii")
            stdin_b64  = base64.b64encode(stdin.encode("utf-8")).decode("ascii")

            try:
                exec_res = container.exec_run(
                    cmd=["python", "-c", SANDBOX_BOOTSTRAP],
                    detach=False,
                    user="nobody",
                    environment={
                        "CODE_B64":  code_b64,
                        "STDIN_B64": stdin_b64,
                        "PYTHONUNBUFFERED": "1",
                    },
                )
                stdout     = exec_res.output.decode("utf-8", errors="replace") if exec_res.output else ""
                exit_code  = exec_res.exit_code
                stderr     = ""  # exec_run merges stderr into output
                status_str = "SUCCESS" if exit_code == 0 else "ERROR"
            except Exception:
                # Timeout — kill the container
                try:
                    container.kill()
                except Exception:
                    pass
                stdout, stderr, exit_code = "", "Execution timed out.", 124
                status_str = "TIMEOUT"
        except Exception as e:
            return ExecResult("", f"Failed to start container: {e}",
                               -1, 0, "ERROR")
        finally:
            if container is not None:
                try:
                    container.remove(force=True)
                except Exception:
                    pass

        return ExecResult(
            stdout=stdout,
            stderr=stderr,
            exit_code=exit_code,
            duration_ms=int((time.time() - start) * 1000),
            status=status_str,
        )


# ──────────────────────────────────────────────────────────────────────
# FastAPI application
# ──────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="Secure Python Code Runner",
    version="1.0.0",
    description="Run untrusted Python code safely inside a Docker sandbox.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

docker_svc = DockerService()


@app.on_event("startup")
def _startup() -> None:
    init_db()
    log.info("API ready  image=%s  timeout=%ss  mem=%s",
             DOCKER_IMAGE, DOCKER_TIMEOUT, DOCKER_MEMORY)


# ── Health ───────────────────────────────────────────────────────────

@app.get("/api/health")
def health():
    return {
        "status": "ok",
        "docker_available": docker_svc.client is not None,
        "image": DOCKER_IMAGE,
    }


# ── Run code ─────────────────────────────────────────────────────────

def _client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


@app.post("/api/run", response_model=RunResponse)
def run_code(payload: RunRequest, request: Request):
    ip = _client_ip(request)
    if not limiter.check(ip):
        raise HTTPException(status_code=429, detail="Rate limit exceeded. Slow down.")

    err = validate_code(payload.code)
    if err:
        raise HTTPException(status_code=400, detail=err)

    log.info("run request  ip=%s  len=%d", ip, len(payload.code))
    result = docker_svc.run(payload.code, payload.stdin)

    exec_id = str(uuid.uuid4())
    with get_db() as conn:
        conn.execute(
            """INSERT INTO executions
               (id, code, stdout, stderr, exit_code, duration_ms, status, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (exec_id, payload.code, result.stdout, result.stderr,
             result.exit_code, result.duration_ms, result.status,
             datetime.utcnow().isoformat()),
        )
    return RunResponse(id=exec_id, **asdict(result))


# ── History ──────────────────────────────────────────────────────────

@app.get("/api/history")
def list_history(limit: int = 20):
    limit = max(1, min(limit, 100))
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM executions ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [dict(r) for r in rows]


@app.get("/api/history/{exec_id}")
def get_history(exec_id: str):
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM executions WHERE id = ?", (exec_id,)
        ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Not found")
    return dict(row)


# ── Static frontend (single-page app) ───────────────────────────────

# Resolve the frontend dir relative to the project root (the parent of
# `app/`). This works both in dev (`uvicorn app.main:app` from the repo
# root) and inside the Docker image (where WORKDIR=/app and we copy
# frontend/ next to app/).
STATIC_DIR_CANDIDATES = [
    Path(__file__).resolve().parent.parent / "frontend",   # ../frontend  (dev + Docker)
    Path(__file__).resolve().parent / "frontend",          # ./frontend   (alt layout)
]

STATIC_DIR: Optional[Path] = None
for candidate in STATIC_DIR_CANDIDATES:
    if candidate.exists():
        STATIC_DIR = candidate
        break

if STATIC_DIR is not None:
    # Mount under root so "/" serves index.html. Must be the LAST route
    # added to the app because it catches every path.
    app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="frontend")
    log.info("Serving frontend from %s", STATIC_DIR)
else:
    log.warning(
        "Frontend directory not found. Tried: %s. "
        "The API will still work, but the UI at '/' will 404.",
        [str(p) for p in STATIC_DIR_CANDIDATES],
    )


# ── Friendly error handler ──────────────────────────────────────────

@app.exception_handler(Exception)
def _on_error(_: Request, exc: Exception):
    log.exception("Unhandled error")
    return JSONResponse(status_code=500, content={"detail": str(exc)})
