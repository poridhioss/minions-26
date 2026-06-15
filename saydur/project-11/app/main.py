from fastapi import FastAPI
from pydantic import BaseModel
import joblib
import numpy as np
import os

app = FastAPI()

model = None

def load_model():
    global model
    model_path = "model/model.pkl"
    if os.path.exists(model_path):
        model = joblib.load(model_path)

load_model()

class PredictRequest(BaseModel):
    features: list

@app.get("/health")
def health():
    return {"status": "ok"}

@app.post("/predict")
def predict(request: PredictRequest):
    if model is None:
        return {"error": "Model not loaded"}
    data = np.array(request.features).reshape(1, -1)
    prediction = model.predict(data)
    return {"prediction": int(prediction[0])}
