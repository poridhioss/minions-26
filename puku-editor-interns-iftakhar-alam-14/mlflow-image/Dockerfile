# Custom MLflow image that includes psycopg2-binary for talking to Postgres.
# The upstream `ghcr.io/mlflow/mlflow` image doesn't ship psycopg2, so when
# we point MLflow at a Postgres backend-store it crashes on startup with
# `ModuleNotFoundError: No module named 'psycopg2'`.
FROM ghcr.io/mlflow/mlflow:v2.22.0

USER root

# psycopg2-binary is a self-contained wheel (no libpq dev headers needed)
RUN pip install --no-cache-dir psycopg2-binary==2.9.12 boto3==1.43.22

# The upstream image runs as root, not a `mlflow` user. Leave as root.