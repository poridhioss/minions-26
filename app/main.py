# ============================================================
# FastAPI app for the Legal Document Classifier.
#
# Single endpoint:  POST /predict
#   Input:   {"text": "The defendant was charged with ..."}
#   Output:  {"label": "Criminal Procedure", "confidence": 0.94}
# ============================================================

from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

# Our own helper that loads the model and runs inference.
# Relative import: main.py lives INSIDE the app/ package, so we
# import the sibling module directly. This is what uvicorn uses
# when invoked as `uvicorn app.main:app`.
from . import model_loader


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


# ---------- Prediction endpoint ----------
@app.post("/predict", response_model=PredictResponse)
def predict(req: PredictRequest):
    try:
        label, confidence = model_loader.predict(req.text)
    except Exception as exc:
        # Don't leak internals to the client; just report the failure.
        raise HTTPException(status_code=500, detail=f"Prediction failed: {exc}") from exc

    return PredictResponse(label=label, confidence=round(confidence, 4))
