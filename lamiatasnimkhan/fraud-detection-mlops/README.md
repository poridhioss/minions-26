# 🛡️ FraudShield MLOps

End-to-end credit-card fraud detection built on the
[ULB creditcard.csv](https://www.kaggle.com/datasets/mlg-ulb/creditcardfraud)
dataset (284,807 transactions · 492 frauds · 30 PCA features), packaged as a
production-style MLOps stack with **FastAPI**, **XGBoost**, **MLflow** and
**Docker Compose** — plus a live ops dashboard in the browser.

> The dashboard you see in `app/index.html` is **also served by the same
> FastAPI process**, so the whole thing is one image and one port.

---

##  Highlights

| | |
|---|---|
| **Model** | XGBoost (200 trees, max_depth 6, lr 0.1) trained on SMOTE-resampled data |
| **ROC-AUC** | 0.9704 (test split, 56,964 transactions) |
| **Recall** | 0.7895 — catches ~79 % of frauds |
| **Precision** | 0.6637 — of everything flagged, ~66 % is actually fraud |
| **F1** | 0.7212 |
| **Serving** | FastAPI / uvicorn (`/predict`, `/health`) |
| **Registry** | MLflow model registry → `FraudDetector` (Production) |
| **Dashboard** | Real-time ops console, live prediction stream, confusion matrix, feature importance, SMOTE comparison, throughput chart |

---

## 🏗️ Architecture

```
                        ┌──────────────┐
                        │ creditcard.  │
                        │    csv       │  284,807 rows · 30 features
                        └──────┬───────┘
                               │
                               ▼
                      ┌────────────────┐
                      │     trainer    │   one-shot job
                      │ preprocess.py  │   dedup · scale · SMOTE
                      │   train.py     │   XGBoost fit
                      └────────┬───────┘
                               │  log params, metrics, model
                               ▼
                ┌──────────────────────────┐
                │          mlflow          │  ghcr.io/mlflow/mlflow:v2.13.0
                │      :5000  :5000        │  sqlite backend · ./mlruns
                └─────────────┬────────────┘
                              │  models:/FraudDetector/Production
                              ▼
                     ┌────────────────┐
                     │      api       │  FastAPI · uvicorn
                     │  /predict      │  POST TransactionFeatures → PredictionResponse
                     │  /health       │  GET
                     │  /             │  static dashboard (index.html + dashboard.js)
                     └────────┬───────┘
                              │  :8000
                              ▼
                       ┌──────────────┐
                       │   browser    │  live stream · charts · forms
                       └──────────────┘
```

Three services on a single bridge network (`mlops-net`), all defined in
[`docker-compose.yml`](docker-compose.yml).

---

## 📁 Project layout

```
fraud-detection-mlops/
├── app/                      FastAPI service + static dashboard
│   ├── __init__.py
│   ├── main.py               routes · /predict · /health · /
│   ├── predictor.py          MLflow-backed scoring (heuristic fallback)
│   ├── schemas.py            TransactionFeatures · PredictionResponse
│   ├── index.html            dashboard markup
│   ├── dashboard.js          live-stream simulator
│   └── style.css             dark-ops theme
├── src/                      training pipeline
│   ├── preprocess.py         dedup · StandardScaler · SMOTE
│   └── train.py              XGBoost + MLflow logging
├── data/                     creditcard.csv (gitignored — see below)
├── models/                   scaler.pkl, metrics.json (gitignored)
├── docker/
│   ├── Dockerfile.trainer
│   └── Dockerfile.api
├── docker-compose.yml
├── requirements.txt
├── .gitignore
└── README.md
```

---

## 🚀 Quick start

### 1. Get the data

Download `creditcard.csv` from
[Kaggle · mlg-ulb/creditcardfraud](https://www.kaggle.com/datasets/mlg-ulb/creditcardfraud)
and place it in `data/`:

```powershell
mkdir data
# copy or move the downloaded file to:
#   data/creditcard.csv
```

> `data/` is gitignored — the file is ~150 MB and not part of the repo.

### 2. Build & run the stack

```powershell
docker compose up --build mlflow
# wait until you see "Listening at: http://0.0.0.0:5000"

# in another shell
docker compose run --rm trainer
# logs: run=... metrics={'roc_auc': 0.97..., 'f1': ..., ...}

# now bring up the API
docker compose up --build api
```

### 3. Open the dashboard

| URL | What you'll see |
|---|---|
| <http://localhost:8000> | Live ops dashboard, simulated prediction stream, manual `POST /predict` form |
| <http://localhost:5000> | MLflow tracking UI — `fraud-detection` experiment, `FraudDetector` registered model |
| <http://localhost:8000/docs> | FastAPI auto-generated Swagger UI |
| `GET /health` | `{ "status": "ok", "model_loaded": true }` |

---

## 🔌 API

### `POST /predict`

Request — exactly matches `app/schemas.py:TransactionFeatures`:

```json
{
  "Time": 406,
  "Amount": 149.62,
  "V1": -1.36, "V2": 1.05,  "V3": -0.07, "V4":  0.89, "V5": -0.32,
  "V6": -0.14, "V7": -0.42, "V8":  0.16, "V9": -0.08, "V10": 0.51,
  "V11":-0.51, "V12":-0.62, "V13":-0.39, "V14":-0.93, "V15": 0.05,
  "V16": 0.39, "V17":-0.21, "V18": 0.07, "V19": 0.04, "V20": 0.21,
  "V21":-0.11, "V22": 0.06, "V23":-0.05, "V24":-0.21, "V25": 0.06,
  "V26":-0.05, "V27":-0.01, "V28": 0.04
}
```

Response — `PredictionResponse`:

```json
{
  "transaction_id": "3f2a91b7",
  "is_fraud": false,
  "fraud_probability": 0.0041,
  "risk_level": "LOW"
}
```

`risk_level` thresholds (in `app/main.py`):

| Probability | Risk | `is_fraud` |
|---|---|---|
| `p ≥ 0.60` | `HIGH`   | `true` |
| `0.25 ≤ p < 0.60` | `MEDIUM` | `true` |
| `p < 0.25` | `LOW`    | `false` |

### `GET /health`

```json
{ "status": "ok", "model_loaded": true }
```

`model_loaded` is `false` if MLflow was unreachable on startup — the API
falls back to a deterministic heuristic so it never 5xxs on boot.

---

## 🧪 Reproducing the reported numbers

```powershell
docker compose up -d mlflow
docker compose run --rm trainer
```

`trainer` will:
1. Load and dedup `data/creditcard.csv` (~284 k rows → ~283 k).
2. Split 80/20 stratified, seed 42.
3. `StandardScaler.fit` on `Time` & `Amount` of train → `models/scaler.pkl`.
4. SMOTE-oversample train to 50/50.
5. Fit `XGBClassifier(n_estimators=200, max_depth=6, lr=0.1, eval_metric="logloss")`.
6. Log params, metrics, and the model to MLflow under experiment `fraud-detection`,
   run name `xgboost-fraud-v1`, registered model name `FraudDetector`.
7. Write `models/metrics.json` with the four headline numbers.

The confusion-matrix numbers in the dashboard (`tn=56857 · fp=12 · fn=20 ·
tp=75`) are the output of that one run on the held-out 20 % test split, at
threshold 0.5.

---

## 🧠 Pipeline stages

| # | Stage | Module | What it does |
|---|---|---|---|
| 1 | **Data Source** | Kaggle · ULB | `creditcard.csv` (PCA-anonymised V1–V28 + Time + Amount + Class) |
| 2 | **Preprocess** | `src/preprocess.py` | drop duplicates · `StandardScaler` on Time/Amount · 80/20 stratified split · SMOTE on train only |
| 3 | **Train** | `src/train.py` | `XGBClassifier` (200 trees, depth 6, lr 0.1) |
| 4 | **Track & Register** | MLflow | log params + metrics · `mlflow.sklearn.log_model` with `registered_model_name="FraudDetector"` |
| 5 | **Serve** | `app/main.py` | FastAPI on `:8000` · loads `models:/FraudDetector/Production` |
| 6 | **Monitor** | `app/index.html` + `dashboard.js` | live stream, throughput chart, confusion matrix, manual predict form |

---

## 🖥️ The dashboard

The dashboard is served from `/` by the same FastAPI process, so a single
container gives you the API **and** the UI.

It has six sections:

1. **System Overview** — KPIs (totals, ROC-AUC, live TPS) + production confusion matrix + rolling throughput chart.
2. **MLOps Pipeline** — six horizontal stage cards with arrows, plus one detail card per stage.
3. **Model Performance** — conic-gradient metric rings (ROC-AUC, F1, Precision, Recall), feature-importance bar chart, before/after SMOTE class distribution.
4. **Live Inference** — auto-incrementing prediction feed + interactive `POST /predict` form with three named profiles (`Normal` / `Suspicious` / `High risk`).
5. **Service Topology** — the three services with ports, image references, and a working `cURL` example.
6. Footer with provenance.

The "live stream" is a **simulated** generator (`dashboard.js`) whose
scoring weights mirror the heuristic in `app/predictor.py` — that way the
dashboard stays useful even when the MLflow registry is empty or the API
is offline.

---

## ⚙️ Configuration

Environment variables (set in `docker-compose.yml`):

| Var | Default | Used by |
|---|---|---|
| `MLFLOW_TRACKING_URI` | `http://mlflow:5000` | `trainer`, `api` |

Hyperparameters (set in `src/train.py`):

| Param | Value | Why |
|---|---|---|
| `n_estimators` | `200` | good ROC-AUC vs training-time trade-off on this dataset |
| `max_depth` | `6` | shallow trees regularise well on tabular fraud data |
| `learning_rate` | `0.1` | XGBoost default, stable convergence |
| `eval_metric` | `logloss` | matches binary classification objective |
| `scale_pos_weight` | `1` | not needed — we SMOTE the train set instead |
| SMOTE | applied to train only | prevents leakage into the test split |

---

## 🛠️ Local development (without Docker)

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt

# in one shell
mlflow server --host 0.0.0.0 --port 5000 `
    --backend-store-uri sqlite:///mlflow.db `
    --default-artifact-root ./mlruns

# in another
$env:MLFLOW_TRACKING_URI = "http://localhost:5000"
python -m src.train
uvicorn app.main:app --reload --port 8000
```

---

## 📦 Tech stack

- **Python** 3.11
- **FastAPI** 0.111 + **Pydantic** 2.7
- **uvicorn** 0.30
- **scikit-learn** 1.5
- **XGBoost** 2.0
- **imbalanced-learn** 0.12 (SMOTE)
- **MLflow** 2.13
- **pandas** 2.2, **numpy** 1.26
- **Chart.js** 4.4 (dashboard)
- **@tabler/icons-webfont** (dashboard)

---

## 🧾 License

Dataset © ULB Machine Learning Group — used under the terms provided on
Kaggle. Code in this repository is released under the **MIT License**.

---

## ✍️ Author

FraudShield MLOps — a reference end-to-end MLOps project. Open an issue or
PR if you'd like to see drift detection, CI/CD, or a Kubernetes manifest.
