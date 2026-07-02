# mltracker — Python SDK

A small, typed client for the ML Experiment Tracking Platform API.

The SDK exposes the same 20 HTTP endpoints as the React frontend, but in idiomatic Python. It also provides a `Run` context manager that automates the "create → log → finish" lifecycle that every ML training script needs.

## Install

```bash
# From the repo root (editable install for local dev)
pip install -e ./sdk

# With dev/test extras
pip install -e "./sdk[dev]"
```

## Quick start

```python
import mltracker

mltracker.login(url="http://localhost:8000", api_key="dev-key-12345")

# Browse
print(mltracker.experiments.count())
print(mltracker.runs.list(limit=10))

# Train + log
exp = mltracker.experiments.create(name="iris-baseline", description="Random forest baseline")

with mltracker.run(experiment_id=exp.id, name="rf-v1") as run:
    run.log_param("n_estimators", 100)
    run.log_param("max_depth", 5)

    model = train_model()  # your code
    run.log_metric("accuracy", 0.94)
    run.log_metric("f1", 0.93)

# Predict
result = mltracker.predict(
    model_name="rf-v1",
    features=[5.1, 3.5, 1.4, 0.2],
)
print(result.predictions)
```

## Configuration

The SDK reads two environment variables if `login()` is not called:

| Variable | Default | Meaning |
|---|---|---|
| `MLTRACKER_URL` | `http://localhost:8000` | Base URL of the FastAPI backend. |
| `MLTRACKER_API_KEY` | — | API key sent as the `X-API-Key` header. |

```bash
export MLTRACKER_URL=http://mltracker.example.com
export MLTRACKER_API_KEY=...
python my_train.py
```

## See also

- `examples/train.py` — full end-to-end training + MLflow registration using the SDK.
- `examples/predict.py` — CLI predictor using the SDK.
- `tests/` — pytest suite that exercises the SDK against a `TestClient`.
- `phases/phase-12-sdk.md` — the design notes and rationale.
