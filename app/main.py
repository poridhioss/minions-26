# ============================================================
# FastAPI app for the Legal Document Classifier.
#
# Single endpoint:  POST /predict
#   Input:   {"text": "The defendant was charged with ..."}
#   Output:  {"label": "Criminal Procedure", "confidence": 0.94}
# ============================================================

import time
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from prometheus_client import (
    CONTENT_TYPE_LATEST,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)

# Our own helper that loads the model and runs inference.
# Relative import: main.py lives INSIDE the app/ package, so we
# import the sibling module directly. This is what uvicorn uses
# when invoked as `uvicorn app.main:app`.
from . import model_loader


# ---------- Prometheus metrics ----------
# A Histogram of prediction latency, in seconds. Buckets cover
# the range we expect from Legal-BERT on CPU (a few hundred ms
# up to a couple of seconds for long inputs).
PREDICTION_LATENCY = Histogram(
    "legal_classifier_prediction_latency_seconds",
    "Time spent running model.predict() for a single request.",
    buckets=(0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 5.0),
)

# Confidence of the last successful prediction. Useful as a live
# "how sure is the model right now?" gauge on the dashboard.
PREDICTION_CONFIDENCE = Gauge(
    "legal_classifier_prediction_confidence",
    "Confidence (probability) of the most recent successful prediction.",
)

# One counter per label, so the dashboard can render a bar chart of
# how often each SCOTUS topic area is predicted.
PREDICTION_LABEL_TOTAL = Counter(
    "legal_classifier_prediction_label_total",
    "Total number of predictions per label.",
    ["label"],
)

# Total number of /predict requests received (success or failure).
REQUEST_TOTAL = Counter(
    "legal_classifier_request_total",
    "Total number of /predict requests received.",
)

# Number of /predict requests that raised an exception.
ERROR_TOTAL = Counter(
    "legal_classifier_error_total",
    "Total number of /predict requests that failed.",
)


# ---------- Request / response schemas ----------
class PredictRequest(BaseModel):
    text: str = Field(..., min_length=1, description="Legal document text to classify")


class PredictResponse(BaseModel):
    label: str
    confidence: float


# ---------- App lifecycle: load the model ONCE on startup ----------
@asynccontextmanager
async def lifespan(_app: FastAPI):
    # This runs when the server starts, before the first request.
    model_loader.load()
    yield
    # Nothing to clean up — the model stays in memory.


app = FastAPI(
    title="Legal Document Classifier",
    description="Classifies legal text into 4 categories using fine-tuned Legal-BERT.",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS: allow the static frontend (file://, localhost, GitHub Pages) to call
# this API from a browser. Without this, browsers block cross-origin POSTs.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],          # the API has no auth, so any origin is fine
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)


# ---------- Health check (handy for Docker / load balancers) ----------
@app.get("/health")
def health():
    return {"status": "ok"}


# ---------- Prometheus scrape endpoint ----------
@app.get("/metrics")
def metrics():
    """
    Exposes all registered Prometheus metrics in the text exposition
    format. Prometheus is configured (see prometheus.yml) to scrape
    this URL every 15 seconds.
    """
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)


# ---------- Prediction endpoint ----------
@app.post("/predict", response_model=PredictResponse)
def predict(req: PredictRequest):
    REQUEST_TOTAL.inc()
    start = time.perf_counter()
    try:
        label, confidence = model_loader.predict(req.text)
    except Exception as exc:
        ERROR_TOTAL.inc()
        # Don't leak internals to the client; just report the failure.
        raise HTTPException(status_code=500, detail=f"Prediction failed: {exc}") from exc
    finally:
        # Record latency even on failures so the dashboard can spot
        # slow-failing requests.
        PREDICTION_LATENCY.observe(time.perf_counter() - start)

    # Update the "live" metrics only on success.
    PREDICTION_CONFIDENCE.set(confidence)
    PREDICTION_LABEL_TOTAL.labels(label=label).inc()

    return PredictResponse(label=label, confidence=round(confidence, 4))
