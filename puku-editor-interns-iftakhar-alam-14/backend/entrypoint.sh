#!/bin/sh
# ─────────────────────────────────────────────────────────────────────────
# entrypoint.sh
#
# Container start-up sequence for the ML Tracker backend.
#
#   1. Optionally wait for Postgres to be reachable (controlled by
#      WAIT_FOR_DB=true, default true). Useful in docker-compose where
#      the DB container may take a few seconds to start.
#   2. Run Alembic migrations: `alembic upgrade head`. This is the
#      production-correct way to bring the schema up to date.
#   3. exec the CMD (uvicorn by default). `exec` replaces the shell
#      process with uvicorn so it becomes PID 1 — important for clean
#      signal handling (SIGTERM from `docker stop` will reach uvicorn
#      and trigger its graceful-shutdown path).
# ─────────────────────────────────────────────────────────────────────────
set -e

# Resolve absolute paths from the script's own location, not $PWD.
SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
cd "$SCRIPT_DIR"

echo "▶ ML Tracker backend entrypoint"
echo "  Working dir: $SCRIPT_DIR"
echo "  DATABASE_URL=${DATABASE_URL%%@*}@***   (masked)"

# ─── 1. Wait for the database ──────────────────────────────────────────
if [ "${WAIT_FOR_DB:-true}" = "true" ]; then
    echo "▶ Waiting for database to accept connections..."

    # Derive a host:port from DATABASE_URL. We use a tiny Python snippet
    # instead of bash regex so it's robust to all SQLAlchemy URL forms.
    DB_TARGET=$(python - <<'PY'
import os
from urllib.parse import urlparse

url = os.environ.get("DATABASE_URL", "")
parsed = urlparse(url)
host = parsed.hostname or "localhost"
port = parsed.port or 5432
print(f"{host}:{port}")
PY
)

    DB_HOST=${DB_TARGET%:*}
    DB_PORT=${DB_TARGET#*:}

    # Try for up to ~60 seconds. We use a TCP probe via /dev/tcp so we
    # don't need extra tooling like `nc` or `psql` in the image.
    ATTEMPTS=0
    MAX_ATTEMPTS=30
    until python -c "
import socket, sys
s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.settimeout(2)
try:
    s.connect(('$DB_HOST', $DB_PORT))
finally:
    s.close()
" 2>/dev/null; do
        ATTEMPTS=$((ATTEMPTS + 1))
        if [ "$ATTEMPTS" -ge "$MAX_ATTEMPTS" ]; then
            echo "  ❌ Database not reachable after $MAX_ATTEMPTS attempts. Aborting."
            exit 1
        fi
        echo "  ...attempt $ATTEMPTS/$MAX_ATTEMPTS — retrying in 2s"
        sleep 2
    done
    echo "  ✅ Database is reachable at $DB_HOST:$DB_PORT"
fi

# ─── 2. Run migrations ─────────────────────────────────────────────────
if [ "${RUN_MIGRATIONS:-true}" = "true" ]; then
    echo "▶ Running Alembic migrations: alembic upgrade head"
    # `alembic.ini` lives in the same directory as this script.
    alembic upgrade head
    echo "  ✅ Migrations applied"
else
    echo "▶ Skipping migrations (RUN_MIGRATIONS=${RUN_MIGRATIONS})"
fi

# ─── 3. Hand off to the CMD ─────────────────────────────────────────────
echo "▶ Starting: $@"
exec "$@"
