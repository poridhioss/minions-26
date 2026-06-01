from fastapi import FastAPI
from pydantic import BaseModel
import joblib
import numpy as np
import pandas as pd

app = FastAPI(title="House Price Predictor")

model = joblib.load("model.pkl")
columns = joblib.load("columns.pkl")

class HouseInput(BaseModel):
    longitude: float
    latitude: float
    housing_median_age: float
    total_rooms: float
    total_bedrooms: float
    population: float
    households: float
    median_income: float
    ocean_proximity: str

@app.get("/")
def home():
    return {"message": "House Price Prediction API is running!"}

@app.post("/predict")
def predict(house: HouseInput):
    data = pd.DataFrame([house.dict()])
    data = pd.get_dummies(data)
    data = data.reindex(columns=columns, fill_value=0)
    prediction = model.predict(data)[0]
    return {"predicted_house_price": f"${prediction:,.2f}"}