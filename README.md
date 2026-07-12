# Legal Document Classifier Observability

> A reproducible laboratory for building, training, serving,
> and monitoring a Legal-BERT text classifier. 
> It opens with a challenge, sets learning goals,
> then walks you through six chapters of implementation, each one
> explaining the **why** before the **how**. Work through Chapters 1 to 6
> in order.

This lab is written so a viewer who has never seen the project can
complete it end-to-end on a fresh Windows + Docker machine in roughly one
hour, **and** understand the role of every file along the way.

---

## Prologue: The Challenge

Legal organizations process thousands of documents every day. Manually
categorizing legal text is slow, expensive, and inconsistent. Modern
transformer models can automate this task, but deploying them into a
production-ready system requires much more than training a neural network.

In this laboratory, you will build a complete Legal Document
Classification pipeline that:

- Fine-tunes Legal-BERT on a curated subset of the SCOTUS benchmark.
- Serves predictions through a FastAPI REST endpoint.
- Tracks training experiments with MLflow.
- Monitors inference metrics using Prometheus.
- Visualizes system health in Grafana.
- Provides a browser-based web interface for end users.

By the end of the lab, you will have reproduced an end-to-end MLOps
workflow for legal NLP - the same shape used in real legal-tech products.

---

## Learning Objectives

By the end of this lab, you will be able to:

-  Fine-tune Legal-BERT on the SCOTUS dataset.
-  Understand transformer-based legal text classification.
-  Deploy a machine learning model using FastAPI.
-  Containerize the application using Docker.
-  Track experiments with MLflow.
-  Collect inference metrics with Prometheus.
-  Visualize system health using Grafana.
-  Test and use the deployed model through a web interface.

---

## System Overview

Before we write a single command, it helps to see the full pipeline as
one picture. Each box becomes a chapter later in the lab.

<img width="955" height="1011" alt="legal-Page-3 drawio (1)" src="https://github.com/user-attachments/assets/461466f1-3e34-4ba4-bb26-ebedcbd4175a" />



The two side-channels you don't see in the picture are **MLflow**
(records hyperparameters and metrics from Chapter 2's training run) and
**health checks** on the API container (Chapter 3). Both surface in the
web UIs you will visit later.

---

## Environment Setup

Exactly one thing has to be true before Chapter 1: your machine can
reach a working Docker daemon. Everything else is downloaded on demand.

### Prerequisites

| Requirement         | Purpose                                           |
|---------------------|---------------------------------------------------|
| Docker Desktop      | Runs the API, MLflow, Prometheus, and Grafana     |
| Google account      | Chapter 2 trains in a free Colab T4 GPU           |
| Git                 | Clone this repository                             |
| PowerShell 5.1+     | All API testing in this lab uses Invoke-RestMethod|

> If you are on macOS or Linux, every PowerShell snippet in this
> document also works inside PowerShell 7, and the `docker compose`
> commands are identical.

### Verify your baseline

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

```powershell
docker run --rm hello-world
```

If you see *"Hello from Docker!"*, the daemon, the network, and the
default registry all work, and you are ready for Chapter 1.

---

# Chapter 1: Understanding the System

> **Why this chapter exists.** Before you run a single command, you need
> a single mental picture of every component in the stack. This chapter
> gives you that picture. Subsequent chapters will keep referring back
> to the diagram and the file tree, so take five minutes to absorb them.
<img width="716" height="631" alt="image" src="https://github.com/user-attachments/assets/7c481404-63d0-47d5-83d4-3b8f38893141" />

## What You Will Build

A paragraph of legal text goes in, and a labelled topic area comes out.
The model classifies text into one of four U.S. Supreme Court topic
areas:

| Label ID | Topic area         |
|----------|--------------------|
| 0        | Criminal Procedure |
| 1        | Civil Rights       |
| 2        | First Amendment    |
| 3        | Economic Activity  |

The classifier is **Legal-BERT** (`nlpaueb/legal-bert-base-uncased`), a
transformer that has already been pre-trained on large legal corpora.
We **fine-tune** it on the SCOTUS split of the
[LexGLUE](https://huggingface.co/datasets/coastalcph/lex_glue)
benchmark. Fine-tuning is short (3 epochs) because the heavy lifting
was already done in pre-training.



## Implementation

### The five components

<img width="1071" height="102" alt="legal-Page-3 drawio" src="https://github.com/user-attachments/assets/dfac2372-ff9f-4b5d-bb51-0fb21d0dda1b" />


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

### Where files live

```
legal-doc-classifier/
+-- saved_model/                 
+-- app/
|   +-- __init__.py               <- makes `app` an importable package
|   +-- main.py                   <- FastAPI app: /predict, /health, /metrics
|   +-- model_loader.py           <- loads Legal-BERT once, exposes predict()
+-- train/
|   +-- train.py                  <- Colab training script 
+-- grafana/
|   +-- dashboards/dashboard.json <- pre-built monitoring dashboard
|   +-- provisioning/
|       +-- datasources/prometheus.yml  <- auto-registers Prometheus
|       +-- dashboards/dashboards.yml   <- tells Grafana where dashboards live
+-- scripts/                      <- PowerShell helpers for ops tasks
+-- prometheus.yml                <- scrape config (15 s, target api:8000)
+-- index.html                    <- static frontend (Chapter 5)
+-- Dockerfile                    <- builds the API image
+-- docker-compose.yml            <- orchestrates api + mlflow + prometheus + grafana
+-- requirements.txt              <- Python dependencies
+-- README.md                    
```

> **WARNING:** `saved_model/` is **not** in git - it weighs ~400 MB.
> Chapter 2 produces it, Chapter 3 consumes it.

### Clone the project

```powershell
cd E:\Projects
git clone https://github.com/bountyhunter12/legal-doc-classifier-observability.git legal-doc-classifier
cd legal-doc-classifier
```

If you already have the project on disk, just `cd` into it.

### Verify the tree

```powershell
Get-ChildItem -Force | Select-Object Name, Mode
```

You should see the folders listed above. The `saved_model/` folder will
be empty for now - that is correct.

## Under the Hood

### What is Legal-BERT?

BERT is a transformer encoder pre-trained on a large general corpus
using two objectives: masked language modeling and next-sentence
prediction. **Legal-BERT** is the same architecture, but pre-trained on
legal text - case law, statutes, contracts. Its token embeddings
already know what *petitioner*, *respondent*, *habeas corpus*, and
*writ of certiorari* mean before we fine-tune it.

The cost of pre-training is days on a multi-GPU cluster, so we don't
do it. The cost of **fine-tuning** the classification head is minutes
on a single T4 - that is Chapter 2.

### What is SCOTUS?

**SCOTUS** stands for *Supreme Court of the United States*. The LexGLUE
SCOTUS split is a benchmark of U.S. Supreme Court opinions, each
labelled with one of 14 issue areas. We discard 10 of them because we
only want four coarse classes. The filtering and remap happens inside
`train/train.py` and is invisible to the rest of the system.

### What is MLflow?

MLflow is an open-source experiment tracker. During Chapter 2's
training run it records the hyperparameters (learning rate, batch
size, epochs) and per-epoch metrics (loss, accuracy, F1) into a local
SQLite store. The `mlflow` service in `docker-compose.yml` is just the
web UI on top of that store, so you can compare runs in your browser
without writing code.

## Verification

By the end of this chapter you should be able to:

- Point at any folder in the tree and explain what lives there.
- Point at any box in the component diagram and name the chapter that
  builds it.
- Explain, in one sentence, what Legal-BERT is and why we don't train
  it from scratch.

If you can, you are ready for Chapter 2.

## Troubleshooting

| Symptom                                              | Cause                          | Fix                                              |
|------------------------------------------------------|--------------------------------|--------------------------------------------------|
| `open //./pipe/dockerDesktopLinuxEngine: ...`        | Docker Desktop not running     | Start it from the Start menu, wait 30 s, retry   |
| `docker: command not found`                         | Docker not in `PATH`           | Reinstall Docker Desktop or add `C:\Program Files\Docker\Docker\resources\bin` to `PATH` |
| WSL2 kernel missing                                  | WSL not installed              | `wsl --install` from an elevated PowerShell, then reboot |

---

# Chapter 2: Training the Model

> **Why this chapter exists.** A saved model is the single artifact the
> rest of the system depends on. Every other chapter either loads it,
> serves it, or measures it. This chapter is the only one that needs a
> GPU, and we deliberately push the GPU work to Google Colab so the
> rest of the lab can run on any laptop.

## What You Will Build

A fine-tuned Legal-BERT model on disk, in a folder called
`saved_model/`, containing the model weights, the tokenizer, and the
configuration that says "this is a 4-class classifier."

We train in Colab because the free T4 GPU finishes in ~10-20 minutes,
vs. several hours on a laptop CPU.

### Why Colab

| Option                  | Cost  | Time     | Verdict                          |
|-------------------------|-------|----------|----------------------------------|
| Local CPU               | Free  | 4-8 h    | Not practical                    |
| Local GPU (RTX 30/40)   | Owned | ~20 min  | Good but not assumed             |
| **Google Colab free T4**| Free  | ~15 min  | **Default for this lab**         |
| Colab Pro / AWS         | $$    | ~5 min   | Out of scope                     |

## Implementation

### Steps

1. Open https://colab.research.google.com and create a new notebook.
2. Set the runtime: **Runtime -> Change runtime type -> T4 GPU -> Save**.
3. In the first cell, install dependencies:

   ```python
   !pip install -q transformers torch datasets mlflow scikit-learn
   ```

4. In a second cell, download the training script and run it:

   ```python
   !wget -q https://raw.githubusercontent.com/bountyhunter12/legal-doc-classifier-observability/main/train/train.py
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

### Download the saved model

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

> **NOTE:** HuggingFace splits checkpoints across several files by
> default; that is fine - the loader just needs the whole directory.

## Under the Hood

### Tokenization

Legal-BERT's tokenizer is a WordPiece tokenizer pre-trained on legal
text. It splits each input sentence into **sub-word tokens** - rare
words get broken into common pieces (`petitioner` -> `petit` + `##ioner`),
and every token maps to an integer ID in a 30 k-entry vocabulary.

The `transformers` library handles this for you: `tokenizer(text,
padding=True, truncation=True, max_length=512)` returns three tensors -
`input_ids`, `attention_mask`, and (sometimes) `token_type_ids` - that
are the actual numeric inputs to the model.

### Attention

Every transformer layer uses **self-attention**: each token looks at
every other token in the same input and asks "how relevant are you to
my meaning?" A 12-layer, 768-hidden BERT-base has 12 such attention
heads per layer, which is what gives the model its deep sense of
context. For a 512-token input, each layer runs 512 * 512 = 262 k
attention comparisons, so a forward pass is not free.

### Fine-tuning vs. pre-training

Pre-training teaches the model general language understanding.
Fine-tuning teaches the model a **specific task** - in our case,
4-class classification. During fine-tuning we:

- Replace BERT's original pre-training head with a fresh 4-class head.
- Continue training on the SCOTUS labels, with all weights unfrozen.
- Use a **small learning rate** (2e-5) so the model doesn't catastrophically
  forget the legal vocabulary it already knows.

### Learning rate and epochs

The two most important fine-tuning hyperparameters are:

- **Learning rate** - we use `2e-5`. Higher (1e-4) usually destroys
  pre-training; lower (1e-6) learns too slowly.
- **Epochs** - we use **3**. Validation loss typically bottoms out by
  epoch 2 or 3; going further overfits.

If you change either, re-run the script and compare the new MLflow run
against the previous one in the MLflow UI.

### MLflow logging

MLflow logging happens through a local SQLite or in-memory tracking URI
inside the Colab session. When you stand up the `mlflow` service in
Chapter 3, the **same** run is visible at `http://localhost:5000`
because `train.py` writes to a file the docker volume mounts.

## Verification

Inside Colab, after training:

```python
from transformers import AutoTokenizer, AutoModelForSequenceClassification
m = AutoModelForSequenceClassification.from_pretrained("./saved_model")
t = AutoTokenizer.from_pretrained("./saved_model")
print(m.config.num_labels)   # should print 4
```

If that prints `4`, the model is healthy and is ready to be moved into
the project root for Chapter 3.

## Troubleshooting

| Symptom                    | Cause                              | Fix                                                           |
|----------------------------|------------------------------------|---------------------------------------------------------------|
| `CUDA out of memory`       | Batch size too large for the GPU   | Lower per-device batch size in the training script (e.g. 4)   |
| `datasets` download hangs  | Slow / blocked network             | Re-run; LexGLUE is ~50 MB                                     |
| `Runtime disconnected`     | Colab idle timeout                 | Keep the tab focused or use Colab Pro                         |
| `mlflow` not finding the run later | Tracking URI mismatch       | Re-train with the same tracking URI; MLflow runs are not portable across URIs by default |


---

# Chapter 3: Deploy the API

> **Why this chapter exists.** A model on disk does not help anyone.
> This chapter wraps the model in a long-running HTTP service so any
> client (a browser, a notebook, a CI test) can send text and get a
> label back. We use FastAPI for the framework and Docker for the
> runtime so the API behaves the same on your laptop, your CI box, and
> a cloud VM.

## What You Will Build

A FastAPI service exposing three endpoints:

| Method | Path        | Purpose                                          |
|--------|-------------|--------------------------------------------------|
| POST   | `/predict`  | Run inference, return `{ label, confidence }`    |
| GET    | `/health`   | Liveness probe - returns `{ "status": "ok" }`    |
| GET    | `/metrics`  | Prometheus text format (consumed in Chapter 4)   |

The service is a single Docker container (`api`) that loads the model
**once** at startup (not per request) via FastAPI's `lifespan` context.
A second container (`mlflow`) hosts the experiment-tracking UI.

## Implementation

### Build and start the stack

```powershell
# Make sure Docker Desktop is running
docker version | Select-String "Server Version"

# Confirm the saved model is in place
Get-ChildItem .\saved_model
```

You should see `config.json`, `pytorch_model.bin` (or
`model.safetensors`), `tokenizer.json`, `vocab.txt`, etc.

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

### Send your first prediction

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

## Under the Hood

### Docker

A Docker image is a sealed snapshot of a filesystem plus a command to
run. The lab's `Dockerfile` extends `python:3.10-slim`, installs
`requirements.txt`, copies `app/` and `saved_model/`, and runs
`uvicorn app.main:app`:

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

The `COPY saved_model/` line is the **entire reason** that directory
has to exist before building. Compose binds the host's `saved_model/`
to `/app/saved_model` inside the container so re-training on the host
becomes visible to the API on the next container restart.

### Uvicorn

**Uvicorn** is the ASGI server that actually runs FastAPI. ASGI is the
async successor to WSGI - it lets FastAPI serve many requests
concurrently from a single process. The `0.0.0.0` host is intentional:
it tells uvicorn to listen on every network interface inside the
container, not just `127.0.0.1` (which would block Docker port-mapping).

### FastAPI lifespan

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    model_loader.load()
    yield
    # shutdown logic, if any
```

This block runs **once** at startup and again at shutdown. Loading a
transformer takes a few seconds; doing it per request would multiply
latency by 100x. FastAPI's `@asynccontextmanager` is the modern
replacement for the deprecated `@app.on_event("startup")` hook.

### Model caching

`app/model_loader.py` is a thin wrapper around
`transformers.AutoModelForSequenceClassification` that returns
`(label_name, confidence)`. It keeps the loaded model on a module-level
variable so the lifespan code only loads once and every request gets
the same instance. Keeping this out of `main.py` means we can unit-test
it without importing FastAPI.

## Verification

```powershell
# Health check
(Invoke-WebRequest http://localhost:8000/health).Content
# -> {"status":"ok"}

# Tail the logs
docker compose logs -f api
```

You should see a single `Uvicorn running on http://0.0.0.0:8000` line
and no error tracebacks. Then:

```powershell
# Hit /predict a few times with different texts
1..5 | ForEach-Object {
  Invoke-RestMethod -Method Post -Uri "http://localhost:8000/predict" `
    -ContentType "application/json" `
    -Body '{"text":"The court held that the search violated the Fourth Amendment."}'
}
```

All five calls should complete in under a second, with the same
`Criminal Procedure` label.

## Troubleshooting

| Symptom                              | Cause                              | Fix                                                            |
|--------------------------------------|------------------------------------|----------------------------------------------------------------|
| `OSError: saved_model not found`     | `saved_model/` empty or wrong path | Re-run Chapter 2, unzip into project root                      |
| Container restarts in a loop         | Model load crashed                 | `docker compose logs api` - look for the stack trace           |
| `port 8000 already in use`           | Another process on 8000            | Edit `docker-compose.yml` to map `8001:8000`                   |
| `Invoke-RestMethod` returns 415       | Wrong content type                 | Always pass `-ContentType "application/json"`                  |
| `curl` works, browser does not       | CORS middleware missing            | Already enabled in `app/main.py` - rebuild the api container   |

---

# Chapter 4: MLOps Monitoring

> **Why this chapter exists.** A deployed model is a black box unless
> you measure it. This chapter adds a metrics pipeline so we can see,
> in real time, how often the API is called, how slow it is, what
> labels it predicts, and how many errors it throws. With these signals
> in place, you can spot regressions, capacity issues, and data drift
> before users complain.

## What You Will Build

A monitoring pipeline that fans out from the API into a queryable
time-series store and a dashboard:

```
   FastAPI (/metrics)
        |
        v
   Prometheus    (scrapes every 15 s, stores time-series)
        |
        v
      Grafana     (queries Prometheus, renders the dashboard)
```

Two new services join `docker-compose.yml`:

| Service     | Port  | Role                                              |
|-------------|-------|---------------------------------------------------|
| Prometheus  | 9090  | Polls `api:8000/metrics` every 15 s, stores data  |
| Grafana     | 3000  | Queries Prometheus, renders the dashboard         |

The `api` service does not need to change - it already exposes
`/metrics` through the `prometheus_client` library.

## Implementation

### Bring up the full stack

```powershell
# Bring up the full stack (4 services)
docker compose up -d --build

# Confirm all four are running
docker compose ps
```

You should see `api`, `mlflow`, `prometheus`, `grafana` all in `Up`.

### Verify Prometheus can reach the API

```powershell
Invoke-RestMethod http://localhost:9090/api/v1/targets |
  Select-Object -ExpandProperty data |
  ForEach-Object { "$($_.labels.job): $($_.health)" }
# -> legal-classifier-api: up
# -> prometheus: up
```

### Generate traffic so the dashboard has something to show

```powershell
1..20 | ForEach-Object {
  Invoke-RestMethod -Method Post -Uri "http://localhost:8000/predict" `
    -ContentType "application/json" `
    -Body '{"text":"The defendant was charged with assault and battery."}'
}
```

### Open the Grafana dashboard

```powershell
Start-Process http://localhost:3000
```

Log in with `admin` / `admin`. The env vars in `docker-compose.yml`
disable the password-reset prompt and allow anonymous access for local
development. The dashboard titled **"Legal Document Classifier -
Monitoring"** is auto-loaded in the **Legal Classifier** folder.

You should see:

- **Total Requests** ticking up
- **Request Rate per minute** showing non-zero
- **Label Prediction Counts** filling in
- **Average Prediction Latency** holding steady around 100-400 ms
<img width="1911" height="772" alt="Screenshot 2026-06-07 174613" src="https://github.com/user-attachments/assets/6f4e1373-afec-4831-a06b-88240adca95f" />
<img width="1918" height="876" alt="Screenshot 2026-06-07 175715" src="https://github.com/user-attachments/assets/462a262e-614a-4a93-8a39-4d5798ee944d" />
<img width="1906" height="901" alt="Screenshot 2026-06-07 175724" src="https://github.com/user-attachments/assets/3b57ff1b-1599-4866-bb25-acef7899d959" />


## Under the Hood

### Metrics being collected

| Metric                                              | Type      | What it tells you                              |
|-----------------------------------------------------|-----------|------------------------------------------------|
| `legal_classifier_prediction_latency_seconds`       | Histogram | Per-request inference time                     |
| `legal_classifier_prediction_confidence`            | Gauge     | Confidence of the most recent prediction       |
| `legal_classifier_prediction_label_total{label=...}`| Counter   | Lifetime count per predicted class             |
| `legal_classifier_request_total`                    | Counter   | Total `/predict` calls                         |
| `legal_classifier_error_total`                      | Counter   | Total failed calls                             |

### How Prometheus scrapes the API

`prometheus.yml` declares one scrape job, `legal-classifier-api`,
that points at `api:8000/metrics` every 15 seconds. `api` resolves
via Docker's internal DNS to the API container's IP:

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
on **itself** (useful when you start adding alert rules).

### How the API exposes metrics

`prometheus_client` in `app/main.py` registers five collectors and
exposes them in Prometheus text format on `GET /metrics`. The
`try/except/finally` block in `predict()` records latency on **both**
success and failure paths - the `finally` block calls
`PREDICTION_LATENCY.observe(time.monotonic() - start)` whether the
call succeeded or raised. Without this, error paths would be invisible.

### How Grafana picks up the dashboard

`grafana/provisioning/datasources/prometheus.yml` registers Prometheus
as the default Grafana data source, and
`grafana/provisioning/dashboards/dashboards.yml` points Grafana at
`/var/lib/grafana/dashboards`, which is bind-mounted to
`./grafana/dashboards/` on the host. The dashboard JSON references
the datasource by **name** (`Prometheus`), not by UID, so Grafana's
auto-generated UIDs don't break panel binding.

The six panels in `dashboard.json` are:

1. **Latency** (timeseries) - histogram quantile
2. **Confidence** (timeseries) - gauge
3. **Label counts** (bar chart) - `sum by (label) (...)`
4. **Request rate** (timeseries) - `rate(...[1m])`
5. **Error rate** (stat with thresholds) - `rate(...[5m])`
6. **Total requests** (stat) - simple counter

## Verification

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

If both return data, the entire metrics pipeline is wired correctly.

## Troubleshooting

| Symptom                                          | Cause                                | Fix                                                                              |
|--------------------------------------------------|--------------------------------------|----------------------------------------------------------------------------------|
| Prometheus target `down`                         | `api:8000` not reachable             | `docker compose logs api` - is the model loaded?                                 |
| Grafana panel "No data"                          | Datasource binding broken            | Re-upload the dashboard (see `scripts/reload_dashboard.ps1`)                     |
| `/metrics` returns HTML 404                      | uvicorn not running the new code     | `docker compose up -d --build api`                                               |
| Grafana asks to change the password              | `GF_SECURITY_DISABLE_INITIAL_ADMIN_PASSWORD_RESET` missing | Already set in `docker-compose.yml`; recreate with `docker compose up -d --force-recreate grafana` |

---

# Chapter 5: User Interface

> **Why this chapter exists.** Not every user of this system is a
> developer. This chapter gives non-technical viewers a friendly way
> to classify text without touching `curl` or PowerShell. It also
> doubles as a smoke test for the API - if the page can reach the
> service, you know the network and CORS are healthy.

## What You Will Build

A single static file, `index.html`, that:

- Has a text area and a **Classify** button.
- POSTs to `http://localhost:8000/predict`.
- Renders the predicted label as a coloured badge and shows the
  confidence score with two decimals.
- Shows a spinner during inference and an error message if the API
  is unreachable.

The four label colours (red, blue, green, amber) are defined in a
small `:root` CSS block at the top of the file and are easy to retheme.

<img width="1841" height="837" alt="Screenshot 2026-06-03 201102" src="https://github.com/user-attachments/assets/e3c5133f-71b2-4ab7-b3da-7cf51b5ddc3f" />



## Verification

1. Type a paragraph of legal text into the box.
2. Click **Classify**.
3. Within ~1 second you should see a coloured badge with the topic
   area and a confidence percentage.

If the badge shows **Criminal Procedure** for *The defendant was
charged with assault and battery*, the full stack - frontend, API,
model, metrics - is working end-to-end.

---

# Chapter 6: Complete System Validation

> **Why this chapter exists.** Most READMEs end after a happy-path
> walkthrough. This chapter is the missing piece: a single,
> ordered, end-to-end test that you can run from a fresh machine to
> prove the entire system works. It is also the script to follow when
> you come back to this project in six months and want to be sure
> nothing rotted.

## End-to-End Test

Follow these ten steps in order. Each step is something you have
already done in earlier chapters - this chapter is the rehearsal.

1. **Train the model.** In Colab, run `train.py` and download
   `saved_model.zip`.
2. **Save the model.** Unzip into the project root so `saved_model/`
   contains the model and tokenizer files.
3. **Start Docker.** Confirm `docker version` shows a Server section.
4. **Test the API.** `Invoke-RestMethod` against `/predict` returns a
   label and confidence.
5. **Generate traffic.** Send 20+ predictions so the dashboard has
   something to plot.
6. **Open Grafana.** `http://localhost:3000`, log in `admin` / `admin`.
7. **Open Prometheus.** `http://localhost:9090`, check
   `/api/v1/targets` for the `legal-classifier-api` job being `up`.
8. **Open the frontend.** Either `Start-Process .\index.html` or
   visit the GitHub Pages URL.
9. **Submit legal text.** Type or paste a paragraph and click
   **Classify**.
10. **Verify dashboard updates.** Within ~15 seconds, the
    **Total Requests**, **Request Rate**, and **Label Prediction
    Counts** panels all move.

If all ten steps pass, you have reproduced an end-to-end MLOps
workflow: training, serving, monitoring, visualization, and end-user
interface - the same shape used in real production legal-tech systems.

---

# Epilogue: The Complete System

Take a step back. You have just built, deployed, and validated six
distinct components. Here is the role each one played:

| Component   | Purpose                                                  |
|-------------|----------------------------------------------------------|
| Legal-BERT  | The classifier itself - domain-adapted transformer       |
| FastAPI     | The serving layer - HTTP API around the model            |
| Docker      | The deployment layer - reproducible runtime environment  |
| MLflow      | Experiment tracking - hyperparameters and metrics       |
| Prometheus  | Monitoring - time-series of inference signals            |
| Grafana     | Visualization - dashboard for humans                     |
| Frontend    | User interaction - browser-based classifier UI           |

## The Principles

Five design principles fall out of the architecture you just built.
Keep these in mind when you adapt the lab to a new domain.

1. **Fine-tune before deployment.** A domain-specific model is
   dramatically better than a general one for legal text.
2. **Load once, predict many.** Cache the model at API startup so
   every request gets a sub-second response.
3. **Monitor everything.** Every prediction should emit a metric; you
   cannot improve what you cannot see.
4. **Containerize for reproducibility.** Docker ensures the dev
   machine, the CI box, and production behave identically.
5. **Separate concerns.** Training, serving, monitoring, and
   visualization are independent services. Swap any one of them
   without touching the others.

## End-to-End Validation

The shortest possible workflow that exercises every component:

```powershell
# 1. Clone the project
git clone https://github.com/bountyhunter12/legal-doc-classifier-observability.git
cd legal-doc-classifier-observability

# 2. Train the model in Colab (see Chapter 2)
#    Download saved_model.zip and unzip into the project root.

# 3. Start all services
docker compose up -d --build

# 4. Test the API
Invoke-RestMethod -Method Post -Uri "http://localhost:8000/predict" `
  -ContentType "application/json" `
  -Body '{"text":"The defendant was charged with assault and battery."}'

# 5. Generate load
1..20 | ForEach-Object {
  Invoke-RestMethod -Method Post -Uri "http://localhost:8000/predict" `
    -ContentType "application/json" `
    -Body '{"text":"The court held that the search violated the Fourth Amendment."}'
}

# 6. Open dashboards
Start-Process http://localhost:5000   # MLflow
Start-Process http://localhost:9090   # Prometheus
Start-Process http://localhost:3000   # Grafana (admin / admin)

# 7. Open the frontend
Start-Process .\index.html
```

If those seven steps work, you have a working MLOps pipeline.

## Reference

Anatomy of the key files, useful one-liners, and the requirements list.
Flip to it when you need it.

### A. Anatomy of the key files

#### `app/main.py`

```
Imports FastAPI, the model loader, and prometheus_client
Defines five metrics (Histogram, Gauge, Counter x3)
Wraps predict() with try/except/finally to record latency
Exposes /predict, /health, and /metrics
```

Two patterns to study:

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

| Service        | URL                              | Default credentials |
|----------------|----------------------------------|---------------------|
| FastAPI        | http://localhost:8000            | -                   |
| API docs       | http://localhost:8000/docs       | -                   |
| Health         | http://localhost:8000/health     | -                   |
| Raw metrics    | http://localhost:8000/metrics    | -                   |
| MLflow UI      | http://localhost:5000            | -                   |
| Prometheus     | http://localhost:9090            | -                   |
| Grafana        | http://localhost:3000            | `admin` / `admin`   |

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
- A Google account (for Chapter 2)
- ~5 GB free disk for the saved model and Docker images

## Troubleshooting

One consolidated table for the whole lab, in the order a new viewer
will hit the problems.

| Problem                              | Solution                                              |
|--------------------------------------|-------------------------------------------------------|
| Docker not running                   | Start Docker Desktop, wait 30 s, retry                |
| `docker: command not found`         | Reinstall Docker Desktop or add `C:\Program Files\Docker\Docker\resources\bin` to `PATH` |
| WSL2 kernel missing                  | `wsl --install` from an elevated PowerShell, then reboot |
| Missing model (`OSError: saved_model not found`) | Re-run Chapter 2, unzip into project root |
| API fails with stack trace           | `docker compose logs api` - check the trace           |
| Port 8000 already in use             | Edit `docker-compose.yml` to map `8001:8000`          |
| `port 5000 already in use`           | Stop the local MLflow or remap to `5001:5000`         |
| Grafana dashboard empty              | Send 20+ predictions, then refresh                    |
| Grafana "No data" on a panel         | Re-upload the dashboard via `scripts/reload_dashboard.ps1` |
| Grafana asks to change the password  | Recreate the container: `docker compose up -d --force-recreate grafana` |
| Frontend CORS error                  | Open `index.html` locally or run the API on a CORS-enabled public host |
| Frontend "Could not connect to API"  | The Docker stack is not running - run Chapter 3       |
| Training `CUDA out of memory`        | Lower per-device batch size in the training script    |
| Training `Runtime disconnected`      | Colab idle timeout - keep the tab focused or use Colab Pro |

---

# Chapter 7: Deploying to Hugging Face Spaces (Free)

> **Why this chapter exists.** Chapters 1-6 walk you through the local
> Docker stack. This chapter is for the moment when you want to share your
> classifier with the world without paying for a server. Hugging Face
> Spaces gives every account a free CPU container that never sleeps, has
> no time limit, and asks for no credit card. The only cost is that the
> container has 16 GB of RAM and 2 vCPUs - which is plenty for Legal-BERT
> but means we can't ship the 418 MB checkpoint inside the git repo. We
> split the deployable into two halves: the *image* (this repo) and the
> *weights* (a Hugging Face Hub model repo). The image downloads the
> weights on first boot.

## What you will end up with

1. A Hugging Face **model repo** holding the Legal-BERT checkpoint.
2. A Hugging Face **Space** (Docker SDK) running this FastAPI image.
3. A public URL of the form `https://huggingface.co/spaces/<you>/legal-classifier`
   that loads the embedded demo UI and exposes `/predict`, `/health`,
   `/metrics`.

## Step 1: Create a free Hugging Face account

Sign up at <https://huggingface.co/join>. The free tier is all you need.

## Step 2: Authenticate from your laptop

The fastest way is the CLI:

```bash
pip install -U huggingface_hub
huggingface-cli login
# paste a token from https://huggingface.co/settings/tokens
```

On Windows PowerShell the same commands work; the token is stored in
`%USERPROFILE%\.cache\huggingface\token`.

## Step 3: Push the checkpoint to a Hub model repo

From the project root (`puku-editor-interns-faozia-fariha-9/legal-doc-classifier/`):

```bash
python scripts/upload_to_hf.py --repo-id <your-hf-username>/legal-bert-scotus
```

Add `--private` if you don't want the weights visible to anyone. The script
creates the repo if needed and uploads every file inside `saved_model/`
(`config.json`, `model.safetensors`, tokenizer files, etc.). For our 418 MB
checkpoint this typically takes 1-3 minutes.

## Step 4: Create the Space

1. Open <https://huggingface.co/new-space>.
2. **Name**: `legal-classifier` (or anything you like).
3. **SDK**: pick **Docker**. Gradio/Static are not appropriate here.
4. **Hardware**: leave the free CPU tier selected.
5. Click **Create Space**.

## Step 5: Wire the Space to this repo

You have two options. Pick whichever is easier.

### Option A: Link a GitHub repo (recommended)

1. In your Space's **Files** tab, click **Add Space secrets** and set:
   - `HF_MODEL_ID` = `<your-hf-username>/legal-bert-scotus`
   - `HF_TOKEN`    = your HF token (only if the model repo is private)
2. In **Settings -> Repository**, click **Connect to a GitHub repo** and
   select the `poridhioss/minions-26` repo at branch `main`. Spaces will
   pull the `legal-doc-classifier/` subfolder automatically as long as
   `README_HF.md` is present at the Space root.

   > **Note**: if Spaces refuses to use a subfolder, copy the contents of
   > `legal-doc-classifier/` into a fresh repo and connect that. The whole
   > project is ~0.1 MB without `saved_model/`, so the clone is instant.

### Option B: Push directly with `git`

```bash
# Add the Space as a second remote.
git remote add space https://huggingface.co/spaces/<your-hf-username>/legal-classifier

# Push only the subfolder (use git subtree, or push from inside it).
cd legal-doc-classifier
git subtree push --prefix=. space main
```

The `README_HF.md` at the top of `legal-doc-classifier/` contains the
YAML frontmatter (`sdk: docker`, `app_port: 7860`) that Spaces needs to
recognise the project.

## Step 6: Set the secrets

In the Space's **Settings -> Variables and secrets**, add:

| Name           | Value                                  | Secret? |
|----------------|----------------------------------------|---------|
| `HF_MODEL_ID`  | `<your-hf-username>/legal-bert-scotus` | no      |
| `HF_TOKEN`     | your HF token                          | **yes** |

That is all. The next build (triggered automatically by the git push or
the GitHub sync) will:

1. Build the Docker image from `Dockerfile` (no `saved_model/` is shipped,
   the COPY step copies an empty directory thanks to `.gitkeep`).
2. Start uvicorn on port `7860` (the `PORT` env var is set by Spaces).
3. Call `model_loader.load()` during startup, which sees the empty local
   checkpoint and falls back to `huggingface_hub.snapshot_download` using
   `HF_MODEL_ID`. The first request will be slow; every later one is fast.

## Step 7: Verify

Open the Space URL in a browser. You should see the same demo UI as
locally, but pointing its `POST /predict` at the Space's own origin (the
`window.HF_SPACE_CONFIG` block injected by `app/main.py` handles this).

```bash
curl https://<your-hf-username>-legal-classifier.hf.space/health
# {"status":"ok"}

curl -X POST https://<your-hf-username>-legal-classifier.hf.space/predict \
     -H 'Content-Type: application/json' \
     -d '{"text":"The defendant was charged with assault and battery."}'
# {"label":"Criminal Procedure","confidence":0.91}
```

## Why this is free forever

- HF Spaces free CPU containers do not sleep after inactivity, unlike
  Render's free web services.
- No credit card is required.
- Hugging Face is the natural home for a transformer demo, so sharing
  the URL with other ML practitioners will be received warmly.

## When you outgrow it

- Need a GPU? Spaces offers paid T4/A10G instances for ~$0.60/hr; turn it
  on in **Settings -> Hardware**.
- Need >16 GB RAM for a bigger model? Same answer.
- Need full Prometheus + Grafana observability? Re-deploy the whole stack
  to Render (see the README on the bounty repo) and keep using the HF Hub
  model repo as the source of truth for the weights.
