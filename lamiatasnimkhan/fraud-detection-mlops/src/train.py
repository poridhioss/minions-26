import mlflow
import mlflow.sklearn
import xgboost as xgb
from sklearn.metrics import classification_report, roc_auc_score, f1_score
from preprocess import load_and_preprocess
import joblib, os
from __future__ import annotations
from pathlib import Path
import pandas as pd
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler

DATA = Path("data/creditcard.csv")
ART  = Path("models"); ART.mkdir(exist_ok=True)
FEATS = ["Time", "Amount"] + [f"V{i}" for i in range(1, 29)]


def load() -> pd.DataFrame:
    df = pd.read_csv(DATA)
    df = df.drop_duplicates().reset_index(drop=True)
    return df


def split(df: pd.DataFrame):
    X = df[FEATS]; y = df["Class"]
    return train_test_split(X, y, test_size=0.2, stratify=y, random_state=42)


def fit_scaler(X_train: pd.DataFrame) -> StandardScaler:
    sc = StandardScaler().fit(X_train[["Time", "Amount"]])
    joblib.dump(sc, ART / "scaler.pkl")
    return sc


def transform(X: pd.DataFrame, sc: StandardScaler) -> pd.DataFrame:
    X = X.copy()
    X[["Time", "Amount"]] = sc.transform(X[["Time", "Amount"]])
    return X


def smote(X, y):
    from imblearn.over_sampling import SMOTE
    return SMOTE(random_state=42).fit_resample(X, y)


MLFLOW_URI = os.getenv("MLFLOW_TRACKING_URI", "http://localhost:5000")
mlflow.set_tracking_uri(MLFLOW_URI)
mlflow.set_experiment("fraud-detection")

def train(data_path: str = "data/raw/creditcard.csv"):
    df = load()
    X_train, X_test, y_train, y_test = split(df)
    scaler = fit_scaler(X_train)
    X_train = transform(X_train, scaler)
    X_test = transform(X_test, scaler)
    X_train, y_train = smote(X_train, y_train)

    params = {
        "n_estimators": 200,
        "max_depth": 6,
        "learning_rate": 0.1,
        "scale_pos_weight": 1,  # balanced after SMOTE
        "use_label_encoder": False,
        "eval_metric": "logloss",
        "random_state": 42,
    }

    with mlflow.start_run(run_name="xgboost-fraud-v1"):
        mlflow.log_params(params)

        model = xgb.XGBClassifier(**params)
        model.fit(X_train, y_train, eval_set=[(X_test, y_test)], verbose=50)

        y_pred = model.predict(X_test)
        y_prob = model.predict_proba(X_test)[:, 1]

        # Metrics
        roc_auc = roc_auc_score(y_test, y_prob)
        f1 = f1_score(y_test, y_pred)
        report = classification_report(y_test, y_pred, output_dict=True)

        mlflow.log_metric("roc_auc", roc_auc)
        mlflow.log_metric("f1_score", f1)
        mlflow.log_metric("precision", report["1"]["precision"])
        mlflow.log_metric("recall", report["1"]["recall"])

        # Log model
        mlflow.sklearn.log_model(model, "model", registered_model_name="FraudDetector")

        # Save locally too
        os.makedirs("models", exist_ok=True)
        joblib.dump(model, "models/model.pkl")

        print(f"\n✅ ROC-AUC: {roc_auc:.4f} | F1: {f1:.4f}")
        print(classification_report(y_test, y_pred))

if __name__ == "__main__":
    train()