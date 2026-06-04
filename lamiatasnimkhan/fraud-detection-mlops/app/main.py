from __future__ import annotations
import uuid
import logging
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pathlib import Path

from .schemas import TransactionFeatures, PredictionResponse
from .predictor import predictor

log = logging.getLogger("fraudshield")
logging.basicConfig(level=logging.INFO)

app = FastAPI(title="FraudShield MLOps", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_credentials=True,
    allow_methods=["*"], allow_headers=["*"],
)


def _risk(p: float) -> tuple[bool, str]:
    if p >= 0.60: return True,  "HIGH"
    if p >= 0.25: return True,  "MEDIUM"
    return False, "LOW"


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "model_loaded": predictor._model is not None}


@app.post("/predict", response_model=PredictionResponse)
def predict(tx: TransactionFeatures) -> PredictionResponse:
    try:
        p = predictor.score(tx.model_dump())
        is_fraud, level = _risk(p)
        return PredictionResponse(
            transaction_id=uuid.uuid4().hex[:8],
            is_fraud=is_fraud,
            fraud_probability=round(p, 4),
            risk_level=level,
        )
    except Exception as e:
        log.exception("predict failed")
        raise HTTPException(status_code=500, detail=str(e))


# ── serve the dashboard (index.html, dashboard.js, style.css)
STATIC = Path(__file__).parent
app.mount("/static", StaticFiles(directory=STATIC), name="static")


@app.get("/")
def root() -> FileResponse:
    return FileResponse(STATIC / "index.html")