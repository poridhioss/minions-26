FROM python:3.10-slim

WORKDIR /app

RUN pip install --no-cache-dir fastapi uvicorn scikit-learn joblib numpy pandas

COPY model.pkl .
COPY columns.pkl .
COPY main.py .
COPY housing.csv .

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]