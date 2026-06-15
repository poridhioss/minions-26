# ============================================================
#  Secure Python runtime for executing UNTRUSTED code
#  Built ONCE, used by the API on every execution.
# ============================================================
FROM python:3.12-alpine AS runtime

# Image metadata
LABEL org.opencontainers.image.title="python-runner-sandbox" \
      org.opencontainers.image.description="Minimal Python runtime for safely executing untrusted code" \
      org.opencontainers.image.licenses="MIT"

# ------------------------------------------------------------------
# 1. System hardening
# ------------------------------------------------------------------
# Disable pip cache, bytecode generation, and set a known timezone
ENV PIP_NO_CACHE_DIR=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONHASHSEED=random \
    PYTHONIOENCODING=utf-8

# ------------------------------------------------------------------
# 2. Create a non-root user with a fixed UID:GID
# ------------------------------------------------------------------
RUN addgroup -g 1000 -S runner && \
    adduser  -u 1000 -G runner -S -h /sandbox runner

# ------------------------------------------------------------------
# 3. Working directory that will be mounted read-only with a tmpfs
# ------------------------------------------------------------------
WORKDIR /sandbox
RUN chown runner:runner /sandbox

# ------------------------------------------------------------------
# 4. Switch to non-root user
# ------------------------------------------------------------------
USER 1000:1000

# ------------------------------------------------------------------
# 5. Entrypoint: just exec whatever args are passed in.
#    The API passes the script path explicitly so we don't need a
#    wrapper here.
# ------------------------------------------------------------------
ENTRYPOINT []
CMD ["python", "--version"]
