from __future__ import annotations
from pydantic import BaseModel, Field, conlist
from typing import Literal


class TransactionFeatures(BaseModel):
    """Matches the 30 columns of creditcard.csv (Time, V1..V28, Amount)."""
    Time: float
    Amount: float
    V1: float; V2: float; V3: float; V4: float; V5: float
    V6: float; V7: float; V8: float; V9: float; V10: float
    V11: float; V12: float; V13: float; V14: float; V15: float
    V16: float; V17: float; V18: float; V19: float; V20: float
    V21: float; V22: float; V23: float; V24: float; V25: float
    V26: float; V27: float; V28: float


class PredictionResponse(BaseModel):
    transaction_id: str
    is_fraud: bool
    fraud_probability: float = Field(ge=0.0, le=1.0)
    risk_level: Literal["LOW", "MEDIUM", "HIGH"]