# Secure Online Python Code Runner: Build a Hardened Code Execution Sandbox

A production-style web application that safely executes untrusted Python
code inside isolated Docker containers. This lab teaches FastAPI, Docker
hardening, Linux security primitives, and container-based sandboxing by
building the system from scratch.

> One-sentence pitch: Users paste Python into a web editor, hit Run, and
> receive stdout, stderr, and exit code. The code executes inside a
> throwaway container with no network, a read-only root filesystem, no
> Linux capabilities, and a strict CPU, memory, and time budget.

---

## Table of Contents

1. [Introduction](#introduction)
2. [Learning Objectives](#learning-objectives)
3. [Prologue: The Challenge](#prologue-the-challenge)
4. [Environment Setup](#environment-setup)
5. [Chapter 1: The Project Skeleton](#chapter-1-the-project-skeleton)
6. [Chapter 2: A Working Web API](#chapter-2-a-working-web-api)
7. [Chapter 3: Static Analysis and Rate Limiting](#chapter-3-static-analysis-and-rate-limiting)
8. [Chapter 4: The Docker Sandbox](#chapter-4-the-docker-sandbox)
9. [Chapter 5: Wiring It Together](#chapter-5-wiring-it-together)
10. [Chapter 6: The Frontend](#chapter-6-the-frontend)
11. [Chapter 7: Persistence and Observability](#chapter-7-persistence-and-observability)
12. [Chapter 8: Hardening Experiments](#chapter-8-hardening-experiments)
13. [Epilogue: The Complete System](#epilogue-the-complete-system)
14. [The Principles](#the-principles)
15. [Troubleshooting](#troubleshooting)
16. [Next Steps](#next-steps)
17. [Additional Resources](#additional-resources)

---

## Introduction

This lab teaches the engineering behind a code-execution service like
HackerRank, LeetCode, or Google Colab. Such services receive untrusted
source code from the public internet, execute it, and return the result.
A single missed defense turns the platform into a botnet, a data
exfiltration tool, or a host takeover.

The lab takes an active approach: predict outcomes before running, fill
in blanks in the code, break things on purpose to see why defenses
matter, and self-assess understanding after each chapter.

**Prerequisites:** Basic Python, familiarity with the command line, and
comfort reading Docker documentation.

---

## Learning Objectives

By the end of this lab, you will be able to:

1. Create a FastAPI application with health, run, and history endpoints.
2. Implement request validation using Pydantic models and custom
   static-analysis rules.
3. Build a per-IP sliding-window rate limiter.
4. Construct a hardened Docker sandbox image using non-root users,
   capability drops, and read-only filesystems.
5. Use the Docker Python SDK to create, start, exec into, and remove
   containers programmatically.
6. Persist execution history in SQLite without an ORM.
7. Serve a single-page frontend with FastAPI's StaticFiles mount.
8. Diagnose common security and container-related failure modes.

---

## Prologue: The Challenge

You join the platform safety team at an online learning company.
Students need a web editor where they can write Python and see results
immediately, similar to Codecademy or Replit. The team has decided to
build the service in-house to keep infrastructure costs low and to
maintain control over what runs on the production hosts.

The danger is real. A user who can run arbitrary Python on the host
can read secrets, exfiltrate the database, mine cryptocurrency, pivot
to internal services, and break the service for everyone. The lab
treats every line of submitted code as hostile.

Your task: build a working code runner that safely executes untrusted
Python and returns stdout, stderr, exit code, and duration. The runner
must reject obviously dangerous patterns before they reach the
container, and the container must fail closed if a defense is missing.

Success criteria:

- A user can paste Python into a web page, click Run, and see output.
- A user attempting to import `subprocess`, `socket`, `requests`, or
  call `eval` is rejected with a clear error.
- A user who somehow gets past validation cannot reach the network,
  cannot write to the host filesystem, and cannot exceed a 128 MB
  memory or 10 second time budget.
- Every execution is recorded in a database the team can query.

---

## Environment Setup

You will need Docker, Python 3.10 or later, and either Git Bash, WSL,
or a Unix shell. Windows users with Docker Desktop work normally;
PowerShell commands are noted where they differ.

### 1. Install prerequisites

```bash
# Update package lists
sudo apt update
sudo apt install -y python3-venv python3-pip curl

# Verify Docker is installed and the daemon is reachable
docker --version
docker ps
```

Expected output for `docker ps`:

```
CONTAINER ID   IMAGE     COMMAND   CREATED   STATUS    PORTS     NAMES
```

An empty list (no error) means the daemon is running.

### 2. Clone and enter the project

```bash
git clone <your-repo>
cd Shihab_Hassan_Project-Python_Code_Runner
```

### 3. Create a Python virtual environment

```bash
python3 -m venv .venv
source .venv/bin/activate          # macOS / Linux
# .venv\Scripts\Activate.ps1       # Windows PowerShell
```

### 4. Install Python dependencies

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

The `requirements.txt` contains:

- `fastapi` - web framework
- `uvicorn` - ASGI server
- `pydantic` - request and response validation
- `docker` - Python SDK for the Docker Engine API
- `pytest` - unit test runner

### 5. Create the project structure

```bash
mkdir -p app frontend docker/runner tests docs data
touch app/__init__.py
```

### 6. Final layout

```
.
├── app/
│   ├── __init__.py
│   └── main.py             # FastAPI app, Docker service, DB
├── docker/
│   └── runner/
│       └── Dockerfile      # Minimal sandbox image
├── frontend/
│   └── index.html          # Single-page UI
├── tests/
│   └── test_main.py        # Unit tests
├── docs/                   # Notes and architecture diagrams
├── data/                   # SQLite database lives here
├── docker-compose.yml      # One-service stack
├── Dockerfile              # API image
├── requirements.txt
├── .env.example
├── .gitignore
└── README.md
```

---

## Chapter 1: The Project Skeleton

A code-execution service has three concerns that must remain separate:
the public HTTP API, the sandbox where user code runs, and storage for
audit logs. The first chapter creates the directory layout and the
minimal FastAPI app that responds to health checks.

### 1.1 What You Will Build

A FastAPI application with a single endpoint, `/api/health`, that
returns the application status. This proves the toolchain works before
the rest of the system is built on top of it.

### 1.2 Think First: The Health Endpoint

**Question:** Why does a backend service need a health endpoint that
returns the status of a downstream dependency (in our case, the Docker
daemon) and not just `{"status": "ok"}`?

<details>
<summary>Click to review</summary>

A health endpoint that returns 200 even when the dependency is
unhealthy misleads load balancers and on-call engineers. The container
is technically running, but the system cannot fulfill requests.
Reporting downstream status lets the platform remove the instance from
rotation automatically and surfaces the real failure.

</details>

### 1.3 Implementation

Create `app/main.py` with the following content. The blanks are
intentional: fill them in before reading the solution.

```python
from fastapi import FastAPI

app = FastAPI(
    title=___,                  # Q1: A short name for the docs UI
    version=___,                # Q2: Use "1.0.0"
)

docker_svc = None  # filled in Chapter 4


@app.get("/api/health")
def health():
    return {
        "status": ___,                       # Q3: A string that means "running"
        "docker_available": ___,             # Q4: A bool
    }
```

Hints:

- Q1 hint: it is a string, often the project name
- Q4 hint: will become `docker_svc.client is not None` later

<details>
<summary>Click to see solution</summary>

```python
from fastapi import FastAPI

app = FastAPI(
    title="Secure Python Code Runner",
    version="1.0.0",
)

docker_svc = None


@app.get("/api/health")
def health():
    return {
        "status": "ok",
        "docker_available": False,
    }
```

</details>

### 1.4 Understanding the Code

Match each line to its purpose:

| Code | Purpose (A-D) |
|------|---------------|
| `FastAPI(...)` | ___ |
| `@app.get("/api/health")` | ___ |
| `def health():` | ___ |
| `return {...}` | ___ |

**Options:**

- A: Registers a route handler for HTTP GET
- B: Defines the function that runs on each request
- C: Sends a JSON response to the client
- D: Creates the application instance with metadata

<details>
<summary>Click to review</summary>

| Code | Purpose |
|------|---------|
| `FastAPI(...)` | D |
| `@app.get("/api/health")` | A |
| `def health():` | B |
| `return {...}` | C |

</details>

### 1.5 Test and Verify

Run the development server:

```bash
uvicorn app.main:app --reload --port 8000
```

In another terminal:

```bash
curl http://localhost:8000/api/health
```

**Predict:** What JSON will the server return?

<details>
<summary>Click to review</summary>

```json
{"status":"ok","docker_available":false}
```

</details>

Also visit `http://localhost:8000/docs` in a browser. FastAPI generates
an interactive API explorer from the type hints and route decorators.

### 1.6 Checkpoint

**Self-Assessment:**

- [ ] The server starts without errors
- [ ] `/api/health` returns the predicted JSON
- [ ] `/docs` renders the API explorer
- [ ] You can explain what `docker_available` will eventually report

### 1.7 Experiment: Broken Import

Stop the server (Ctrl+C), then change the import line in `app/main.py`
to:

```python
from fastapi import FastAPIX
```

Restart the server.

**Observe:** The application fails to start. The traceback mentions
`ModuleNotFoundError`.

**Question:** Why does FastAPI not return a 500 error here the way it
would for a runtime error inside a handler?

Restore the correct import before continuing.

---

## Chapter 2: A Working Web API

The health endpoint proves the toolchain. This chapter adds the
endpoint that will eventually execute user code. The endpoint accepts
a request, validates the input shape, and returns a placeholder
response. Real execution is added in Chapter 4.

### 2.1 What You Will Build

A `POST /api/run` endpoint that accepts JSON of the form
`{"code": "...", "stdin": "..."}` and returns a structured response
with `id`, `stdout`, `stderr`, `exit_code`, `duration_ms`, and
`status`. For now, the endpoint echoes a stub response.

### 2.2 Think First: Request and Response Models

**Question:** Why use Pydantic models for the request and response
instead of accepting and returning plain dictionaries?

<details>
<summary>Click to review</summary>

Pydantic validates types, enforces length limits, and produces clear
error messages before the handler runs. Returning a typed model
guarantees the response always has the same shape, even when fields
are added later. Plain dictionaries give up all of those guarantees
for a few lines of saved typing.

</details>

### 2.3 Implementation

Add the following to `app/main.py` after the `health` endpoint.

```python
from fastapi import HTTPException
from pydantic import BaseModel, Field
import uuid

MAX_CODE_LENGTH = 10000


class RunRequest(BaseModel):
    code:  str = Field(..., min_length=___, max_length=___)  # Q1, Q2
    stdin: str = Field(default=___)                          # Q3


class RunResponse(BaseModel):
    id:          str
    stdout:      str
    stderr:      str
    exit_code:   int
    duration_ms: int
    status:      str   # SUCCESS | ERROR | TIMEOUT


@app.post("/api/run", response_model=RunResponse)
def run_code(payload: RunRequest):
    if not payload.code.strip():
        raise HTTPException(status_code=___, detail=___)  # Q4, Q5

    return RunResponse(
        id=str(uuid.uuid4()),
        stdout="(execution not implemented yet)",
        stderr="",
        exit_code=0,
        duration_ms=0,
        status="SUCCESS",
    )
```

Hints:

- Q1: minimum length; a non-empty string is `1`
- Q4: HTTP status for "the client sent bad data" is `400`
- Q5: a short message such as `"Code is empty."`

<details>
<summary>Click to see solution</summary>

```python
class RunRequest(BaseModel):
    code:  str = Field(..., min_length=1, max_length=MAX_CODE_LENGTH)
    stdin: str = Field(default="")


@app.post("/api/run", response_model=RunResponse)
def run_code(payload: RunRequest):
    if not payload.code.strip():
        raise HTTPException(status_code=400, detail="Code is empty.")

    return RunResponse(
        id=str(uuid.uuid4()),
        stdout="(execution not implemented yet)",
        stderr="",
        exit_code=0,
        duration_ms=0,
        status="SUCCESS",
    )
```

</details>

### 2.4 Understanding the Code

Answer in one sentence each:

1. What does `Field(..., min_length=1)` do?
2. What HTTP status does FastAPI return automatically if you send
   `{"code": 123}` instead of a string?
3. Why does `run_code` use `payload.code.strip()` instead of just
   `payload.code`?

<details>
<summary>Click to review</summary>

1. It rejects empty strings with a 422 validation error before the
   handler runs.
2. HTTP 422 Unprocessable Entity, with a JSON body listing the
   invalid field.
3. To treat whitespace-only input the same as empty input.

</details>

### 2.5 Test and Verify

With the server running:

```bash
curl -X POST http://localhost:8000/api/run \
  -H "Content-Type: application/json" \
  -d '{"code": "print(2+2)"}'
```

**Predict:** What will `stdout` contain?

<details>
<summary>Click to review</summary>

`"(execution not implemented yet)"` - execution is added in Chapter 4.

</details>

Try sending invalid input:

```bash
curl -X POST http://localhost:8000/api/run \
  -H "Content-Type: application/json" \
  -d '{"code": ""}'
```

**Predict:** What status code?

<details>
<summary>Click to review</summary>

HTTP 400 with `{"detail":"Code is empty."}`. The Pydantic `min_length`
would also have caught this, but the explicit check produces a clearer
message.

</details>

### 2.6 Checkpoint

**Self-Assessment:**

- [ ] A valid request returns a 200 with all expected fields
- [ ] Empty code returns 400 with a clear message
- [ ] A non-string code field returns 422
- [ ] You can explain the difference between 400 and 422

### 2.7 Experiment: Bypassing Validation

Try sending the request with `Content-Type` set to
`text/plain` and a JSON body. Then try omitting the `Content-Type`
header entirely.

**Observe:** The server returns 422 because FastAPI cannot parse the
body as JSON. This is a defense by accident: malformed clients fail
before the handler runs.

---

## Chapter 3: Static Analysis and Rate Limiting

Before code ever reaches a container, two cheap defenses should run:
a regex-based static analyzer that blocks obviously dangerous Python
constructs, and a per-IP rate limiter that stops brute-force abuse.

### 3.1 What You Will Build

A `validate_code` function that returns `None` for safe code and an
error message for dangerous code, plus a `RateLimiter` class that tracks
request timestamps per IP.

### 3.2 Think First: Defense in Depth

**Question:** If the Docker sandbox already blocks network access and
filesystem writes, why bother rejecting `import subprocess` in the API
layer?

<details>
<summary>Click to review</summary>

Defense in depth: any single defense can fail. A future image rebuild
might forget a flag, a kernel CVE might allow escape, or the container
runtime might misbehave. Rejecting known-bad patterns at the edge
shrinks the attack surface and produces clearer error messages
("we refused to run this" instead of a cryptic container error).

</details>

### 3.3 Implementation

Add the following helpers to `app/main.py`.

```python
import re
import time

DANGEROUS_PATTERNS = [
    r"\bos\.system\b",
    r"\bsubprocess\b",
    r"\beval\s*\(",
    r"\bexec\s*\(",
    r"\b__import__\b",
    r"\bshutil\b",
    r"\bsocket\b",
    r"\brequests\b",
    r"\burllib\b",
    r"\bopen\s*\([^)]*['\"]w['\"]",   # open(..., 'w')
]
DANGER_RE = re.compile("|".join(DANGEROUS_PATTERNS))


def validate_code(code: str) -> str | None:
    code = code.strip()
    if not code:
        return "Code is empty."
    if len(code) > MAX_CODE_LENGTH:
        return f"Code too long ({len(code)} > {MAX_CODE_LENGTH} chars)."
    if DANGER_RE.search(code):
        return "Code contains a blocked construct."
    return None


class RateLimiter:
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


limiter = RateLimiter(max_requests=30, window_seconds=60)
```

Now update the `run_code` handler to call both:

```python
def _client_ip(request) -> str:
    return request.client.host if request.client else "unknown"


@app.post("/api/run", response_model=RunResponse)
def run_code(payload: RunRequest, request: Request):
    ip = _client_ip(request)
    if not limiter.check(ip):
        raise HTTPException(status_code=___, detail=___)  # Q1, Q2

    err = validate_code(payload.code)
    if err:
        raise HTTPException(status_code=___, detail=err)  # Q3

    return RunResponse(
        id=str(uuid.uuid4()),
        stdout="(execution not implemented yet)",
        stderr="",
        exit_code=0,
        duration_ms=0,
        status="SUCCESS",
    )
```

Hints:

- Q1: 429 means "too many requests"
- Q2: a polite message like `"Rate limit exceeded. Slow down."`
- Q3: 400 (the same code used in Chapter 2)

<details>
<summary>Click to see solution</summary>

```python
if not limiter.check(ip):
    raise HTTPException(status_code=429, detail="Rate limit exceeded. Slow down.")

err = validate_code(payload.code)
if err:
    raise HTTPException(status_code=400, detail=err)
```

</details>

### 3.4 Understanding the Code

Match each pattern to the threat it blocks:

| Pattern | Threat (A-D) |
|---------|--------------|
| `\bsubprocess\b` | ___ |
| `\bopen\s*\([^)]*['\"]w['\"]` | ___ |
| `\bsocket\b` | ___ |
| `\beval\s*\(` | ___ |

**Options:**

- A: Arbitrary code execution via string parsing
- B: Writing to the host filesystem
- C: Raw network access bypassing the firewall
- D: Spawning child processes (often used for shells)

<details>
<summary>Click to review</summary>

| Pattern | Threat |
|---------|--------|
| `\bsubprocess\b` | D |
| `\bopen\s*\([^)]*['\"]w['\"]` | B |
| `\bsocket\b` | C |
| `\beval\s*\(` | A |

</details>

### 3.5 Test and Verify

Run the server and try:

```bash
curl -X POST http://localhost:8000/api/run \
  -H "Content-Type: application/json" \
  -d '{"code": "import subprocess\nprint(1)"}'
```

**Predict:** Status code and body?

<details>
<summary>Click to review</summary>

HTTP 400 with `{"detail":"Code contains a blocked construct."}`.

</details>

Try a safe program:

```bash
curl -X POST http://localhost:8000/api/run \
  -H "Content-Type: application/json" \
  -d '{"code": "print(2+2)"}'
```

**Predict:** Status code and body?

<details>
<summary>Click to review</summary>

HTTP 200 with the stub response, since the executor is not wired up
yet.

</details>

### 3.6 Checkpoint

**Self-Assessment:**

- [ ] `import subprocess` is rejected with 400
- [ ] `open("/etc/passwd", "w")` is rejected with 400
- [ ] `print("hello")` is accepted with 200
- [ ] You can explain why the regex uses `\b` word boundaries
- [ ] You can predict the 31st request's response

### 3.7 Experiment: Evading the Filter

Try these and observe which pass validation:

```python
from subprocess import run
__import__("os").system("id")
"".__class__.__mro__[1].__subclasses__()
```

**Observe:** The third example is a classic Python jail escape that
uses no banned module name.

**Question:** Why is regex-based filtering a defense, not a guarantee?
What would a stronger layer look like?

<details>
<summary>Click to review</summary>

A motivated attacker can avoid any fixed list of strings. The sandbox
itself is the real guarantee: even if `__import__("os")` runs, the
process is unprivileged, has no network, and cannot write to disk.
Stronger layers include running user code in a RestrictedPython
sandbox, an AST-level allowlist, or a different language VM entirely
(like Pyodide running in a WebAssembly sandbox).

</details>

---

## Chapter 4: The Docker Sandbox

This chapter builds the component that actually executes user code: a
hardened Python image and a `DockerService` class that creates,
starts, execs into, and removes a container for each request.

### 4.1 What You Will Build

A `docker/runner/Dockerfile` that produces a minimal, unprivileged
Python image, and a `DockerService` Python class that uses the
official Docker SDK to spin up a container, run code inside it via
`exec_run`, and tear it down.

### 4.2 Think First: Why a Separate Image?

**Question:** Why is the sandbox image built once and stored in the
local Docker cache, instead of being built fresh on every request?

<details>
<summary>Click to review</summary>

Building per request would add tens of seconds of latency and consume
disk space for every user. A pre-built, vetted image guarantees the
attack surface does not change between runs and makes startup cheap
(docker only needs to start a container, not compile layers).

</details>

### 4.3 Implementation: The Sandbox Image

Create `docker/runner/Dockerfile`:

```dockerfile
FROM python:3.12-alpine

ENV PIP_NO_CACHE_DIR=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONHASHSEED=random \
    PYTHONIOENCODING=utf-8

RUN addgroup -g 1000 -S runner && \
    adduser -u 1000 -G runner -S -h /sandbox runner

WORKDIR /sandbox
RUN chown runner:runner /sandbox

USER 1000:1000

ENTRYPOINT []
CMD ["python", "--version"]
```

Build it once:

```bash
docker build -t code-runner:latest -f docker/runner/Dockerfile docker/runner/
```

**Predict:** What will `docker images code-runner` show for SIZE?

<details>
<summary>Click to review</summary>

A typical `python:3.12-alpine` build is around 50-80 MB. The exact
size depends on the base image digest.

</details>

### 4.4 Implementation: The DockerService Class

Add the following to `app/main.py`. This is the longest block in the
lab, so blanks are introduced in stages.

Stage 1: imports and the result dataclass.

```python
import base64
import docker
from dataclasses import dataclass


@dataclass
class ExecResult:
    stdout:      str
    stderr:      str
    exit_code:   int
    duration_ms: int
    status:      str   # SUCCESS | ERROR | TIMEOUT
```

Stage 2: the bootstrap string. The user code is passed via environment
variables because the container's root filesystem is read-only.

```python
SANDBOX_BOOTSTRAP = """
import os, sys, base64, io
code     = base64.b64decode(os.environ.pop('CODE_B64', '')).decode('utf-8')
stdin_dt = base64.b64decode(os.environ.pop('STDIN_B64', '')).decode('utf-8')
sys.stdin = io.StringIO(stdin_dt)
exec(compile(code, '<user>', 'exec'))
"""
```

Stage 3: the class skeleton with one blank to fill in.

```python
class DockerService:
    def __init__(self):
        self.client = None
        try:
            self.client = docker.from_env()
            self.client.ping()
        except Exception as e:
            print("Docker not reachable:", e)

    def run(self, code: str, stdin: str = "", timeout: int = 10) -> ExecResult:
        if not self.client:
            return ExecResult("", "Docker daemon not reachable.",
                               -1, 0, "ERROR")

        container = self.client.containers.create(
            image="code-runner:latest",
            command=["sleep", "30"],
            detach=True,
            network_mode=___,    # Q1
            read_only=___,       # Q2
            user="nobody",
            mem_limit="128m",
            memswap_limit="128m",
            cpu_quota=50000,
            cpu_period=100000,
            pids_limit=64,
            security_opt=["no-new-privileges"],
            cap_drop=["ALL"],
            tmpfs={"/tmp": "size=10m,noexec"},
            environment={"PYTHONUNBUFFERED": "1"},
        )
        container.start()

        code_b64  = base64.b64encode(code.encode("utf-8")).decode("ascii")
        stdin_b64 = base64.b64encode(stdin.encode("utf-8")).decode("ascii")

        try:
            exec_res = container.exec_run(
                cmd=["python", "-c", SANDBOX_BOOTSTRAP],
                detach=False,
                user="nobody",
                environment={
                    "CODE_B64": code_b64,
                    "STDIN_B64": stdin_b64,
                    "PYTHONUNBUFFERED": "1",
                },
            )
            stdout    = exec_res.output.decode("utf-8", errors="replace") if exec_res.output else ""
            exit_code = exec_res.exit_code
            status    = "SUCCESS" if exit_code == 0 else "ERROR"
        except Exception:
            try:
                container.kill()
            except Exception:
                pass
            return ExecResult("", "Execution timed out.", 124, 0, "TIMEOUT")
        finally:
            try:
                container.remove(force=True)
            except Exception:
                pass

        return ExecResult(stdout, "", exit_code, 0, status)
```

Hints:

- Q1: a string that means "no network interfaces at all"
- Q2: a boolean that means "the root filesystem cannot be written to"

<details>
<summary>Click to see solution</summary>

- Q1: `"none"`
- Q2: `True`

</details>

### 4.5 Understanding the Code

Answer the following:

1. Why pass the user code as a base64-encoded environment variable
   instead of writing it to a file in the container?
2. Why use `exec_run` with `python -c <bootstrap>` instead of
   `containers.run(cmd=["python", "/sandbox/user.py"])`?
3. What does `cap_drop=["ALL"]` accomplish?

<details>
<summary>Click to review</summary>

1. The root filesystem is read-only, and the Docker Python SDK 7+
   removed the `stdin=` argument from `containers.run()`. Passing
   code through an environment variable requires no filesystem write
   and no stdin stream.
2. `exec_run` reuses the running container's namespaces and does
   not require a separate image build for each script. The bootstrap
   string decodes the payload and execs it in place.
3. It removes every Linux capability (CAP_NET_RAW, CAP_SYS_ADMIN,
   etc.) so the process cannot perform privileged operations even if
   it somehow gains access to a sensitive syscall.

</details>

### 4.6 Test and Verify

Replace the stub executor in the `run_code` handler:

```python
docker_svc = DockerService()


@app.post("/api/run", response_model=RunResponse)
def run_code(payload: RunRequest, request: Request):
    ip = _client_ip(request)
    if not limiter.check(ip):
        raise HTTPException(status_code=429, detail="Rate limit exceeded.")
    err = validate_code(payload.code)
    if err:
        raise HTTPException(status_code=400, detail=err)

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
    return RunResponse(id=exec_id,
                       stdout=result.stdout, stderr=result.stderr,
                       exit_code=result.exit_code,
                       duration_ms=result.duration_ms,
                       status=result.status)
```

Restart the server and run:

```bash
curl -X POST http://localhost:8000/api/run \
  -H "Content-Type: application/json" \
  -d '{"code": "print(2 + 2)"}'
```

**Predict:** What does `stdout` contain?

<details>
<summary>Click to review</summary>

`"4\n"`. The bootstrap script runs in the sandbox, prints the result,
and the host captures it.

</details>

### 4.7 Checkpoint

**Self-Assessment:**

- [ ] `print(2+2)` returns stdout `4`
- [ ] A program that takes input works when `stdin` is provided
- [ ] A program that raises `ZeroDivisionError` returns exit code 1
- [ ] You can explain why `sleep 30` is the container command

### 4.8 Experiment: Sandbox Escapes

Try each of the following from the same curl command and observe the
response. None of these should succeed.

```json
{"code": "import socket; s = socket.socket(); s.connect(('example.com', 80))"}
{"code": "open('/etc/passwd', 'r').read()"}
{"code": "while True: pass"}
```

**Observe:**

- The first one is rejected by the regex filter at 400.
- The second one is allowed by the filter (it is a read, not a write)
  but the container cannot reach the host filesystem because the root
  is read-only and `/sandbox` is the only writable mount. It may
  succeed inside the container but cannot escape.
- The third one hangs. The 10-second timeout in production would
  prevent this; in development it just blocks until you kill the
  process.

**Question:** Which of these is a defense-layer failure and which is
a defense-layer success?

<details>
<summary>Click to review</summary>

The first is a filter success (regex caught it). The second is a
sandbox success (filesystem isolation worked). The third is a
**missing** defense in this development build: the timeout logic is
not yet wired into the inner `exec_run`. In production, `container.kill()`
must be called when `exec_run` blocks. This is the topic of
Chapter 8.

</details>

---

## Chapter 5: Wiring It Together

The API and the sandbox now exist independently. This chapter wires
them into a single `docker compose up` workflow, including the API
Dockerfile and the compose file.

### 5.1 What You Will Build

An API image that bundles `app/` and `frontend/`, plus a compose file
that mounts the SQLite directory as a volume and sets sane defaults.

### 5.2 Think First: Why Two Dockerfiles?

**Question:** The project has `Dockerfile` (for the API) and
`docker/runner/Dockerfile` (for the sandbox). Why are they separate?

<details>
<summary>Click to review</summary>

The two images have different security postures and different base
operating systems. The API image is a normal Debian-slim image with
pip packages and the frontend assets. The sandbox image is an Alpine
image with no pip packages, no shell, and a non-root user. Building
them together would bloat the sandbox and weaken the API.

</details>

### 5.3 Implementation: API Dockerfile

Create `Dockerfile` at the project root:

```dockerfile
FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ ./app/
COPY frontend/ ./frontend/

RUN useradd -m appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### 5.4 Implementation: Compose File

Create `docker-compose.yml`:

```yaml
services:
  api:
    build: .
    container_name: code-runner-api
    ports:
      - "8000:8000"
    environment:
      DOCKER_HOST: "tcp://host.docker.internal:2375"
      DOCKER_IMAGE: "code-runner:latest"
      DOCKER_TIMEOUT: "10"
      DOCKER_MEMORY: "128m"
    volumes:
      - ./data:/app/data
      - ./docker/runner:/runner-src:ro
    extra_hosts:
      - "host.docker.internal:host-gateway"
    restart: unless-stopped
```

> Note for Windows and macOS: the Docker daemon lives on the host.
> `host.docker.internal` resolves to the host gateway so the API
> container can reach it via TCP instead of the Unix socket.

### 5.5 Implementation: Environment Defaults

Create `.env.example` (copy to `.env` to use):

```
DOCKER_IMAGE=code-runner:latest
DOCKER_TIMEOUT=10
DOCKER_MEMORY=128m
DOCKER_CPU_QUOTA=0.5
MAX_CODE_LENGTH=10000
RATE_LIMIT_PER_MIN=30
DB_PATH=data/history.db
```

### 5.6 Test and Verify

```bash
docker compose up --build
```

In another terminal:

```bash
curl http://localhost:8000/api/health
```

**Predict:** What does `docker_available` return now?

<details>
<summary>Click to review</summary>

`true`, because the API container can reach the host Docker daemon
over `host.docker.internal`.

</details>

### 5.7 Checkpoint

**Self-Assessment:**

- [ ] `docker compose up` builds both images
- [ ] `curl /api/health` returns `docker_available: true`
- [ ] You can explain why `host.docker.internal` is needed
- [ ] You can explain the difference between `Dockerfile` and
      `docker/runner/Dockerfile`

---

## Chapter 6: The Frontend

A CLI is fine for development, but the brief is a web app. This
chapter adds a single-page HTML editor and mounts it as static files
from FastAPI.

### 6.1 What You Will Build

A single `frontend/index.html` file that loads CodeMirror from a CDN,
has a Run button, displays stdout, and shows recent history.

### 6.2 Think First: Single-File Frontend

**Question:** Why is the entire UI in a single HTML file with inline
CSS and JavaScript, instead of using a framework like React or Vue?

<details>
<summary>Click to review</summary>

The lab's goal is clarity. A framework introduces a build step, a
node_modules directory, and abstract concepts. Inline code is the
shortest path from "click Run" to "see output." The trade-off is
scalability: this approach does not survive a 20-component team.

</details>

### 6.3 Implementation

Create `frontend/index.html`:

```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <title>Python Code Runner</title>
  <link rel="stylesheet"
        href="https://cdnjs.cloudflare.com/ajax/libs/codemirror/5.65.16/codemirror.min.css" />
  <link rel="stylesheet"
        href="https://cdnjs.cloudflare.com/ajax/libs/codemirror/5.65.16/theme/dracula.min.css" />
  <style> /* layout, colors, button styles */ </style>
</head>
<body>
  <h1>Python Code Runner</h1>
  <textarea id="code">print("hello")</textarea>
  <input id="stdin" placeholder="stdin (optional)" />
  <button id="runBtn">Run</button>
  <pre id="output"></pre>
  <h2>Recent runs</h2>
  <ul id="history"></ul>
  <script src="https://cdnjs.cloudflare.com/ajax/libs/codemirror/5.65.16/codemirror.min.js"></script>
  <script src="https://cdnjs.cloudflare.com/ajax/libs/codemirror/5.65.16/mode/python/python.min.js"></script>
  <script>
    const editor = CodeMirror.fromTextArea(document.getElementById('code'), {
      mode: 'python', lineNumbers: true, theme: 'dracula',
    });
    // ... wire Run button to fetch('/api/run', ...) and render output ...
    // ... call fetch('/api/history?limit=10') to populate the list ...
  </script>
</body>
</html>
```

The blanks to fill in are inside `<script>`:

```javascript
async function run() {
  const code  = editor.getValue();
  const stdin = document.getElementById('stdin').value;
  const res   = await fetch('/api/run', {
    method: 'POST',
    headers: { 'Content-Type': '___' },   // Q1
    body: JSON.stringify({ code, stdin }),
  });
  const data = await res.json();
  document.getElementById('output').textContent =
    data.detail ?? `stdout:\n${data.stdout}\n\nexit: ${data.exit_code}  (${data.duration_ms} ms)`;
}

async function loadHistory() {
  const res  = await fetch('___');   // Q2
  const rows = await res.json();
  const ul   = document.getElementById('history');
  ul.innerHTML = '';
  for (const r of rows) {
    const li = document.createElement('li');
    li.textContent = `${r.status}  ${r.code.slice(0, 40)}`;
    ul.appendChild(li);
  }
}

document.getElementById('runBtn').addEventListener('click', run);
loadHistory();
```

Hints:

- Q1: the MIME type for JSON
- Q2: the endpoint that returns the last 20 executions

<details>
<summary>Click to see solution</summary>

- Q1: `'application/json'`
- Q2: `'/api/history?limit=20'`

</details>

### 6.4 Mounting the Frontend

Add the static-files mount at the **bottom** of `app/main.py` (it must
be the last route, because it catches every path).

```python
from pathlib import Path
from fastapi.staticfiles import StaticFiles

STATIC_DIR_CANDIDATES = [
    Path(__file__).resolve().parent.parent / "frontend",
    Path(__file__).resolve().parent / "frontend",
]

STATIC_DIR = next((p for p in STATIC_DIR_CANDIDATES if p.exists()), None)
if STATIC_DIR is not None:
    app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True),
              name="frontend")
```

### 6.5 Test and Verify

Open `http://localhost:8000` in a browser. You should see the code
editor, a Run button, an output area, and a history list.

Type:

```python
for i in range(3):
    print(f"step {i}")
```

Click Run.

**Predict:** What appears in the output area?

<details>
<summary>Click to review</summary>

```
stdout:
step 0
step 1
step 2

exit: 0  (~500 ms)
```

</details>

### 6.6 Checkpoint

**Self-Assessment:**

- [ ] The UI loads at `/` (not 404)
- [ ] Clicking Run sends a request to `/api/run`
- [ ] The output area shows stdout and exit code
- [ ] The history list shows previous runs

### 6.7 Experiment: Hard Refresh

After editing `index.html`, the browser may show a cached copy.

**Observe:** Ctrl+Shift+R (Windows/Linux) or Cmd+Shift+R (macOS)
forces a fresh fetch. The DevTools Network tab also has a "Disable
cache" checkbox while the panel is open.

---

## Chapter 7: Persistence and Observability

Every run is useful only if it can be retrieved later. This chapter
adds SQLite-backed history and a small `/api/history` endpoint.

### 7.1 What You Will Build

A `data/history.db` SQLite file with a single `executions` table and
two endpoints: a list view and a single-item view.

### 7.2 Think First: Why SQLite?

**Question:** Why use SQLite for an audit log instead of PostgreSQL or
a flat file?

<details>
<summary>Click to review</summary>

The audit log is local, append-mostly, and read by the same process
that writes it. PostgreSQL would add an external dependency and a
container. A flat file would lose query features (filtering, ordering,
limits). SQLite sits exactly in the middle: zero-config, transactional,
queryable, and durable.

</details>

### 7.3 Implementation

Add to `app/main.py`:

```python
import sqlite3
from datetime import datetime

DB_PATH = "data/history.db"
Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)


def init_db() -> None:
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS executions (
                id          TEXT PRIMARY KEY,
                code        TEXT NOT NULL,
                stdout      TEXT,
                stderr      TEXT,
                exit_code   INTEGER,
                duration_ms INTEGER,
                status      TEXT,
                created_at  TEXT
            )
        """)
        conn.commit()


@app.on_event("startup")
def _startup() -> None:
    init_db()
```

Now add the two history endpoints:

```python
@app.get("/api/history")
def list_history(limit: int = 20):
    limit = max(1, min(limit, 100))            # Q1
    with sqlite3.connect(DB_PATH) as conn:
        rows = conn.execute(
            "SELECT * FROM executions ORDER BY created_at DESC LIMIT ___",  # Q2
            (limit,),
        ).fetchall()
    return [dict(r) for r in rows]
```

Hints:

- Q1: the bounds prevent a client from asking for one billion rows
- Q2: the variable name from the line above

<details>
<summary>Click to see solution</summary>

- Q1: `max(1, min(limit, 100))`
- Q2: `?`

</details>

### 7.4 Test and Verify

Run two programs, then list history:

```bash
curl -X POST http://localhost:8000/api/run \
  -H "Content-Type: application/json" -d '{"code": "print(1)"}'
curl -X POST http://localhost:8000/api/run \
  -H "Content-Type: application/json" -d '{"code": "print(2)"}'
curl http://localhost:8000/api/history?limit=2
```

**Predict:** In what order do the two records appear?

<details>
<summary>Click to review</summary>

Newest first, because the query uses `ORDER BY created_at DESC`.

</details>

### 7.5 Checkpoint

**Self-Assessment:**

- [ ] `init_db` runs at startup
- [ ] The `executions` table exists after the first request
- [ ] `GET /api/history?limit=2` returns at most 2 rows
- [ ] Records persist across container restarts (because `data/` is a
      volume)

---

## Chapter 8: Hardening Experiments

Defenses are only useful if they actually stop attacks. This chapter
runs four deliberate experiments to verify that the sandbox and the
filter do what they claim.

### Experiment 1: Filesystem Read

**Goal:** Show that a read-only root filesystem blocks writes.

Run:

```python
open("/tmp/owned", "w").write("pwned")
```

**Predict:** Does the request succeed? What does the API return?

<details>
<summary>Click to review</summary>

The regex filter rejects this with 400 because the pattern matches
`open(..., 'w')`. Even if the filter is bypassed, the read-only root
and the `tmpfs` on `/tmp` would still allow this specific write, so
this is a filter-success, not a sandbox-success.

</details>

### Experiment 2: Network Egress

**Goal:** Show that `network_mode="none"` blocks outbound traffic.

Bypass the filter by using a less-obvious module:

```python
import urllib.request
urllib.request.urlopen("http://example.com").read()
```

**Predict:** The regex filter will catch this. Remove the filter
temporarily (comment out the `validate_code` call) and try again.

**Observe:** A long hang followed by a connection error. The
container has no network interfaces, so the request cannot resolve or
connect.

### Experiment 3: Fork Bomb

**Goal:** Show that `pids_limit=64` stops a fork bomb.

Bypass the filter and run:

```python
import os
while True:
    os.fork()
```

**Observe:** The container eventually refuses to create new
processes, and the process limit is hit. The host remains
unaffected.

### Experiment 4: Memory Bomb

**Goal:** Show that `mem_limit` kills processes that exceed 128 MB.

Bypass the filter and run:

```python
x = " " * (200 * 1024 * 1024)  # 200 MB string
```

**Observe:** The process is killed with `MemoryError` or an
out-of-memory signal. The host memory is untouched.

### Self-Assessment After Experiments

- [ ] You can list at least three independent layers of defense
- [ ] You can explain why each layer matters even when the others are
      intact
- [ ] You can describe what would happen if any single layer were
      removed

---

## Epilogue: The Complete System

Your single application now provides:

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/health` | Liveness + Docker reachability |
| POST | `/api/run` | Execute user code in a sandbox |
| GET | `/api/history` | List recent executions |
| GET | `/api/history/{id}` | Fetch a single execution |
| GET | `/` | Single-page web editor |

Verify the full system end-to-end:

```bash
# 1. Health
curl http://localhost:8000/api/health

# 2. Safe code
curl -X POST http://localhost:8000/api/run \
  -H "Content-Type: application/json" \
  -d '{"code":"print(2+2)"}'

# 3. Banned module
curl -X POST http://localhost:8000/api/run \
  -H "Content-Type: application/json" \
  -d '{"code":"import subprocess"}'

# 4. Stdin pass-through
curl -X POST http://localhost:8000/api/run \
  -H "Content-Type: application/json" \
  -d '{"code":"name = input()\nprint(\"hi,\" + name)","stdin":"Shihab"}'

# 5. Runtime error captured
curl -X POST http://localhost:8000/api/run \
  -H "Content-Type: application/json" \
  -d '{"code":"print(1/0)"}'

# 6. History
curl http://localhost:8000/api/history?limit=3
```

Expected status codes and key fields:

| Step | Status | Key field |
|------|--------|-----------|
| 1 | 200 | `docker_available: true` |
| 2 | 200 | `stdout: "4\n"` |
| 3 | 400 | `detail: "Code contains a blocked construct..."` |
| 4 | 200 | `stdout: "hi,Shihab\n"` |
| 5 | 200 | `exit_code: 1`, `status: "ERROR"` |
| 6 | 200 | Array of recent executions |

The interactive API explorer is at `http://localhost:8000/docs`.

---

## The Principles

1. **Treat all input as hostile.** The user owns the code, not the
   platform. Every defense has to assume the layer above it has
   failed.
2. **Defense in depth beats single-layer security.** A regex filter
   plus a sandbox plus capability drops plus resource limits is much
   stronger than any one of those alone.
3. **Fail closed, not open.** If a defense cannot be applied (Docker
   down, image missing), refuse the request rather than running it
   unsandboxed.
4. **Validate at the boundary, then trust internal code.** Pydantic
   stops malformed requests at the door; the rest of the system can
   assume well-typed data.
5. **Use the platform.** Docker namespaces, cgroups, capabilities,
   and seccomp exist for exactly this problem. Reuse them instead of
   reinventing isolation in Python.
6. **Prefer simple, explicit code for security-critical paths.** A
   200-line single-file app is easier to audit than a 2000-line
   microservice mesh.
7. **Make abuse expensive and observable.** Rate limits, structured
   logs, and persistent history turn attacks from silent failures
   into data you can act on.

---

## Troubleshooting

### Error: Docker daemon not reachable

**Cause:** The Docker Desktop service is not running, or the API
container cannot see the host daemon.

**Solution:**

```bash
# 1. Start Docker Desktop (Windows / macOS) or
sudo systemctl start docker   # Linux

# 2. Confirm the host can reach the daemon
docker ps

# 3. If running inside a container, set DOCKER_HOST
export DOCKER_HOST=tcp://host.docker.internal:2375
```

### Error: Address already in use (port 8000)

**Cause:** Another process is bound to port 8000.

**Solution:**

```bash
# macOS / Linux
lsof -ti:8000 | xargs kill -9

# Windows PowerShell
Get-NetTCPConnection -LocalPort 8000 |
  Select-Object -ExpandProperty OwningProcess -Unique |
  ForEach-Object { Stop-Process -Id $_ -Force }
```

### Error: ModuleNotFoundError: No module named 'fastapi'

**Cause:** The virtual environment is not activated, or dependencies
were not installed.

**Solution:**

```bash
source .venv/bin/activate
pip install -r requirements.txt
```

### Error: 422 Unprocessable Entity on /api/run

**Cause:** The request body is not valid JSON, or a field has the
wrong type.

**Solution:** Send a JSON object with string fields:

```bash
curl -X POST http://localhost:8000/api/run \
  -H "Content-Type: application/json" \
  -d '{"code":"print(1)"}'
```

### Error: container rootfs is marked read-only

**Cause:** The user code was being copied into the container with
`put_archive`, which fails on a read-only root. The fix is to pass
code via the `CODE_B64` environment variable instead.

**Solution:** Confirm `app/main.py` uses
`container.exec_run(cmd=["python", "-c", SANDBOX_BOOTSTRAP],
environment={...})` rather than `put_archive`.

### Error: run() got an unexpected keyword argument 'stdin'

**Cause:** The Docker Python SDK 7+ removed `stdin=` from
`containers.run()`. The lab uses the lower-level `create + start +
exec_run` flow to avoid this.

**Solution:** Update `DockerService.run` to use `containers.create` and
`exec_run` exactly as shown in Chapter 4.

### Error: Failed to fetch on the web UI

**Cause:** The browser is loading a cached version of the page, or
the API is on a different port.

**Solution:** Hard-refresh the page (Ctrl+Shift+R). Confirm the API
responds on `http://localhost:8000/api/health`.

---

## Next Steps

Suggested extensions for students who complete the lab:

1. **Add a `GET /api/history/{id}` endpoint** that returns a single
   execution record by id. Hint: use `SELECT * FROM executions WHERE
   id = ?` and return 404 if the row is missing.
2. **Add streaming output** using Server-Sent Events so a long-running
   program emits output line by line.
3. **Replace the regex filter with an AST allowlist.** Use the `ast`
   module to walk the syntax tree and reject any `Import`,
   `Call(func=Name('eval'|'exec'|'open'))`, or `Subscript` node.
4. **Persist Docker image builds.** Tag the sandbox image with a git
   commit hash and rebuild only on changes.
5. **Add multi-language support.** Build a second sandbox image for
   JavaScript using Node Alpine, and select the image based on a
   `language` field in the request.
6. **Wire OpenTelemetry.** Emit a span for each container lifecycle
   phase (create, start, exec, remove) and a counter for rate-limited
   requests.

---

## Additional Resources

- FastAPI documentation: <https://fastapi.tiangolo.com/>
- Pydantic v2 documentation: <https://docs.pydantic.dev/latest/>
- Docker Engine API reference: <https://docs.docker.com/engine/api/>
- Docker SDK for Python: <https://docker-py.readthedocs.io/>
- Linux capabilities manual: `man 7 capabilities`
- cgroups v2 manual: <https://www.kernel.org/doc/Documentation/admin-guide/cgroup-v2.rst>
- SQLite documentation: <https://www.sqlite.org/docs.html>
- OWASP Top 10: <https://owasp.org/www-project-top-ten/>
