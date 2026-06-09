from fastapi.testclient import TestClient
import sys
sys.path.append("app")
from main import app

client = TestClient(app)

def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}

def test_predict():
    response = client.post("/predict", json={
        "features": [5.1, 3.5, 1.4, 0.2]
    })
    assert response.status_code == 200
    assert "prediction" in response.json()
