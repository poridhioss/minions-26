# ─── Stage 1: build dependencies in a throw-away image ─────────────────
# We split "install deps" from "copy code" so Docker can cache the deps
# layer. As long as requirements.txt is unchanged, re-builds skip pip.
FROM python:3.12-slim AS builder

# Don't write .pyc files, flush stdout/stderr immediately (so logs show up
# in `docker logs` without buffering), and skip interactive prompts.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Install build deps for psycopg2-binary + greenlet (small native modules).
# We use --no-install-recommends to keep the image lean.
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        libpq-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /install
# Copy ONLY requirements.txt first so the install layer is cache-stable.
COPY requirements.txt .
RUN pip install --prefix=/install/deps --no-warn-script-location -r requirements.txt


# ─── Stage 2: lean runtime image ────────────────────────────────────────
FROM python:3.12-slim AS runtime

# Same env vars as the builder so behavior is consistent at runtime.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    # Make `python -m backend.app.main` work without setting PYTHONPATH.
    PYTHONPATH=/app

# libpq5 is the runtime client for Postgres. We don't need the dev headers
# in the final image — only the shared lib.
RUN apt-get update && apt-get install -y --no-install-recommends \
        libpq5 \
        curl \
    && rm -rf /var/lib/apt/lists/*

# Copy the prebuilt Python packages from the builder.
COPY --from=builder /install/deps /usr/local

# Create a non-root user to run the app. The official python image already
# has a `nonroot` user with uid 65532, but we make our own for clarity.
RUN groupadd --system --gid 1001 mltracker && \
    useradd --system --uid 1001 --gid mltracker --create-home --shell /bin/bash mltracker

WORKDIR /app

# Copy project source. The .dockerignore keeps venv/, tests/_tmp/, mlruns/,
# __pycache__/ etc. out of the image.
COPY --chown=mltracker:mltracker . /app

# Make the entrypoint script executable.
RUN chmod +x /app/entrypoint.sh

USER mltracker

EXPOSE 8000

# Lightweight healthcheck — `curl /health` (no auth required).
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl --fail --silent http://localhost:8000/health || exit 1

# entrypoint.sh: waits for the DB, runs alembic upgrade head, then execs
# uvicorn. CMD is the default args; entrypoint can override.
ENTRYPOINT ["/app/entrypoint.sh"]
CMD ["uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "8000"]
