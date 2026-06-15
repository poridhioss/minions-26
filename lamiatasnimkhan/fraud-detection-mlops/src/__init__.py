from __future__ import annotations
import json
from pathlib import Path

import mlflow
import mlflow.sklearn
from xgboost import XGBClassifier
from sklearn.metrics import roc_auc_score, f1_score, precision_score, recall_score

from preprocess import load, split, fit_scaler, transform, smote, ART

EXPERIMENT = "fraud-detection"
MODEL_NAME = "FraudDetector"


def main() -> None:
    mlflow.set_tracking_uri("http://mlflow:5000")
    mlflow.set_experiment(EXPERIMENT)

    df = load()
    X_tr, X_te, y_tr, y_te = split(df)
    sc = fit_scaler(X_tr)
    X_tr = transform(X_tr, sc); X_te = transform(X_te, sc)
    X_tr, y_tr = smote(X_tr, y_tr)

    params = dict(n_estimators=200, max_depth=6, learning_rate=0.1,
                  eval_metric="logloss", n_jobs=-1, random_state=42)

    with mlflow.start_run(run_name="xgboost-fraud-v1") as run:
        mlflow.log_params(params)
        clf = XGBClassifier(**params).fit(X_tr, y_tr)
        p_te = clf.predict_proba(X_te)[:, 1]
        yhat = (p_te >= 0.5).astype(int)

        metrics = dict(
            roc_auc=roc_auc_score(y_te, p_te),
            f1=f1_score(y_te, yhat),
            precision=precision_score(y_te, yhat),
            recall=recall_score(y_te, yhat),
        )
        mlflow.log_metrics(metrics)

        mlflow.sklearn.log_model(clf, "model",
                                 registered_model_name=MODEL_NAME)
        (ART / "metrics.json").write_text(json.dumps(metrics, indent=2))
        print(f"run={run.info.run_id}  metrics={metrics}")


if __name__ == "__main__":
    main()