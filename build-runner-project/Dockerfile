# Python base for both the FastAPI server and the worker
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONDONTWRITEBYTECODE=1

# git for `git clone`, docker-cli so the worker can drive the host daemon
RUN apt-get update \
    && apt-get install -y --no-install-recommends git curl ca-certificates \
    && curl -fsSL https://download.docker.com/linux/static/stable/x86_64/docker-27.4.0.tgz \
       | tar -xz -C /tmp && mv /tmp/docker/docker /usr/local/bin/docker \
       && rm -rf /tmp/docker \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Run as non-root when possible (the worker still needs the docker socket,
# which is mounted by docker-compose with appropriate perms).
RUN useradd -m -u 1000 runner || true
USER runner

EXPOSE 8000

# default command runs the API; worker overrides this in compose
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]