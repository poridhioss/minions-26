from __future__ import annotations
import joblib
import numpy as np
import pandas as pd
import os
import math
from typing import Any

class _HeuristicScorer:
    """Mirror of the weights used in app/dashboard.js for the simulator."""
    WEIGHTS = {
        "V14": -1.40, "V12": -1.05, "V10": -0.95, "V11": -0.70, "V4":  0.80,
        "V17":  0.65, "V3":  -0.55, "V7":  -0.50, "V16": 0.45, "V18": 0.40,
    }
    BIAS = -2.6

    def score(self, features: dict[str, float]) -> float:
        z = self.BIAS + sum(self.WEIGHTS[k] * features.get(k, 0.0) for k in self.WEIGHTS)
        return 1.0 / (1.0 + math.exp(-z))


class FraudPredictor:
    def __init__(self) -> None:
        self._model: Any | None = None
        self._fallback = _HeuristicScorer()
        try:
            import mlflow  # noqa: F401
            uri = os.getenv("MLFLOW_TRACKING_URI", "http://mlflow:5000")
            mlflow.set_tracking_uri(uri)
            self._model = mlflow.sklearn.load_model("models:/FraudDetector/Production")
        except Exception:
            self._model = None  # use heuristic fallback

        model_path = os.getenv("MODEL_PATH", "models/model.pkl")
        scaler_path = os.getenv("SCALER_PATH", "models/scaler.pkl")
        self.scaler = joblib.load(scaler_path)

    def predict(self, features: dict) -> tuple[bool, float, str]:
        if self._model is None:
            return self._fallback.score(features), 0.0, "HEURISTIC"

        df = pd.DataFrame([features])

        # Scale Amount and Time
        df[["Amount", "Time"]] = self.scaler.transform(df[["Amount", "Time"]])

        prob = self._model.predict_proba(df)[0][1]
        is_fraud = prob >= 0.5

        if prob < 0.3:
            risk = "LOW"
        elif prob < 0.6:
            risk = "MEDIUM"
        else:
            risk = "HIGH"

        return is_fraud, round(float(prob), 4), risk


predictor = FraudPredictor()