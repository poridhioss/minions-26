---
title: Legal Document Classifier
emoji: ⚖️
colorFrom: indigo
colorTo: purple
sdk: docker
app_port: 7860
pinned: false
license: mit
short_description: FastAPI + Legal-BERT classifier with live Prometheus metrics.
---

# Legal Document Classifier

A FastAPI service that classifies US Supreme Court opinion excerpts into one
of four SCOTUS topic areas using Legal-BERT, instrumented with Prometheus
metrics and a small in-browser demo UI.

This Space runs the FastAPI API on port `7860` (the Hugging Face Spaces
default). The bundled `index.html` is exposed at `/` by a tiny static file
mount inside the container, so the whole demo is one URL.

## How the model is loaded

By default the service loads the checkpoint from the local `saved_model/`
directory. If that directory is empty (typical on Spaces, since the model
weights are not committed to the repo) the loader falls back to downloading
them from a Hugging Face Hub model repo, controlled by the env vars:

| Variable      | Purpose                                                   |
|---------------|-----------------------------------------------------------|
| `MODEL_DIR`   | Override the local checkpoint directory                  |
| `HF_MODEL_ID` | Hub repo id (e.g. `yourname/legal-bert-scotus`) to fetch  |
| `HF_TOKEN`    | Required only if the Hub repo is private                 |

The first request after boot may take a few seconds while the model
downloads; subsequent requests are cached on the container's ephemeral disk.

## Endpoints

| Method | Path        | Description                                       |
|--------|-------------|---------------------------------------------------|
| GET    | `/`         | Static demo UI (this is what you see in the tab)  |
| GET    | `/health`   | Liveness probe                                    |
| POST   | `/predict`  | `{ "text": "..." }` → label + confidence          |
| GET    | `/metrics`  | Prometheus exposition format                      |

## Local development

```bash
docker compose up --build
# API on http://localhost:8000
```

Inside the Space the same image is run but bound to port `7860`, and the
embedded demo automatically points at that origin via the `window.SPACE_CONFIG`
object baked into `index.html`.
