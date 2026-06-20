"""
schemas.py
==========
Purpose : Pydantic v2 request/response models for the FastAPI app.
Why     : Validation is the front door of an ML service. Defining the
          expected shape here gives us:
            - automatic request validation (422 on bad input)
            - auto-generated Swagger docs (/docs)
            - type hints the rest of the code can rely on
"""

from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field, ConfigDict


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------
class HealthResponse(BaseModel):
    """Response model for GET /health."""
    status: str = Field(..., examples=["ok"])
    model_loaded: bool = Field(..., examples=[True])
    model_name: str = Field(..., examples=["LogisticRegression"])


# ---------------------------------------------------------------------------
# Prediction
# ---------------------------------------------------------------------------
class CustomerFeatures(BaseModel):
    """One customer's features — exactly what the model expects.

    Field constraints catch obvious mistakes (negative age, etc.) before
    they ever reach the model. The ``examples`` block powers the
    Swagger UI "Try it out" button.
    """
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "age": 45,
                "tenure": 5,
                "salary": 50000,
                "balance": 60000,
                "num_products": 2,
                "has_credit_card": 1,
                "is_active_member": 0,
                "gender": 1,
                "geography": 1,
            }
        }
    )

    age: int = Field(..., ge=18, le=120, description="Customer age in years")
    tenure: int = Field(..., ge=0, le=120, description="Months as a customer")
    salary: float = Field(..., ge=0, description="Annual salary in USD")
    balance: float = Field(..., ge=0, description="Account balance in USD")
    num_products: int = Field(..., ge=1, le=10, description="Number of bank products")
    has_credit_card: int = Field(..., ge=0, le=1, description="0 = no, 1 = yes")
    is_active_member: int = Field(..., ge=0, le=1, description="0 = no, 1 = yes")
    gender: int = Field(..., ge=0, le=1, description="0 = female, 1 = male")
    geography: int = Field(
        ..., ge=0, le=2,
        description="0 = France, 1 = Germany, 2 = Spain",
    )


class PredictRequest(BaseModel):
    """Batch prediction request — one or more customers at once."""
    instances: List[CustomerFeatures] = Field(
        ..., min_length=1,
        description="One or more customers to score.",
    )


class PredictionItem(BaseModel):
    """One prediction result — class, probability, and a friendly label."""
    prediction: int = Field(..., description="0 = no churn, 1 = churn")
    churn_probability: float = Field(..., ge=0.0, le=1.0)
    label: str = Field(..., examples=["churn", "no_churn"])


class PredictResponse(BaseModel):
    """Response model for POST /predict."""
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "model": "LogisticRegression",
                "count": 1,
                "predictions": [
                    {"prediction": 0, "churn_probability": 0.4998, "label": "no_churn"}
                ],
            }
        }
    )
    model: str
    count: int
    predictions: List[PredictionItem]


# ---------------------------------------------------------------------------
# Training
# ---------------------------------------------------------------------------
class TrainRequest(BaseModel):
    """Optional knobs for POST /train. All have safe defaults."""
    csv_path: Optional[str] = Field(
        default=None,
        description="Path to a CSV. Defaults to the bundled customer_churn.csv.",
    )


class ModelMetrics(BaseModel):
    accuracy: float
    precision: float
    recall: float
    f1: float
    roc_auc: float


class RunSummary(BaseModel):
    model: str
    run_id: str
    accuracy: float
    precision: float
    recall: float
    f1: float
    roc_auc: float


class TrainResponse(BaseModel):
    """Response model for POST /train — summary of the new run."""
    best_model: str
    best_run_id: str
    best_metrics: ModelMetrics
    all_runs: List[RunSummary]
    model_artifact: str = Field(..., description="Path to the saved best model.")


# ---------------------------------------------------------------------------
# Error envelope
# ---------------------------------------------------------------------------
class ErrorResponse(BaseModel):
    """Uniform error response shape for all endpoints."""
    detail: str
    error_type: str = "error"
