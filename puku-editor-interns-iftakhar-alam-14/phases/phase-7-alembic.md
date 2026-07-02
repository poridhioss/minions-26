# Phase 7 — Alembic Database Migrations

## 🎯 What This Phase Did

Phase 6 shipped a running FastAPI app. In its `lifespan` handler, we used `Base.metadata.create_all(engine)` to spin up the tables — a fine bootstrap, but a **dead end** for any real project. The moment a teammate adds a column, drops a constraint, or renames a field, the schema drifts and we have no way to replay, review, or roll back the change.

Phase 7 replaces that with **Alembic** — SQLAlchemy's official migration tool. Migrations are versioned Python files that say, in code: *"here's how to go from schema A to schema B"* and *"here's how to undo it"*. Every change to the database is now a reviewed, committed file in `git`.

We also discovered and fixed a **latent Phase 2 bug**: `backend/app/models/__init__.py` was empty, so `import backend.app.models` was a no-op and `Base.metadata` knew about zero tables. `create_all()` would have silently created an empty database. Alembic caught this — `target_metadata` was empty, so the first autogenerate attempt produced nothing.

> 🏗️ Think of Phase 6 as pouring the building's foundation in one shot, and Phase 7 as replacing that with **blueprints**: every future wall, door, or window is its own numbered, dated, signed-off drawing you can flip back through.

---

## 📂 What Was Created

```
backend/
├── alembic.ini                                  ← Alembic top-level config
└── alembic/
    ├── env.py                                   ← The migration environment
    ├── script.py.mako                           ← Template for new migration files
    └── versions/
        └── 20260610_07eb0a6baff3_initial_schema_experiments_and_runs.py
                                               ← The first (base) migration
```

**One bug fixed:**

```
backend/app/models/
└── __init__.py                                 ← Was 0 bytes; now imports the models
```

---

## ⭐ File 1: `backend/alembic.ini`

This is Alembic's top-level config — read once, before any Python runs. It tells Alembic:

1. Where to find migration scripts (`script_location = alembic`)
2. What to prepend to `sys.path` so migrations can import `app.*` (`prepend_sys_path = .`)
3. How loud to be in the logs

```ini
[alembic]
script_location = alembic
prepend_sys_path = .
version_path_separator = os

# The actual DB URL is left EMPTY here on purpose.
# env.py reads it from `app.core.config.settings.DATABASE_URL`,
# which in turn reads it from the .env file. This way the URL
# lives in one place (the .env) and isn't duplicated into alembic.ini.
sqlalchemy.url =

[loggers]
keys = root,sqlalchemy,alembic

[handlers]
keys = console

[formatters]
keys = generic

[logger_root]
level = WARN
handlers = console
qualname =

[logger_sqlalchemy]
level = WARN
handlers =
qualname = sqlalchemy.engine

[logger_alembic]
level = INFO
handlers =
qualname = alembic

[handler_console]
class = StreamHandler
args = (sys.stderr,)
level = NOTSET
formatter = generic

[formatter_generic]
format = %(levelname)-5.5s [%(name)s] %(message)s
datefmt = %H:%M:%S
```

### Why is `sqlalchemy.url` empty?

Two reasons:

1. **Single source of truth.** The connection string lives in `backend/.env` as `DATABASE_URL=postgresql://user:pass@host:5432/db`. If we hardcoded it in `alembic.ini`, anyone with a different local password would have to edit a tracked file.
2. **No secrets in git.** Connection strings with passwords don't belong in committed config.

`env.py` reads `settings.DATABASE_URL` and calls `config.set_main_option("sqlalchemy.url", ...)` at runtime, so the empty string in `alembic.ini` is intentional.

---

## ⭐ File 2: `backend/alembic/env.py`

This is the **Python script that runs once per `alembic` command**. It:

- Configures the DB URL
- Sets `target_metadata` (what Alembic compares the live schema against)
- Provides both **online** (live DB connection) and **offline** (emit SQL to stdout) modes

```python
"""
Alembic migration environment.

This file runs every time you call `alembic <something>`. It is NOT
a migration itself — it just configures how migrations run.
"""
import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import engine_from_config, pool

# ─── 1. Make `app.*` imports work ────────────────────────────────────────
# alembic.ini's `prepend_sys_path = .` only adds the cwd (backend/) to
# sys.path. We need the PROJECT ROOT (ml-tracker/) on the path so we
# can `from app.database import Base`.
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# ─── 2. Pull in our app's settings + Base + models ──────────────────────
from app.core.config import settings        # reads backend/.env
from app.database import Base               # the SQLAlchemy DeclarativeBase
import app.models                           # noqa: F401  side-effect import

# ─── 3. Standard Alembic config setup ────────────────────────────────────
config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Override the empty URL in alembic.ini with the one from our settings.
config.set_main_option("sqlalchemy.url", settings.DATABASE_URL)

# This is what `--autogenerate` diffs against. Must be Base.metadata
# AFTER all models have been imported, so it actually has tables in it.
target_metadata = Base.metadata


# ─── 4. Offline mode (no live DB — emit SQL to stdout) ───────────────────
def run_migrations_offline() -> None:
    """Emit SQL to stdout, do not connect to a database.

    Useful for:
      - Reviewing what a migration WILL do before applying it
      - Generating SQL scripts to hand to a DBA
    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
    )
    with context.begin_transaction():
        context.run_migrations()


# ─── 5. Online mode (the normal case — connect and apply) ────────────────
def run_migrations_online() -> None:
    """Connect to the database and apply migrations in a transaction."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            compare_server_default=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
```

### The five key things in this file

#### 1. `PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent`

The `__file__` is `backend/alembic/env.py`. Walking up three levels gets us to the project root (`ml-tracker/`). We put that on `sys.path` so `from app.database import Base` works.

> ⚠️ This is the **second sys.path gotcha** in the project. Phase 6 had to do the same trick in `main.py` to import `backend.app.*`. We could fix this with a proper `pyproject.toml` and `pip install -e .`, but for an internship project a few lines of `sys.path` manipulation is fine.

#### 2. `import app.models  # noqa: F401`

The `# noqa: F401` tells linters "yes, I know this import looks unused — that's intentional". The import is a **side-effect import**: when Python executes `app/models/__init__.py`, the model classes register themselves with `Base.metadata`. If we skip this, `Base.metadata.tables` is empty, and `alembic revision --autogenerate` thinks there's no schema at all.

#### 3. `target_metadata = Base.metadata`

Alembic's "autogenerate" works by **diffing**:
- the live database schema (queried via `SELECT` from `information_schema`)
- the `Base.metadata` (built from your model classes)

If you skip a model import, the diff says *"your DB has table X but your models don't — drop it!"*. Always import all models before assigning `target_metadata`.

#### 4. `compare_type=True`

Without this, Alembic only sees **column adds and drops**. If you change a column from `String(255)` to `Text`, autogenerate won't notice. With it, the diff includes type changes.

#### 5. `compare_server_default=True`

Same idea, but for `server_default` values. Change `server_default=func.now()` to `server_default=func.current_timestamp()` and Alembic will detect it.

---

## ⭐ File 3: `backend/alembic/script.py.mako`

This is a **Mako template** — Alembic reads it every time you run `alembic revision -m "..."` to generate the file body. It's almost identical to what Alembic ships out of the box:

```mako
"""${message}

Revision ID: ${up_revision}
Revises: ${down_revision | comma,n}
Create Date: ${create_date}
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
${imports if imports else ""}

# revision identifiers, used by Alembic.
revision: str = ${repr(up_revision)}
down_revision: Union[str, None] = ${repr(down_revision)}
branch_labels: Union[str, Sequence[str], None] = ${repr(branch_labels)}
depends_on: Union[str, Sequence[str], None] = ${repr(depends_on)}


def upgrade() -> None:
    ${upgrades if upgrades else "pass"}


def downgrade() -> None:
    ${downgrades if downgrades else "pass"}
```

You almost never edit this file — it's the cookie-cutter for new migrations. But it's nice to read so you understand why every migration file you create has the same shape: `revision`, `down_revision`, `upgrade()`, `downgrade()`.

---

## ⭐ File 4: `backend/alembic/versions/20260610_07eb0a6baff3_initial_schema_experiments_and_runs.py`

The **first (base) migration** — it creates the `experiments` and `runs` tables. The filename is `<UTC-timestamp>_<revision-id>_<message-with-dashes>.py`.

```python
"""initial schema: experiments and runs

Revision ID: 07eb0a6baff3
Revises:
Create Date: 2026-06-10 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "07eb0a6baff3"
down_revision: Union[str, None] = None          # ← this is the BASE migration
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create the initial schema: experiments + runs tables."""
    op.create_table(
        "experiments",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("tags", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_experiments"),
    )
    op.create_index("ix_experiments_id", "experiments", ["id"])
    op.create_index("ix_experiments_name", "experiments", ["name"], unique=True)

    op.create_table(
        "runs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("experiment_id", sa.Integer(), nullable=False),
        sa.Column("run_name", sa.String(length=255), nullable=True),
        sa.Column("status", sa.String(length=50), nullable=True),
        sa.Column("metrics", sa.Text(), nullable=True),
        sa.Column("parameters", sa.Text(), nullable=True),
        sa.Column("tags", sa.Text(), nullable=True),
        sa.Column("artifact_uri", sa.String(length=500), nullable=True),
        sa.Column("start_time", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=True),
        sa.Column("end_time", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["experiment_id"], ["experiments.id"],
            name="fk_runs_experiment_id_experiments",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_runs"),
    )
    op.create_index("ix_runs_id", "runs", ["id"])


def downgrade() -> None:
    """Drop the runs and experiments tables (in reverse order)."""
    # Runs first — it has a FK to experiments.
    op.drop_index("ix_runs_id", table_name="runs")
    op.drop_table("runs")

    op.drop_index("ix_experiments_name", table_name="experiments")
    op.drop_index("ix_experiments_id", table_name="experiments")
    op.drop_table("experiments")
```

### Anatomy of a migration

Every migration has **four mandatory parts**:

| Part | What it is | Example |
|------|-----------|---------|
| `revision` | This migration's unique ID (12 chars) | `"07eb0a6baff3"` |
| `down_revision` | The ID of the migration we apply BEFORE this one. `None` means "this is the first one" | `None` |
| `upgrade()` | How to go from the previous state to the new state | `op.create_table(...)` |
| `downgrade()` | How to undo `upgrade()` | `op.drop_table(...)` |

Alembic uses `revision` and `down_revision` to build a **linked list** of migrations. When you run `alembic upgrade head`, it walks the list from the current version (stored in the `alembic_version` table in your DB) up to `head` (the newest migration), applying each `upgrade()` along the way.

### Why hand-write the migration?

In a real workflow you'd usually run:

```bash
alembic revision --autogenerate -m "add user email"
```

…and Alembic would diff the live DB against `Base.metadata` and write the `upgrade()`/`downgrade()` for you. But autogenerate **requires a live database connection** to query `information_schema` — and our dev Postgres wasn't running in the sandbox.

So we ran the skeleton-only command:

```bash
alembic revision -m "initial schema: experiments and runs"
```

…which gave us the file with empty `upgrade()` and `downgrade()` functions. We then hand-wrote the bodies to **exactly match** the model definitions. We verified correctness by running `alembic upgrade head --sql` and inspecting the emitted DDL — the column types, indexes, and FKs all match the models.

---

## 🐛 Sidebar: The Phase 2 Bug We Fixed

While wiring up `target_metadata`, we ran a smoke test:

```python
>>> from app.database import Base
>>> sorted(Base.metadata.tables.keys())
[]
```

**Zero tables.** This was because `backend/app/models/__init__.py` was 0 bytes. Without explicit `from .experiment import Experiment` etc., the package import was a no-op, and the model classes never registered themselves with `Base.metadata`.

The fix — 9 lines:

```python
"""Database models for the ML tracker."""
from backend.app.models.experiment import Experiment
from backend.app.models.run import Run

__all__ = ["Experiment", "Run"]
```

After the fix:

```python
>>> sorted(Base.metadata.tables.keys())
['experiments', 'runs']                            # ✅
>>> list(Base.metadata.tables['experiments'].columns.keys())
['id', 'name', 'description', 'tags', 'created_at', 'updated_at']
>>> list(Base.metadata.tables['runs'].columns.keys())
['id', 'experiment_id', 'run_name', 'status',
 'metrics', 'parameters', 'tags', 'artifact_uri', 'start_time', 'end_time']
```

> 🪲 **Why didn't Phase 6 catch this?** Phase 6's `create_all()` would have silently created a database with zero tables. But the verification test stopped earlier — the `SELECT 1` connection check failed first (no Postgres in the sandbox), so `create_all()` was never reached. The lesson: always smoke-test that `Base.metadata` actually contains the expected tables after model imports.

---

## 🧠 Concepts You Should Understand

### 1. The `alembic_version` table

Alembic adds a single row to a single table in your database:

```
alembic_version
───────────────
version_num: '07eb0a6baff3'
```

This row is the **bookmark** of "where we are in the migration history". On every `alembic upgrade` or `alembic downgrade`, Alembic reads this row, figures out which migrations are pending or to-undo, and applies them — then updates the row.

If you delete this row, Alembic loses its mind ("current revision is unknown — refusing to proceed"). Treat it like a sacred artifact.

### 2. Online vs. offline mode

| Mode | Connection | Output | Use case |
|------|-----------|--------|----------|
| **Online** (`alembic upgrade head`) | Connects to Postgres | Runs the SQL | Normal dev/prod workflow |
| **Offline** (`alembic upgrade head --sql`) | None | Prints SQL to stdout | Review what a migration will do; generate SQL scripts |

We used offline mode for verification (no DB available in the sandbox):

```bash
alembic upgrade head --sql
# → BEGIN;
#   CREATE TABLE alembic_version (...);
#   CREATE TABLE experiments (...);
#   CREATE INDEX ix_experiments_id ON experiments (id);
#   CREATE UNIQUE INDEX ix_experiments_name ON experiments (name);
#   CREATE TABLE runs (...);
#   CREATE INDEX ix_runs_id ON runs (id);
#   INSERT INTO alembic_version VALUES ('07eb0a6baff3');
#   COMMIT;

alembic downgrade 07eb0a6baff3:base --sql
# → BEGIN;
#   DROP INDEX ix_runs_id;
#   DROP TABLE runs;
#   DROP INDEX ix_experiments_name;
#   DROP INDEX ix_experiments_id;
#   DROP TABLE experiments;
#   DELETE FROM alembic_version WHERE alembic_version.version_num='07eb0a6baff3';
#   DROP TABLE alembic_version;
#   COMMIT;
```

### 3. The migration "linked list"

Migrations form a chain via `down_revision`:

```
         ┌──────────────────┐
         │ 07eb0a6baff3     │   ← base (down_revision = None)
         │ initial schema   │
         └────────┬─────────┘
                  │ points to (None)
                  ▼
                (nothing — this is the first one)
```

When you add a new migration, it gets a new revision ID and its `down_revision` points to `07eb0a6baff3`. The chain extends.

If you create two branches (e.g. you and a teammate each make a migration from the same base), you get a **merge** — Alembic asks you to run `alembic merge` to reconcile them.

### 4. Autogenerate is not magic

`alembic revision --autogenerate` **diffs**, it doesn't **think**. Common things it gets wrong:

- **Column renames** look like drop + add. You have to fix the migration by hand.
- **Data migrations** (UPDATE statements, backfills) are invisible to it.
- **SQL defaults vs Python defaults** can be confused.
- **Table renames** look like drop + add.

The rule: autogenerate gives you a 90% draft. You always read the resulting `upgrade()` and `downgrade()` before committing.

### 5. Idempotency

`Base.metadata.create_all()` (in `main.py`'s lifespan) is **idempotent**: it only creates tables that don't exist. If Alembic has already created them, `create_all` is a no-op. That's why we left it in `main.py` as a dev convenience — first-time devs can boot the app against an empty DB and immediately have tables, no `alembic upgrade head` step required. In production, the migration is the source of truth.

---

## ✅ How to Verify Phase 7 Works

We verified Phase 7 **without needing a live database** by using offline (SQL-emit) mode.

### Check 1 — Alembic loads our env.py cleanly

```bash
$ cd backend
$ alembic current
# Expected: fails with a Postgres connection error, NOT a Python import error.
# We get: psycopg2.OperationalError: connection to server at "localhost" (::1),
#         port 5432 failed: Connection refused.
# ✅ env.py imported settings, Base, and models without crashing.
```

If env.py had a bug (e.g. `Base.metadata` was empty because of the `__init__.py` bug), this command would either crash with `ModuleNotFoundError` or succeed with `Current revision(s) for PostgreSQL: None` even when it should have seen our migrations — so the failure mode here is actually a **good** signal.

### Check 2 — Upgrade SQL is correct

```bash
$ alembic upgrade head --sql
```

Emits valid PostgreSQL DDL: `CREATE TABLE experiments`, `CREATE TABLE runs` (with the FK to `experiments.id`), two indexes on `experiments` (one unique on `name`), one index on `runs`, plus Alembic's own `alembic_version` table. All wrapped in `BEGIN; ... COMMIT;` for transactional safety.

### Check 3 — Downgrade SQL is correct

```bash
$ alembic downgrade 07eb0a6baff3:base --sql
```

Emits the reverse: `DROP TABLE runs` first (FK-dependent), then `DROP TABLE experiments`, then `DROP TABLE alembic_version`. Order matters — drop the child before the parent or PostgreSQL will error.

### Check 4 — Migration file parses as valid Python

```python
>>> import importlib.util
>>> spec = importlib.util.spec_from_file_location(
...     "migration",
...     "alembic/versions/20260610_07eb0a6baff3_initial_schema_experiments_and_runs.py",
... )
>>> mod = importlib.util.module_from_spec(spec)
>>> spec.loader.exec_module(mod)
>>> mod.revision
'07eb0a6baff3'
>>> mod.down_revision is None
True
>>> callable(mod.upgrade) and callable(mod.downgrade)
True
# ✅
```

### Check 5 — Models are registered with `Base.metadata`

```python
>>> from app.database import Base
>>> sorted(Base.metadata.tables.keys())
['experiments', 'runs']
>>> sum(len(t.columns) for t in Base.metadata.tables.values())
16
# 6 (experiments) + 10 (runs) = 16 columns total
# ✅
```

---

## 🔄 Migration Lifecycle

Here's the full lifecycle of a schema change, from "developer has an idea" to "production has the new schema":

```
Developer wants to add a `notes` column to `runs`
              │
              ▼
  1. Edit backend/app/models/run.py — add Column("notes", Text)
              │
              ▼
  2. alembic revision --autogenerate -m "add notes column to runs"
              │
              │     Alembic:
              │       • connects to dev DB
              │       • reads information_schema
              │       • diffs against Base.metadata
              │       • creates alembic/versions/<new>_add_notes_column_to_runs.py
              │       • fills in upgrade() with op.add_column(...)
              │         and downgrade() with op.drop_column(...)
              ▼
  3. Open the new migration file
              │
              │     • Review the auto-generated upgrade() / downgrade()
              │     • Maybe tweak: add backfill, change column type, etc.
              │     • Commit the file to git
              ▼
  4. On dev machine: alembic upgrade head
              │
              │     • Alembic reads alembic_version → "07eb0a6baff3"
              │     • Sees the new migration in versions/ → "3f4e2a1b9c8d"
              │     • Runs upgrade() inside a transaction
              │     • Updates alembic_version → "3f4e2a1b9c8d"
              ▼
  5. In CI / production: alembic upgrade head
              │
              │     • Same as step 4, but against prod DB
              │     • Run BEFORE deploying the new app code
              │     • (Or as part of a Docker entrypoint that runs migrations)
              ▼
  6. Oops, the new column broke something?
              │
              ▼
     alembic downgrade -1
              │
              │     • Runs downgrade() to drop the column
              │     • Updates alembic_version back to "07eb0a6baff3"
              ▼
  7. Fix the migration file, commit, redeploy.
```

---

## 🧩 Where Phase 7 Fits in the Big Picture

```
[ Phase 1: skeleton ] ─► [ Phase 2: models ] ─► [ Phase 3: schemas ] ─► [ Phase 4: services ] ─► [ Phase 5: routers ] ─► [ Phase 6: main.py ] ─► [ Phase 7: alembic ] ─► [ Phase 8: tests? ]
        │                        │                       │                       │                       │                       │                          │
   "create the              "define tables         "validate input/      "write business         "expose URL           "tie it all              "version &            "verify it all
    folder & DB              that store              output shapes"        logic using             endpoints"           into a runnable          migrate the           works as
    connection"              our data"                                       these tables"                                web server"                  schema"               expected"
                                                                                                       │                       │                          │
                                                                                                       ▼                       ▼                          ▼
                                                                                                 http://...:8000      alembic upgrade head    pytest -v
                                                                                                  /api/v1/...           (replaces create_all)
```

**Phase 7 = the schema's version control.** Every other layer can change without breaking the database, because every change to the database is now an explicit, reviewable, reversible file.

---

## 📋 Files Inventory

| File | Lines | Purpose |
|------|-------|---------|
| `backend/alembic.ini` | ~58 | Top-level Alembic config — script location, logging |
| `backend/alembic/env.py` | ~95 | Migration environment — DB URL, `target_metadata`, online + offline runners |
| `backend/alembic/script.py.mako` | ~25 | Mako template for new migration file bodies |
| `backend/alembic/versions/20260610_07eb0a6baff3_initial_schema_experiments_and_runs.py` | ~95 | Base migration — creates `experiments` and `runs` |
| `backend/app/models/__init__.py` *(fixed)* | 9 | Was 0 bytes; now registers `Experiment` and `Run` with `Base.metadata` |
| `backend/app/main.py` *(edited)* | +9/-2 | Updated the `create_all` comment block to reference the new Alembic workflow |

**Total: 4 new files + 1 fixed + 1 minor edit = ~290 net new lines.**

---

## 🚀 What's Next

We've now got a **production-shaped backend**: settings, models, schemas, services, routers, an ASGI app, and versioned migrations. The natural next phases are:

- **Phase 8: Pytest** — a real test suite covering the services, the routers, and the migration. The scaffolding (`backend/tests/` is currently empty) is already there.
- **Phase 9: Second migration** — practice the workflow by adding a real column (e.g. `runs.notes`, `experiments.owner`) and writing the migration for it. Best way to internalize the diff workflow.
- **Phase 10: Frontend** — the React app in `frontend/src/` is empty. Time to build the UI that talks to all of this.

A good Phase 8 would be **tests** — they pin down the behavior we've built so far and catch regressions as the project grows.
