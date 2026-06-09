from fastapi import FastAPI
from pydantic import BaseModel
from prometheus_fastapi_instrumentator import Instrumentator
import joblib
import numpy as np

app = FastAPI()

model = joblib.load("/model/model.pkl")

Instrumentator().instrument(app).expose(app)

class PredictRequest(BaseModel):
    features: list

@app.get("/health")
def health():
    return {"status": "ok"}

@app.post("/predict")
def predict(request: PredictRequest):
    data = np.array(request.features).reshape(1, -1)
    prediction = model.predict(data)
    return {"prediction": int(prediction[0])}