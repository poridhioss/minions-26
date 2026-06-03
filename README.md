# Legal Document Classifier - End-to-End Lab

> A reproducible, step-by-step laboratory document for building, training,
> serving, and monitoring a Legal-BERT text classifier. This is a single
> lab with six numbered **steps**; each step has a stated **goal**, the
> **commands** you must run, an explanation of **what is happening under
> the hood**, a **verification** step, and a **troubleshooting** block
> for the common failure modes. Work through Steps 1 to 6 in order.

This document is written so a viewer who has never seen the project can
complete it end-to-end on a fresh Windows + Docker machine in roughly one
hour, *and* understand the role of every file along the way.

---

## What you will build

Given a paragraph of legal text, the API returns the most likely SCOTUS
topic area along with a confidence score. The same `predict()` function
powers both the FastAPI endpoint and any client that can `POST` JSON, so
the model can be plugged into a web app, a notebook, or a CI smoke test
without changes. Steps 1 to 6 walk you through doing all of that on your
own machine.

---
## User Interface

<img width="1841" height="837" alt="image" src="https://github.com/user-attachments/assets/7fe6ac28-bb26-4ca1-96c7-a7b5f2d05575" />



## Step 1 - Orient yourself and form the mental model

**Goal.** Form a single mental picture of every component in the stack
*before* writing a single command, so that every later step has a place
to land.

### 1.1 What we are building

We are going to take a paragraph of legal text and automatically label it
with one of four U.S. Supreme Court topic areas:

| Label ID | Topic area           |
|----------|----------------------|
| 0        | Criminal Procedure   |
| 1        | Civil Rights         |
| 2        | First Amendment      |
| 3        | Economic Activity    |

We use a transformer called **Legal-BERT** (`nlpaueb/legal-bert-base-uncased`)
that has already been pre-trained on large legal corpora, and we *fine-tune*
it on the SCOTUS split of the [LexGLUE](https://huggingface.co/datasets/coastalcph/lex_glue)
benchmark. Fine-tuning is short (3 epochs) because the heavy lifting was
already done in pre-training.

### 1.2 The five components

```
   +--------------+      +--------------+      +--------------+
   |  1. Training | ---> | 2. Saved     | ---> |  3. FastAPI  |
   |  (Colab GPU) |      |   model      |      |   service    |
   +--------------+      +--------------+      +------+-------+
                                                       | /predict
                                                       v
                                              +----------------+
                                              |  4. Prometheus |
                                              |   (scrapes     |
                                              |    /metrics)   |
                                              +------+---------+
                                                     | PromQL
                                                     v
                                              +----------------+
                                              |  5. Grafana    |
                                              |   (dashboards) |
                                              +----------------+
```

1. **Training** runs once, on a GPU we don't own (Google Colab). It
   produces a folder of weights + tokenizer files.
2. **Saved model** is a plain directory we copy into the project. ~400 MB.
3. **FastAPI service** loads the model once at startup and exposes
   `POST /predict` plus `GET /metrics`.
4. **Prometheus** polls the service every 15 s and stores time-series data.
5. **Grafana** queries Prometheus and renders the dashboard.

A sixth component, **MLflow**, is the experiment tracker that records the
hyperparameters and metrics from the training run so you can compare
different fine-tuning experiments later.

### 1.3 Where files live

```
legal-doc-classifier/
+-- saved_model/                  <- created in Step 3, copied into project in Step 4
+-- app/
|   +-- __init__.py               <- makes `app` an importable package
|   +-- main.py                   <- FastAPI app: /predict, /health, /metrics
|   +-- model_loader.py           <- loads Legal-BERT once, exposes predict()
+-- train/
|   +-- train.py                  <- Colab training script (Step 3)
+-- grafana/
|   +-- dashboards/dashboard.json <- pre-built monitoring dashboard
|   +-- provisioning/
|       +-- datasources/prometheus.yml  <- auto-registers Prometheus
|       +-- dashboards/dashboards.yml   <- tells Grafana where dashboards live
+-- scripts/                      <- PowerShell helpers for ops tasks
+-- prometheus.yml                <- scrape config (15 s, target api:8000)
+-- index.html                    <- static frontend (Step 6)
+-- Dockerfile                    <- builds the API image
+-- docker-compose.yml            <- orchestrates api + mlflow + prometheus + grafana
+-- requirements.txt              <- Python dependencies
+-- README.md                     <- this file
```

> WARNING: `saved_model/` is **not** in git - it weighs ~400 MB. Step 3 produces
> it, Step 4 consumes it.

### 1.4 What "end-to-end" means here

End-to-end in this project means: a user types legal text into a web
page (or hits an API), the text is sent to a containerised model, the
model returns a label, the call is recorded as a metric, Prometheus
collects the metric, and Grafana visualises it - all without you writing
extra glue code.

---

## Step 2 - Set up the working environment

**Goal.** Get a clean baseline: Docker running, project cloned, helper
tools available, no surprises in the next steps.

### 2.1 Prerequisites

| Tool | Version | Why |
|------|---------|-----|
| [Docker Desktop](https://www.docker.com/products/docker-desktop/) | 4.x or newer | Runs API, MLflow, Prometheus, Grafana in containers |
| PowerShell | 5.1+ (ships with Windows) | All `Invoke-RestMethod` examples in this guide |
| ~5 GB free disk | - | Saved model + Docker images |
| A Google account | - | Step 3 needs Colab GPU |

> If you are on macOS or Linux, the PowerShell snippets still work inside
> PowerShell 7, and all `docker compose` commands are identical.

### 2.2 Steps

```powershell
# 1. Start Docker Desktop
#    Either double-click the desktop icon, or:
Start-Process "C:\Program Files\Docker\Docker\Docker Desktop.exe"

# 2. Wait for the daemon, then confirm:
docker version
docker info | Select-String "Server Version"
```

You should see both a **Client** and a **Server** section with a
non-empty version string. If you see *"Cannot connect to the Docker
daemon"*, Docker Desktop is still starting - wait 30 seconds and retry.

### 2.3 Clone or download the project

```powershell
cd E:\Projects
git clone <your-repo-url> legal-doc-classifier
cd legal-doc-classifier
```

If you already have the project on disk, just `cd` into it.

### 2.4 Verify the tree

```powershell
Get-ChildItem -Force | Select-Object Name, Mode
```

You should see the folders listed in Step 1 section 1.3. The `saved_model/`
folder will be empty for now - that is correct.

### 2.5 What is happening

- **Docker Desktop** is a Hyper-V/VirtIO-based Linux VM that runs the
  Docker daemon. Every `docker compose` command in later steps creates
  containers *inside that VM*, not on your Windows host.
- The **project tree** is the source of truth. Compose reads
  `docker-compose.yml` from this root, and the model loader reads
  `saved_model/` from the same root (mounted at `/app/saved_model`
  inside the API container).

### 2.6 Verify

```powershell
docker run --rm hello-world
```

You should see *"Hello from Docker!"* This proves the daemon, the
network, and the default registry all work.

### 2.7 Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| `open //./pipe/dockerDesktopLinuxEngine: ...` | Docker Desktop not running | Start it from the Start menu, wait 30 s, retry |
| `docker: command not found` | Docker not in `PATH` | Reinstall Docker Desktop or add `C:\Program Files\Docker\Docker\resources\bin` to `PATH` |
| WSL2 kernel missing | WSL not installed | `wsl --install` from an elevated PowerShell, then reboot |

---

## Step 3 - Train the model in Google Colab

**Goal.** Produce the `saved_model/` directory containing a fine-tuned
Legal-BERT and matching tokenizer. We do this in Colab because the free
T4 GPU finishes in ~10-20 minutes, vs. several hours on a laptop CPU.

### 3.1 Why Colab

| Option | Cost | Time | Verdict |
|--------|------|------|---------|
| Local CPU | Free | 4-8 hours | Not practical |
| Local GPU (RTX 30/40) | You own it | ~20 min | Good but not assumed |
| **Google Colab free T4** | Free | ~15 min | **Default for this lab** |
| Colab Pro / AWS | $$ | ~5 min | Out of scope |

### 3.2 Steps

1. Open https://colab.research.google.com and create a new notebook.
2. Set the runtime: **Runtime -> Change runtime type -> T4 GPU -> Save**.
3. In the first cell, install dependencies:
   ```python
   !pip install -q transformers torch datasets mlflow scikit-learn
   ```
4. In a second cell, download the training script and run it:
   ```python
   !wget -q https://raw.githubusercontent.com/<owner>/legal-doc-classifier/main/train/train.py
   %run train.py
   ```
   Or, if you prefer to paste the script, open `train/train.py` from
   this repo, copy its contents into a new cell, and run that cell.
5. The script will:
   - Load the LexGLUE SCOTUS split (~3 k train, ~700 test).
   - Filter out everything except labels `0, 1, 2, 8` and remap them to
     `0, 1, 2, 3` (the four target topic areas).
   - Tokenize with `nlpaueb/legal-bert-base-uncased`, `max_length=512`.
   - Fine-tune for **3 epochs, batch size 8, learning rate 2e-5**.
   - Log hyperparameters and per-epoch metrics to MLflow.
   - Save the model + tokenizer to `./saved_model/`.

### 3.3 Download the saved model

```python
!zip -r saved_model.zip saved_model
from google.colab import files
files.download("saved_model.zip")
```

Unzip the downloaded file **into the root of this project** so the
folder structure becomes:

```
legal-doc-classifier/
+-- saved_model/
    +-- config.json
    +-- tokenizer.json
    +-- tokenizer_config.json
    +-- vocab.txt
    +-- pytorch_model.bin     (or model.safetensors)
    +-- ... (other HuggingFace files)
```

> NOTE: HuggingFace splits checkpoints across several files by default;
> that's fine - the loader just needs the whole directory.

### 3.4 What is happening

- **LexGLUE SCOTUS** is a benchmark of U.S. Supreme Court opinions, each
  labelled with one of 14 issue areas. We discard 10 of them because we
  only want four coarse classes.
- **Fine-tuning** adjusts the final classification head (and gently the
  encoder) to fit those four classes. The encoder's prior knowledge of
  legal English is what makes 3 epochs enough.
- **MLflow logging** happens through a local SQLite or in-memory
  tracking URI. When you stand up the `mlflow` service in Step 4, the
  same runs will appear in the UI at `http://localhost:5000`.

### 3.5 Verify

Inside Colab, after training:

```python
from transformers import AutoTokenizer, AutoModelForSequenceClassification
m = AutoModelForSequenceClassification.from_pretrained("./saved_model")
t = AutoTokenizer.from_pretrained("./saved_model")
print(m.config.num_labels)   # should print 4
```

If that prints `4` and the API is happy in Step 4, the model is healthy.

### 3.6 Troubleshooting

| Symptom | Fix |
|---------|-----|
| `CUDA out of memory` | Lower per-device batch size in the training script (e.g. 4) |
| `datasets` download hangs | Re-run; LexGLUE is ~50 MB |
| `Runtime disconnected` | Colab idle timeout - keep the tab focused or use Colab Pro |

---

## Step 4 - Serve the model with FastAPI and Docker

**Goal.** Run the saved model behind a REST API on `http://localhost:8000`
so any client (curl, PowerShell, a web page) can classify text.

### 4.1 What we are building

A single container (`api`) that:

- Loads the model **once** at startup (not per request) via FastAPI's
  `lifespan` context.
- Exposes `POST /predict` -> `{ label, confidence }`.
- Exposes `GET /health` -> `{ "status": "ok" }`.
- Exposes `GET /metrics` -> Prometheus text format (Step 5).

A second container (`mlflow`) hosts the experiment-tracking UI.

### 4.2 Steps

```powershell
# Make sure Docker Desktop is running
docker version | Select-String "Server Version"

# Confirm the saved model is in place
Get-ChildItem .\saved_model
```

You should see `config.json`, `pytorch_model.bin` (or `model.safetensors`),
`tokenizer.json`, `vocab.txt`, etc.

```powershell
# Build and start the stack (api + mlflow for now)
docker compose up -d --build
```

The first build takes a few minutes because it pulls `python:3.10`,
installs `torch` (large), and copies the model. Subsequent builds are
fast thanks to layer caching.

```powershell
# Confirm the API container is healthy
docker compose ps
```

You should see `api` and `mlflow` in state `Up` / `running`.

### 4.3 Send your first prediction

In a new PowerShell window:

```powershell
Invoke-RestMethod -Method Post -Uri "http://localhost:8000/predict" `
  -ContentType "application/json" `
  -Body '{"text":"The defendant was charged with assault and battery."}'
```

Expected output:

```
label              confidence
-----              ----------
Criminal Procedure     0.8421
```

You can also visit the auto-generated API docs at
**http://localhost:8000/docs** and try the endpoint from a browser
with a "Try it out" button.

### 4.4 What is happening

- `Dockerfile` extends `python:3.10-slim`, installs `requirements.txt`,
  copies `app/` and `saved_model/`, and runs `uvicorn app.main:app`.
- `app/main.py` uses `lifespan` to load the model **once**. Loading a
  transformer takes a few seconds; doing it per request would multiply
  latency by 100x.
- `app/model_loader.py` is a thin wrapper around
  `transformers.AutoModelForSequenceClassification` that returns
  `(label_name, confidence)`. Keeping it in its own module means we
  can unit-test it without importing FastAPI.
- `docker-compose.yml` mounts `MODEL_DIR=/app/saved_model` so the loader
  knows where to look inside the container.

### 4.5 Verify

```powershell
# Health check
(Invoke-WebRequest http://localhost:8000/health).Content
# -> {"status":"ok"}

# Tail the logs
docker compose logs -f api
```

You should see a single `Uvicorn running on http://0.0.0.0:8000` line
and no error tracebacks.

### 4.6 Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| `OSError: saved_model not found` | `saved_model/` is empty or at the wrong path | Re-run Step 3, unzip into project root |
| Container restarts in a loop | Model load crashed | `docker compose logs api` - look for the stack trace |
| `port 8000 already in use` | Another process on 8000 | Edit `docker-compose.yml` to map `8001:8000` |
| `curl` works but `Invoke-RestMethod` fails | Wrong content type | Always pass `-ContentType "application/json"` |

---

## Step 5 - Observe the service with Prometheus + Grafana

**Goal.** Add a metrics pipeline so we can see, in real time, how often
the API is called, how slow it is, what labels it predicts, and how
many errors it throws.

### 5.1 What we are adding

| Service | Port | Role |
|---------|------|------|
| Prometheus | 9090 | Polls `api:8000/metrics` every 15 s, stores time-series |
| Grafana    | 3000 | Queries Prometheus, renders the dashboard |

Both are added to `docker-compose.yml` as two more services, but the
existing `api` does not need to change - it already exposes `/metrics`
through the `prometheus_client` library.

### 5.2 Metrics being collected

| Metric | Type | What it tells you |
|--------|------|-------------------|
| `legal_classifier_prediction_latency_seconds` | Histogram | Per-request inference time |
| `legal_classifier_prediction_confidence` | Gauge | Confidence of the most recent prediction |
| `legal_classifier_prediction_label_total{label="..."}` | Counter | Lifetime count per predicted class |
| `legal_classifier_request_total` | Counter | Total `/predict` calls |
| `legal_classifier_error_total` | Counter | Total failed calls |

### 5.3 Steps

```powershell
# Bring up the full stack (4 services)
docker compose up -d --build

# Confirm all four are running
docker compose ps
```

You should see `api`, `mlflow`, `prometheus`, `grafana` all in `Up`.

```powershell
# 1. Verify Prometheus can reach the API
Invoke-RestMethod http://localhost:9090/api/v1/targets |
  Select-Object -ExpandProperty data |
  ForEach-Object { "$($_.labels.job): $($_.health)" }
# -> legal-classifier-api: up
# -> prometheus: up
```

```powershell
# 2. Generate traffic so the dashboard has something to show
1..20 | ForEach-Object {
  Invoke-RestMethod -Method Post -Uri "http://localhost:8000/predict" `
    -ContentType "application/json" `
    -Body '{"text":"The defendant was charged with assault and battery."}'
}
```

```powershell
# 3. Open the Grafana dashboard
Start-Process http://localhost:3000
```

Log in with `admin` / `admin` (the env vars in `docker-compose.yml`
disable the password-reset prompt and allow anonymous access for local
development). The dashboard titled **"Legal Document Classifier -
Monitoring"** is auto-loaded in the **Legal Classifier** folder.

You should see:

- **Total Requests** ticking up
- **Request Rate per minute** showing non-zero
- **Label Prediction Counts** filling in
- **Average Prediction Latency** holding steady around 100-400 ms

### 5.4 What is happening

- `prometheus.yml` declares one scrape job,
  `legal-classifier-api`, that points at `api:8000/metrics` every
  15 seconds. `api` resolves via Docker's internal DNS to the API
  container's IP.
- `prometheus_client` in `app/main.py` registers five collectors and
  exposes them in Prometheus text format on `GET /metrics`. The
  `try/except/finally` block in `predict()` records latency on
  *both* success and failure paths.
- `grafana/provisioning/datasources/prometheus.yml` registers
  Prometheus as the default Grafana data source, and
  `grafana/provisioning/dashboards/dashboards.yml` points Grafana at
  `/var/lib/grafana/dashboards`, which is bind-mounted to
  `./grafana/dashboards/` on the host.
- The dashboard JSON references the datasource by **name** (`Prometheus`),
  not by UID, so Grafana's auto-generated UIDs don't break panel binding.

### 5.5 Verify

```powershell
# Raw metrics
(Invoke-WebRequest http://localhost:8000/metrics).Content -split "`n" |
  Where-Object { $_ -match "^legal_classifier_" } |
  Select-Object -First 10
```

You should see lines like:

```
# HELP legal_classifier_request_total Total number of /predict requests.
# TYPE legal_classifier_request_total counter
legal_classifier_request_total 20.0
```

```powershell
# PromQL directly through Prometheus
(Invoke-WebRequest "http://localhost:9090/api/v1/query?query=rate(legal_classifier_request_total[1m])").Content
```

### 5.6 Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| Prometheus target `down` | `api:8000` not reachable | `docker compose logs api` - is the model loaded? |
| Grafana panel "No data" | Datasource binding broken | Re-upload the dashboard (see `scripts/reload_dashboard.ps1`) |
| `/metrics` returns HTML 404 | uvicorn not running the new code | `docker compose up -d --build api` |
| Grafana asks to change the password | `GF_SECURITY_DISABLE_INITIAL_ADMIN_PASSWORD_RESET` missing | Already set in `docker-compose.yml`; recreate the container with `docker compose up -d --force-recreate grafana` |

---

## Step 6 - Use the web frontend

**Goal.** Give non-technical viewers a friendly way to classify text
without touching `curl` or PowerShell.

### 6.1 What we are adding

A single static file, `index.html`, that:

- Has a text area and a **Classify** button.
- POSTs to `http://localhost:8000/predict`.
- Renders the predicted label as a coloured badge and shows the
  confidence score with two decimals.
- Shows a spinner during inference and an error message if the API
  is unreachable.

### 6.2 Steps

Option A - **open the file directly:**

```powershell
Start-Process .\index.html
```

Option B - **publish to GitHub Pages:**

1. Push `index.html` to the repo's `main` branch.
2. In GitHub -> **Settings -> Pages**, set the source to `main / root`.
3. After ~30 s, your page is live at
   `https://<owner>.github.io/legal-doc-classifier/`.

### 6.3 What is happening

- The page is **plain HTML + CSS + vanilla JavaScript** - no build
  step, no framework, no bundler. You can read the entire file in
  one screen.
- It calls `http://localhost:8000/predict` directly, so the browser
  must be on a machine that can reach the API. From GitHub Pages
  this means the visitor's own machine must be running the Docker
  stack, or the API must be exposed behind a CORS-enabled public URL.
- The four label colours (red, blue, green, amber) are defined in
  a small `:root` CSS block at the top of the file and are easy to
  retheme.

### 6.4 Verify

1. Type a paragraph of legal text into the box.
2. Click **Classify**.
3. Within ~1 second you should see a coloured badge with the topic
   area and a confidence percentage.

### 6.5 Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| "Could not connect to API" | Docker stack not running | Run Step 4 to start it |
| CORS error in browser console | GitHub Pages calling `localhost` | Run the API on a CORS-enabled public host, or open `index.html` locally |
| Page loads but button does nothing | JavaScript disabled | Re-enable JS in the browser |

---

## Reference

Everything in this section is reference material - anatomy of the key
files, port/URL cheat sheet, useful one-liners, and the full
requirements list. You don't need to read it linearly; flip to it when
you need it.

### A. Anatomy of the key files

#### `app/main.py`

```python
# Imports FastAPI, the model loader, and prometheus_client
# Defines five metrics (Histogram, Gauge, Counter x3)
# Wraps predict() with try/except/finally to record latency
# Exposes /predict, /health, and /metrics
```

The full file is short (~100 lines). Two patterns to study:

- **Lifespan loading** - `@asynccontextmanager async def lifespan(app):`
  loads the model once at startup. Per-request loading would be 100x slower.
- **Always-record-latency** - the `finally` block calls
  `PREDICTION_LATENCY.observe(time.monotonic() - start)` whether the
  call succeeded or raised. Without this, error paths would be invisible.

#### `app/model_loader.py`

Wraps `transformers.AutoModelForSequenceClassification` and exposes a
single `predict(text: str) -> tuple[str, float]`. The label name is
resolved through `model.config.id2label`. Keeping this out of `main.py`
means tests can import the model code without pulling in FastAPI.

#### `train/train.py`

Loads LexGLUE SCOTUS, filters to four labels, tokenizes with
`nlpaueb/legal-bert-base-uncased`, and fine-tunes for 3 epochs with
`AdamW` + linear warmup. Logs to MLflow. Saves the model + tokenizer.

#### `Dockerfile`

```
FROM python:3.10-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app/ ./app/
COPY saved_model/ ./saved_model/
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

The `COPY saved_model/` line is the **entire reason** the directory has
to exist before building.

#### `docker-compose.yml`

Four services - `api`, `mlflow`, `prometheus`, `grafana` - each with
its own port mapping and bind mount. The `grafana` service uses
`provisioning` to auto-register the Prometheus data source and load
the dashboard on first start.

#### `prometheus.yml`

```yaml
global:
  scrape_interval: 15s
scrape_configs:
  - job_name: legal-classifier-api
    static_configs:
      - targets: ["api:8000"]
  - job_name: prometheus
    static_configs:
      - targets: ["localhost:9090"]
```

The first job scrapes our service; the second lets Prometheus report
on *itself* (useful when you start adding alert rules).

#### `grafana/dashboards/dashboard.json`

Six panels: latency (timeseries), confidence (timeseries), label
counts (bar chart), request rate (timeseries), error rate (stat with
thresholds), total requests (stat). The PromQL expressions are the
ones you'd write by hand for a typical web service - `rate(...[1m])`
for per-second rates, `sum by (label) (...)` for per-class counts.

### B. Service URL reference

| Service     | URL                            | Default credentials |
|-------------|--------------------------------|---------------------|
| FastAPI     | http://localhost:8000          | - |
| API docs    | http://localhost:8000/docs     | - |
| Health      | http://localhost:8000/health   | - |
| Raw metrics | http://localhost:8000/metrics  | - |
| MLflow UI   | http://localhost:5000          | - |
| Prometheus  | http://localhost:9090          | - |
| Grafana     | http://localhost:3000          | `admin` / `admin`   |

### C. Useful one-liners

```powershell
# Tail logs for one service
docker compose logs -f api

# Restart a single service
docker compose restart api

# Wipe everything (containers + volumes) and start fresh
docker compose down -v
docker compose up -d --build

# Send 100 predictions as a load test
1..100 | ForEach-Object -Parallel {
  Invoke-RestMethod -Method Post -Uri "http://localhost:8000/predict" `
    -ContentType "application/json" `
    -Body '{"text":"The defendant was charged with assault and battery."}'
} -ThrottleLimit 8

# Push the dashboard to a running Grafana (after editing dashboard.json)
powershell -ExecutionPolicy Bypass -File .\scripts\reload_dashboard.ps1
```

### D. Requirements

- Docker Desktop 4.x or newer
- Python 3.10+ (only if you want to run uvicorn directly without Docker)
- A Google account (for Step 3)
- ~5 GB free disk for the saved model and Docker images
