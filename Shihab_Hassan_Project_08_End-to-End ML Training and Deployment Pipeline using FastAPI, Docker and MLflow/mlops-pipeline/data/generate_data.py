"""
generate_data.py
================
Purpose : Generate a realistic synthetic Customer Churn dataset.
Why     : The rest of the pipeline needs a CSV to train on. Using a
          generator keeps the project self-contained (no external
          download) while producing meaningful features that a real
          churn model would use.

Output  : ../data/customer_churn.csv
          (relative to this file: mlops-pipeline/data/customer_churn.csv)
"""

import os
import numpy as np
import pandas as pd

# Reproducibility — same dataset every time the script is run.
RANDOM_STATE = 42
NUM_CUSTOMERS = 2000


def generate_churn_dataset(n_samples: int = NUM_CUSTOMERS,
                           random_state: int = RANDOM_STATE) -> pd.DataFrame:
    """
    Build a synthetic churn dataset with realistic feature distributions.

    Features
    --------
    age              : int   - Customer age (18-70)
    tenure           : int   - Months as a customer (0-72)
    salary           : float - Annual salary in USD
    balance          : float - Account balance in USD
    num_products     : int   - Number of bank products (1-4)
    has_credit_card  : int   - 0/1
    is_active_member : int   - 0/1
    gender           : int   - 0 = Female, 1 = Male
    geography        : int   - 0 = France, 1 = Germany, 2 = Spain
    churn            : int   - TARGET (0 = stays, 1 = leaves)
    """
    rng = np.random.default_rng(random_state)

    # --- Generate base features ---
    # Use explicit numpy integer dtypes for NumPy 2.x compatibility
    # (np.int / np.float aliases were removed in NumPy 2.0).
    age = rng.integers(low=18, high=71, size=n_samples, dtype=np.int64)
    tenure = rng.integers(low=0, high=73, size=n_samples, dtype=np.int64)
    salary = np.round(rng.normal(loc=60000, scale=20000, size=n_samples).clip(15000, 200000), 2)
    balance = np.round(rng.normal(loc=75000, scale=30000, size=n_samples).clip(0, 250000), 2)
    num_products = rng.integers(low=1, high=5, size=n_samples, dtype=np.int64)
    has_credit_card = rng.integers(low=0, high=2, size=n_samples, dtype=np.int64)
    is_active_member = rng.integers(low=0, high=2, size=n_samples, dtype=np.int64)
    gender = rng.integers(low=0, high=2, size=n_samples, dtype=np.int64)
    geography = rng.integers(low=0, high=3, size=n_samples, dtype=np.int64)

    # --- Generate churn label using a logistic rule ---
    # Higher age, more products, low activity and German customers
    # tend to churn more in this synthetic setup.
    logit = (
        -2.0
        + 0.02 * (age - 40)
        - 0.01 * (tenure - 20)
        + 0.4 * (num_products - 1.5)
        - 1.2 * is_active_member
        - 0.000005 * (balance)
        + 0.5 * (geography == 1).astype(int)
        + 0.3 * (gender == 0).astype(int)
    )
    prob = 1.0 / (1.0 + np.exp(-logit))
    churn = (rng.random(n_samples) < prob).astype(np.int64)

    df = pd.DataFrame({
        "age": age,
        "tenure": tenure,
        "salary": salary,
        "balance": balance,
        "num_products": num_products,
        "has_credit_card": has_credit_card,
        "is_active_member": is_active_member,
        "gender": gender,
        "geography": geography,
        "churn": churn,
    })
    return df


def main() -> None:
    """Generate the CSV in ./customer_churn.csv (this script's folder)."""
    here = os.path.dirname(os.path.abspath(__file__))
    out_path = os.path.join(here, "customer_churn.csv")

    # Make sure the destination directory exists (it should — we are in it).
    os.makedirs(here, exist_ok=True)

    df = generate_churn_dataset()
    df.to_csv(out_path, index=False)
    print(f"[OK] Generated {len(df)} rows -> {out_path}")
    print(f"[OK] Churn rate: {df['churn'].mean():.2%}")


if __name__ == "__main__":
    try:
        main()
    except PermissionError:
        # Most common cause: the CSV is open in Excel / a viewer and
        # Windows refuses to overwrite it. Give a clear hint.
        print(
            "[ERROR] Could not write customer_churn.csv.\n"
            "         Close the file in Excel/any viewer and try again."
        )
        raise
