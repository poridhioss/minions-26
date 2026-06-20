"""
preprocess.py
=============
Purpose : All data preparation logic for the churn pipeline.
Why     : Keeping preprocessing in one place means the same exact
          transformations are applied at training time AND at
          prediction time — this is critical to avoid train/serve skew.

Public functions
----------------
- load_data(csv_path)        : load the raw CSV as a pandas DataFrame
- clean_data(df)             : drop nulls, fix dtypes, basic sanity checks
- split_features_target(df)  : separate X (features) and y (target)
- get_train_test_split(...)  : stratified train/test split
- get_preprocessor()         : build a sklearn ColumnTransformer
- preprocess_for_training(...) : end-to-end training preparation
- preprocess_for_inference(df, scaler): scale new rows the same way
"""

from __future__ import annotations

import os
from typing import Tuple

import joblib
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

# ---------------------------------------------------------------------------
# Constants — single source of truth for column names and file locations.
# Changing these here propagates everywhere; never hard-code column names
# inside other files.
# ---------------------------------------------------------------------------
DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
MODELS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "models")
DEFAULT_CSV = os.path.join(DATA_DIR, "customer_churn.csv")

TARGET_COLUMN = "churn"

# All features the model uses. Order matters: keep it stable so the
# saved scaler/model always receives columns in the same order.
FEATURE_COLUMNS: list[str] = [
    "age",
    "tenure",
    "salary",
    "balance",
    "num_products",
    "has_credit_card",
    "is_active_member",
    "gender",
    "geography",
]

# Numeric vs categorical splits. Useful for building a ColumnTransformer
# that does scaling on numeric columns and leaves binary/encoded ones alone.
NUMERIC_COLUMNS: list[str] = [
    "age",
    "tenure",
    "salary",
    "balance",
    "num_products",
]
CATEGORICAL_COLUMNS: list[str] = [
    "has_credit_card",
    "is_active_member",
    "gender",
    "geography",
]


def load_data(csv_path: str = DEFAULT_CSV) -> pd.DataFrame:
    """Load the churn CSV into a DataFrame.

    Why a wrapper?
        Centralizes the file path and lets us add validation later
        (e.g. schema checks with pandera) in one place.
    """
    if not os.path.exists(csv_path):
        raise FileNotFoundError(
            f"Dataset not found at {csv_path}. "
            f"Run `python data/generate_data.py` to create it."
        )
    return pd.read_csv(csv_path)


def clean_data(df: pd.DataFrame) -> pd.DataFrame:
    """Apply minimal cleaning: drop duplicates, ensure numeric dtypes.

    Why minimal?
        Our synthetic data is already clean; in a real project this is
        where you would handle missing values, outliers, and type fixes.
    """
    df = df.copy()
    df = df.drop_duplicates().reset_index(drop=True)

    # Coerce every expected column to numeric; bad rows become NaN
    # and are then dropped (defensive — useful for real-world CSVs).
    for col in FEATURE_COLUMNS + [TARGET_COLUMN]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.dropna().reset_index(drop=True)
    return df


def split_features_target(df: pd.DataFrame) -> Tuple[pd.DataFrame, pd.Series]:
    """Return (X, y) using the global feature/target column names."""
    X = df[FEATURE_COLUMNS].copy()
    y = df[TARGET_COLUMN].astype(int)
    return X, y


def get_train_test_split(
    X: pd.DataFrame,
    y: pd.Series,
    test_size: float = 0.2,
    random_state: int = 42,
):
    """Stratified split so class balance is preserved in train and test.

    stratify=y is important because the dataset is imbalanced (~11% churn).
    """
    return train_test_split(
        X, y, test_size=test_size, random_state=random_state, stratify=y
    )


def get_preprocessor() -> ColumnTransformer:
    """Build the sklearn preprocessing pipeline.

    - Numeric features  -> StandardScaler (mean 0, std 1)
    - Binary/categorical -> passed through unchanged

    A ColumnTransformer is the cleanest way to keep these steps in a
    single fitted object that can be reused at inference time.
    """
    numeric_pipeline = Pipeline(steps=[
        ("scaler", StandardScaler()),
    ])
    preprocessor = ColumnTransformer(
        transformers=[
            ("num", numeric_pipeline, NUMERIC_COLUMNS),
            ("cat", "passthrough", CATEGORICAL_COLUMNS),
        ],
        remainder="drop",  # safety: drop anything we didn't list
    )
    return preprocessor


def preprocess_for_training(
    csv_path: str = DEFAULT_CSV,
    test_size: float = 0.2,
    random_state: int = 42,
):
    """All-in-one helper used by the training script.

    Returns
    -------
    X_train, X_test, y_train, y_test, preprocessor
    """
    df = load_data(csv_path)
    df = clean_data(df)
    X, y = split_features_target(df)
    X_train, X_test, y_train, y_test = get_train_test_split(
        X, y, test_size=test_size, random_state=random_state
    )
    preprocessor = get_preprocessor()
    return X_train, X_test, y_train, y_test, preprocessor


def transform_with(preprocessor: ColumnTransformer, X: pd.DataFrame):
    """Fit/transform helper used by training (fit) and inference (transform)."""
    return preprocessor.transform(X)


def save_preprocessor(preprocessor: ColumnTransformer,
                      path: str | None = None) -> str:
    """Persist the fitted preprocessor so inference can reproduce scaling."""
    if path is None:
        path = os.path.join(MODELS_DIR, "preprocessor.joblib")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    joblib.dump(preprocessor, path)
    return path


def load_preprocessor(path: str | None = None) -> ColumnTransformer:
    """Load a previously fitted preprocessor from disk."""
    if path is None:
        path = os.path.join(MODELS_DIR, "preprocessor.joblib")
    return joblib.load(path)


if __name__ == "__main__":
    # Quick sanity check when running this file directly.
    X_train, X_test, y_train, y_test, _ = preprocess_for_training()
    print(f"[OK] Train shape: {X_train.shape}, Test shape: {X_test.shape}")
    print(f"[OK] Train churn rate: {y_train.mean():.2%}")
    print(f"[OK] Test  churn rate: {y_test.mean():.2%}")
