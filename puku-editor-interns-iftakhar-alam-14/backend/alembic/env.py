"""
Alembic migration environment.

This is the file alembic actually executes when you run
``alembic upgrade head`` or ``alembic revision --autogenerate``.

Its job is to:
1. Configure the SQLAlchemy URL (from our app's settings).
2. Set ``target_metadata`` to the Base.metadata of our models
   so that --autogenerate can diff the live schema vs. the models.
3. Run migrations in online mode (real connection) or offline
   mode (emit SQL without connecting — useful for review).

Note on imports: this file is executed by alembic with the
``backend/`` directory as cwd (because ``script_location = alembic``
is relative to ``backend/alembic.ini``). To import the project's
``app`` package, we add the parent of ``backend/`` to ``sys.path``
at runtime. The imports below therefore use the *plain* ``app.*``
path, not ``backend.app.*``.
"""

import os
import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import engine_from_config, pool

# ─── Make ``app`` importable ──────────────────────────────────────────
# The alembic.ini lives in backend/, and env.py runs with backend/ as
# cwd. Our project root is one level up. Adding it to sys.path lets
# us write ``from app.database import Base`` instead of
# ``from backend.app.database import Base``.
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# ─── Project imports ──────────────────────────────────────────────────
# These imports are critical: they register our models with Base.metadata
# so that autogenerate can see them.
from app.core.config import settings      # noqa: E402
from app.database import Base             # noqa: E402
import app.models                         # noqa: E402,F401  (side-effect import to register models)

# ─── Alembic Config object ────────────────────────────────────────────
# `config` is the in-memory representation of alembic.ini.
# We override sqlalchemy.url with the value from our app settings
# so the URL is read from .env (not hardcoded into alembic.ini).
config = context.config

# Override the URL — pulls from .env via pydantic-settings
config.set_main_option("sqlalchemy.url", settings.DATABASE_URL)

# Configure logging from alembic.ini
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# ─── target_metadata ──────────────────────────────────────────────────
# This is what autogenerate compares against. It MUST be the
# Base.metadata that your models are registered with.
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """
    Emit SQL to stdout without connecting to a database.
    Useful for:
      - Reviewing what migration would do
      - Generating SQL scripts for DBAs who manage prod
    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        # Compare types so e.g. VARCHAR(255) → TEXT is detected
        compare_type=True,
        # Compare server defaults
        compare_server_default=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """
    Connect to the database and apply migrations.
    This is the normal mode for dev/staging/prod.
    """
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            # Compare types so e.g. VARCHAR(255) → TEXT is detected
            compare_type=True,
            # Compare server defaults
            compare_server_default=True,
            # Include schema name in migration (None = default schema)
            include_schemas=False,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
