# =============================================================================
# Dockerfile for the Customer Churn ML Pipeline
# =============================================================================
# Build :  docker build -t ml-pipeline .
# Run   :  docker run -p 8000:8000 ml-pipeline
# Docs  :  http://localhost:8000/docs
# =============================================================================

# ----- 1. Base image ---------------------------------------------------------
# Slim keeps the image small; Python 3.11 is the current sweet spot for ML libs.
FROM python:3.11-slim

# ----- 2. Environment hygiene ------------------------------------------------
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# ----- 3. Working directory ---------------------------------------------------
WORKDIR /app

# ----- 4. System deps (only if your libs need any) ---------------------------
# scikit-learn + numpy wheels are self-contained on slim, so no extra apt
# packages are required. Add `RUN apt-get update && apt-get install -y ...`
# here if you switch to packages that need compiled extensions (e.g. lightgbm).

# ----- 5. Python dependencies (cached layer) ----------------------------------
# Copy ONLY requirements first so Docker reuses this layer when source changes.
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# ----- 6. Application code ----------------------------------------------------
COPY app/      ./app/
COPY src/      ./src/
COPY data/     ./data/
COPY models/   ./models/
COPY mlruns/   ./mlruns/

# ----- 7. Health check (optional but nice) ------------------------------------
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request, sys; \
sys.exit(0 if urllib.request.urlopen('http://localhost:8000/health', timeout=3).status == 200 else 1)"

# ----- 8. Expose + launch -----------------------------------------------------
EXPOSE 8000

# uvicorn with 1 worker is fine for a demo; bump --workers for real traffic.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
