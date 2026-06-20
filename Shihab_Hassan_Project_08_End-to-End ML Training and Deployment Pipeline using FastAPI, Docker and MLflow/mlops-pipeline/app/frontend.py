"""
frontend.py
===========
Streamlit UI for the Customer Churn ML Pipeline.

What it does
------------
- Talks to the FastAPI backend (default: http://localhost:8000)
- Lets the user fill in a single customer's features and get a prediction
- Lets the user upload a CSV of customers and score them in batch
- Lets the user trigger a re-train of the model

Run
---
    streamlit run app/frontend.py
"""

from __future__ import annotations

import io
import os
import sys

import pandas as pd
import requests
import streamlit as st

# Make the project root importable so we can reuse the schemas for validation.
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from app import schemas  # noqa: E402

# ---------------------------------------------------------------------------
# Page setup
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="Customer Churn Predictor",
    page_icon="📊",
    layout="wide",
)

API_URL = os.environ.get("API_URL", "http://localhost:8000")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
@st.cache_data(ttl=10)
def check_health(base_url: str) -> dict:
    """GET /health — return the JSON body or a dict describing the failure."""
    try:
        r = requests.get(f"{base_url}/health", timeout=5)
        r.raise_for_status()
        return r.json()
    except Exception as e:  # noqa: BLE001 — surface every error to the user
        return {"status": "unreachable", "error": str(e)}


def post_predict(base_url: str, instances: list[dict]) -> tuple[dict | None, str | None]:
    """POST /predict — return (response_json, error_message)."""
    try:
        r = requests.post(
            f"{base_url}/predict",
            json={"instances": instances},
            timeout=30,
        )
        if r.status_code == 200:
            return r.json(), None
        # Try to extract FastAPI's structured error.
        try:
            detail = r.json().get("detail", r.text)
        except Exception:  # noqa: BLE001
            detail = r.text
        return None, f"HTTP {r.status_code}: {detail}"
    except requests.exceptions.RequestException as e:
        return None, f"Network error: {e}"


def post_train(base_url: str) -> tuple[dict | None, str | None]:
    """POST /train — return (response_json, error_message)."""
    try:
        r = requests.post(f"{base_url}/train", json={}, timeout=300)
        if r.status_code == 200:
            return r.json(), None
        try:
            detail = r.json().get("detail", r.text)
        except Exception:  # noqa: BLE001
            detail = r.text
        return None, f"HTTP {r.status_code}: {detail}"
    except requests.exceptions.RequestException as e:
        return None, f"Network error: {e}"


# ---------------------------------------------------------------------------
# Sidebar — API status + controls
# ---------------------------------------------------------------------------
with st.sidebar:
    st.header("⚙️ API Connection")
    api_input = st.text_input("API URL", value=API_URL, help="FastAPI backend URL")
    health = check_health(api_input)
    if health.get("status") == "ok" and health.get("model_loaded"):
        st.success(
            f"✅ Connected — model **{health.get('model_name', '?')}** loaded"
        )
    elif health.get("status") == "ok":
        st.warning("⚠️ Connected, but no model is loaded. Click 'Retrain' below.")
    else:
        st.error(
            f"❌ Cannot reach the API at `{api_input}`.\n\n"
            f"Make sure the backend is running:\n\n"
            f"`uvicorn app.main:app --host 0.0.0.0 --port 8000`\n\n"
            f"Error: {health.get('error', 'unknown')}"
        )

    st.divider()
    st.header("🔁 Retrain")
    st.caption("Re-runs training on the current `data/customer_churn.csv`.")
    if st.button("Retrain models", use_container_width=True):
        with st.spinner("Training both candidates — this may take a minute..."):
            summary, err = post_train(api_input)
        if err:
            st.error(f"Training failed: {err}")
        else:
            best = summary["best_model"]
            f1 = summary["best_metrics"]["f1"]
            st.success(
                f"✅ Best model: **{best}** (F1 = {f1:.3f})"
            )
            with st.expander("See all runs"):
                rows = [
                    {
                        "model": r["model"],
                        "f1": r["f1"],
                        "roc_auc": r["roc_auc"],
                        "run_id": r["run_id"],
                    }
                    for r in summary["all_runs"]
                ]
                st.dataframe(pd.DataFrame(rows), use_container_width=True)

    st.divider()
    st.caption("Backend ↔ this UI use HTTP/JSON. Open `http://localhost:8000/docs` for Swagger.")


# ---------------------------------------------------------------------------
# Main area
# ---------------------------------------------------------------------------
st.title("📊 Customer Churn Predictor")
st.caption(
    "Predict whether a bank customer is likely to leave. "
    "Backend: FastAPI · Model: Scikit-learn · Tracking: MLflow"
)

tab_single, tab_batch = st.tabs(["👤 Single customer", "📂 Batch (CSV)"])


# ---------------------------------------------------------------------------
# Tab 1 — single prediction
# ---------------------------------------------------------------------------
with tab_single:
    st.subheader("Enter customer details")

    # The form is laid out in 3 columns to keep it tidy.
    col1, col2, col3 = st.columns(3)
    with col1:
        age = st.number_input("Age", min_value=18, max_value=100, value=42, step=1)
        tenure = st.number_input(
            "Tenure (months)", min_value=0, max_value=72, value=6, step=1
        )
        salary = st.number_input(
            "Annual salary (USD)", min_value=0, max_value=500_000, value=55_000, step=1_000
        )
        balance = st.number_input(
            "Account balance (USD)", min_value=0, max_value=500_000, value=80_000, step=1_000
        )
    with col2:
        num_products = st.selectbox("Number of products", [1, 2, 3, 4], index=1)
        has_credit_card = st.checkbox("Has credit card", value=True)
        is_active_member = st.checkbox("Is an active member", value=True)
    with col3:
        gender_label = st.selectbox("Gender", ["Female", "Male"], index=1)
        geography_label = st.selectbox("Geography", ["France", "Germany", "Spain"], index=1)

    gender = 0 if gender_label == "Female" else 1
    geography = {"France": 0, "Germany": 1, "Spain": 2}[geography_label]
    has_credit_card_int = 1 if has_credit_card else 0
    is_active_member_int = 1 if is_active_member else 0

    payload = {
        "age": int(age),
        "tenure": int(tenure),
        "salary": float(salary),
        "balance": float(balance),
        "num_products": int(num_products),
        "has_credit_card": has_credit_card_int,
        "is_active_member": is_active_member_int,
        "gender": int(gender),
        "geography": int(geography),
    }

    # Validate against the Pydantic schema before sending. If it fails, the
    # validation error is shown right under the form.
    validation_error = None
    try:
        schemas.CustomerFeatures(**payload)
    except Exception as e:  # noqa: BLE001
        validation_error = str(e)

    st.divider()
    predict_clicked = st.button(
        "Predict churn", type="primary", use_container_width=True
    )

    if predict_clicked:
        if validation_error:
            st.error(f"Input validation failed: {validation_error}")
            st.stop()
        if health.get("model_loaded") is not True:
            st.error("Model is not loaded. Click **Retrain models** in the sidebar first.")
            st.stop()
        with st.spinner("Scoring..."):
            data, err = post_predict(api_input, [payload])
        if err:
            st.error(f"Prediction failed: {err}")
        else:
            item = data["predictions"][0]
            prob = item["churn_probability"]
            is_churn = item["prediction"] == 1
            model_name = data.get("model", "?")

            # Big visual result
            if is_churn:
                st.error(
                    f"## ⚠️ Likely to churn\n"
                    f"**Probability of churn: {prob:.1%}** "
                    f"(model: `{model_name}`)"
                )
            else:
                st.success(
                    f"## ✅ Likely to stay\n"
                    f"**Probability of staying: {(1 - prob):.1%}** "
                    f"(model: `{model_name}`)"
                )

            # A small progress bar makes the probability easy to read.
            st.progress(min(max(prob, 0.0), 1.0))
            st.caption(f"Threshold: 0.5 (churn if ≥ 0.5)")

            with st.expander("Raw response"):
                st.json(data)


# ---------------------------------------------------------------------------
# Tab 2 — batch prediction
# ---------------------------------------------------------------------------
with tab_batch:
    st.subheader("Score a CSV of customers")
    st.caption(
        "The CSV must contain all 9 feature columns: "
        "`age, tenure, salary, balance, num_products, has_credit_card, "
        "is_active_member, gender, geography`."
    )

    uploaded = st.file_uploader("Upload CSV", type=["csv"])

    if uploaded is not None:
        try:
            df = pd.read_csv(uploaded)
        except Exception as e:  # noqa: BLE001
            st.error(f"Could not read the CSV: {e}")
            st.stop()

        st.write(f"Loaded **{len(df)}** rows · columns: {list(df.columns)}")
        st.dataframe(df.head(), use_container_width=True)

        required = [
            "age", "tenure", "salary", "balance", "num_products",
            "has_credit_card", "is_active_member", "gender", "geography",
        ]
        missing = [c for c in required if c not in df.columns]
        if missing:
            st.error(f"Missing required columns: {missing}")
            st.stop()

        if st.button("Predict for all rows", type="primary", use_container_width=True):
            if health.get("model_loaded") is not True:
                st.error("Model is not loaded. Click **Retrain models** in the sidebar first.")
                st.stop()
            instances = df[required].to_dict(orient="records")
            with st.spinner(f"Scoring {len(instances)} customers..."):
                data, err = post_predict(api_input, instances)
            if err:
                st.error(f"Prediction failed: {err}")
            else:
                preds = data["predictions"]
                df_out = df.copy()
                df_out["churn_prediction"] = [p["prediction"] for p in preds]
                df_out["churn_probability"] = [p["churn_probability"] for p in preds]
                df_out["label"] = [p["label"] for p in preds]

                churn_rate = (df_out["churn_prediction"] == 1).mean()
                col_a, col_b, col_c = st.columns(3)
                col_a.metric("Total customers", len(df_out))
                col_b.metric("Predicted churners", int((df_out["churn_prediction"] == 1).sum()))
                col_c.metric("Predicted churn rate", f"{churn_rate:.1%}")

                st.dataframe(df_out, use_container_width=True)

                # Download button — useful for the demo.
                csv_buf = io.StringIO()
                df_out.to_csv(csv_buf, index=False)
                st.download_button(
                    "Download predictions as CSV",
                    data=csv_buf.getvalue(),
                    file_name="churn_predictions.csv",
                    mime="text/csv",
                    use_container_width=True,
                )
