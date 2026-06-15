import pandas as pd
import numpy as np
from sklearn.preprocessing import StandardScaler
from imblearn.over_sampling import SMOTE
from sklearn.model_selection import train_test_split
import joblib, os

def load_and_preprocess(data_path: str, scaler_path: str = "models/scaler.pkl"):
    df = pd.read_csv(data_path)

    # Drop duplicates
    df.drop_duplicates(inplace=True)

    # Features & target
    X = df.drop(columns=["Class"])
    y = df["Class"]

    # Scale 'Amount' and 'Time' (V1-V28 are already PCA'd)
    scaler = StandardScaler()
    X[["Amount", "Time"]] = scaler.fit_transform(X[["Amount", "Time"]])

    # Save scaler for inference
    os.makedirs("models", exist_ok=True)
    joblib.dump(scaler, scaler_path)

    # Train/test split
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=y
    )

    # Handle class imbalance with SMOTE
    smote = SMOTE(random_state=42)
    X_train_res, y_train_res = smote.fit_resample(X_train, y_train)

    return X_train_res, X_test, y_train_res, y_test