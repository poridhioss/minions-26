import pandas as pd
import numpy as np
from sklearn.model_selection import train_test_split
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error, r2_score
import joblib

# Load dataset
df = pd.read_csv("housing.csv")

# Drop rows with missing values
df = df.dropna()

# Features and target
X = df.drop("median_house_value", axis=1)
X = pd.get_dummies(X)
y = df["median_house_value"]

# Split
X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)

# Train
model = RandomForestRegressor(n_estimators=100, random_state=42)
model.fit(X_train, y_train)

# Accuracy
predictions = model.predict(X_test)
mae = mean_absolute_error(y_test, predictions)
r2 = r2_score(y_test, predictions)
print(f"Mean Absolute Error: ${mae:,.2f}")
print(f"R2 Score: {r2:.4f}")

# Save
joblib.dump(model, "model.pkl")
joblib.dump(list(X.columns), "columns.pkl")
print("model.pkl saved!")