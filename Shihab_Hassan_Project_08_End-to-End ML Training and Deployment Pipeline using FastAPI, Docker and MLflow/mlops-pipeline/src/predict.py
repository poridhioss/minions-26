"""
predict.py
==========
Purpose : Wrap the trained model behind a tiny, testable class.
Why     : The FastAPI app should not know how to load files or build
          DataFrames — that logic lives here. This also makes the
          predictor trivial to unit-test in isolation.
"""

from __future__ import annotations

import os
from typing import Any, Dict, List

import joblib
import numpy as np
import pandas as pd

# Sibling-module import for shared constants.
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import preprocess as pp  # noqa: E402

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_MODEL_PATH = os.path.join(PROJECT_ROOT, "models", "best_model.joblib")


class ChurnPredictor:
    """Loads the persisted sklearn Pipeline and predicts churn.

    The pipeline already contains the fitted ColumnTransformer, so we
    never have to scale incoming rows manually — exactly matching the
    training-time preprocessing (this is how we avoid train/serve skew).
    """

    def __init__(self, model_path: str = DEFAULT_MODEL_PATH) -> None:
        if not os.path.exists(model_path):
            raise FileNotFoundError(
                f"No trained model at {model_path}. "
                f"Train one first with: python -m src.train"
            )
        self.model_path = model_path
        self.pipeline = joblib.load(model_path)
        self.model_name = type(self.pipeline.named_steps["model"]).__name__

    def _to_dataframe(self, records: List[Dict[str, Any]]) -> pd.DataFrame:
        """Validate input records and return a DataFrame in feature order."""
        df = pd.DataFrame(records)
        # Reorder / select columns in the exact order the pipeline expects.
        missing = [c for c in pp.FEATURE_COLUMNS if c not in df.columns]
        if missing:
            raise ValueError(
                f"Missing required feature(s): {missing}. "
                f"Required: {pp.FEATURE_COLUMNS}"
            )
        return df[pp.FEATURE_COLUMNS]

    def predict(self, records: List[Dict[str, Any]]) -> List[int]:
        """Return binary churn predictions: 0 = stays, 1 = leaves."""
        df = self._to_dataframe(records)
        preds = self.pipeline.predict(df)
        return [int(p) for p in preds]

    def predict_proba(self, records: List[Dict[str, Any]]) -> List[float]:
        """Return churn probabilities (the model's confidence in class 1)."""
        df = self._to_dataframe(records)
        if not hasattr(self.pipeline, "predict_proba"):
            raise RuntimeError("Underlying model does not support predict_proba.")
        probas = self.pipeline.predict_proba(df)[:, 1]
        return [float(p) for p in probas]

    def predict_with_proba(self, records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Convenience: return both class and probability for each record."""
        df = self._to_dataframe(records)
        preds = self.pipeline.predict(df)
        probas = (
            self.pipeline.predict_proba(df)[:, 1]
            if hasattr(self.pipeline, "predict_proba")
            else np.zeros(len(df))
        )
        out = []
        for p, prob in zip(preds, probas):
            out.append({
                "prediction": int(p),
                "churn_probability": round(float(prob), 4),
                "label": "churn" if int(p) == 1 else "no_churn",
            })
        return out


# ---------------------------------------------------------------------------
# Quick CLI smoke test
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    predictor = ChurnPredictor()
    sample = [{
        "age": 45,
        "tenure": 5,
        "salary": 50000,
        "balance": 60000,
        "num_products": 2,
        "has_credit_card": 1,
        "is_active_member": 0,
        "gender": 1,
        "geography": 1,
    }]
    print("Loaded model:", predictor.model_name)
    print("Predictions :", predictor.predict_with_proba(sample))
