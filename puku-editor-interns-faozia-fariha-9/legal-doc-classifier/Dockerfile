# Single-stage image. The PORT env var defaults to 8000 for local use;
# Hugging Face Spaces sets PORT=7860 and the same CMD picks it up.
FROM python:3.10-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8000

WORKDIR /app

# Install Python deps first so this layer caches across code changes.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the small app/ + index.html first. We add the (optional) saved_model/
# directory in a separate layer so HF Spaces builds (which don't have it)
# don't fail the COPY step. The build context must include a `saved_model/`
# folder even when empty; we ship `.gitkeep` for that case.
COPY app/ ./app/
COPY index.html ./index.html
COPY saved_model/ ./saved_model/

EXPOSE 8000 7860

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT}"]
