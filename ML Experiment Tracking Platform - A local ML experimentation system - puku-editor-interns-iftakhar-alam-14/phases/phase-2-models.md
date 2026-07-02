# Phase 2 — Database Models (SQLAlchemy ORM)

## 🎯 What This Phase Did

Phase 2 defined **what our data looks like in the database**. We created two tables — `experiments` and `runs` — using SQLAlchemy's ORM (Object-Relational Mapping).

> 🧠 Think of it like drawing the **blueprint** of the two rooms in our house before building the walls (services) or the doors (API endpoints).

---

## 📂 What Was Created

```
backend/app/models/
├── __init__.py
├── experiment.py    ← The "experiments" table
└── run.py           ← The "runs" table
```

---

## ⭐ File 1: `backend/app/models/experiment.py`

This file defines the **experiments** table — one row per project (e.g. "house-prices", "sentiment-classifier").

```python
from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, DateTime
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from backend.app.database import Base


class Experiment(Base):
    """Represents the 'experiments' table in PostgreSQL."""

    __tablename__ = "experiments"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), unique=True, nullable=False, index=True)
    description = Column(Text, nullable=True)
    tags = Column(Text, nullable=True)                # JSON or comma-separated
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # One experiment → many runs
    runs = relationship("Run", back_populates="experiment", cascade="all, delete-orphan")
```

### Field-by-field

| Field | Type | Meaning |
|---|---|---|
| `id` | `Integer` | Auto-incrementing primary key (1, 2, 3, …) |
| `name` | `String(255)` | Unique name like `"house-prices"`. `unique=True` means no two experiments can share it. |
| `description` | `Text` | Long-form text. Nullable = optional. |
| `tags` | `Text` | Free-form labels (we'll store as JSON or comma-separated). |
| `created_at` | `DateTime` | Set automatically by PostgreSQL when the row is inserted. |
| `updated_at` | `DateTime` | Auto-updated by SQLAlchemy whenever the row changes. |
| `runs` | `relationship` | A Python shortcut to access all runs of this experiment (e.g. `my_exp.runs`). |

---

## ⭐ File 2: `backend/app/models/run.py`

This file defines the **runs** table — one row per training run. Multiple runs belong to one experiment.

```python
from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from backend.app.database import Base


class Run(Base):
    """Represents the 'runs' table in PostgreSQL."""

    __tablename__ = "runs"

    id = Column(Integer, primary_key=True, index=True)
    experiment_id = Column(Integer, ForeignKey("experiments.id", ondelete="CASCADE"), nullable=False, index=True)
    run_name = Column(String(255), nullable=True)
    status = Column(String(50), default="RUNNING", nullable=False)   # RUNNING | FINISHED | FAILED
    metrics = Column(Text, nullable=True)        # JSON: {"accuracy": 0.94}
    parameters = Column(Text, nullable=True)     # JSON: {"lr": 0.01}
    tags = Column(Text, nullable=True)           # JSON
    artifact_uri = Column(String(500), nullable=True)  # s3://bucket/.../model.pkl
    start_time = Column(DateTime(timezone=True), server_default=func.now())
    end_time = Column(DateTime(timezone=True), nullable=True)

    experiment = relationship("Experiment", back_populates="runs")
```

### Field-by-field

| Field | Type | Meaning |
|---|---|---|
| `id` | `Integer` | Primary key |
| `experiment_id` | `Integer` | Foreign key → `experiments.id`. **`ondelete="CASCADE"`** means: if the parent experiment is deleted, all its runs are deleted too. |
| `run_name` | `String(255)` | Human label, e.g. `"random-forest-v1"` |
| `status` | `String(50)` | One of `RUNNING` (in progress), `FINISHED` (done), `FAILED` (error) |
| `metrics` | `Text` | JSON string, e.g. `'{"accuracy": 0.94, "loss": 0.06}'` |
| `parameters` | `Text` | JSON string of hyperparameters, e.g. `'{"lr": 0.01, "n_estimators": 100}'` |
| `tags` | `Text` | JSON string of free-form labels |
| `artifact_uri` | `String(500)` | Where the trained model is stored (S3/MinIO path) |
| `start_time` | `DateTime` | Set automatically when created |
| `end_time` | `DateTime` | Set manually when training finishes (or fails) |

---

## 🗄️ The Resulting Database Schema

```
┌─────────────────────────────┐
│       experiments           │
├─────────────────────────────┤
│ id (PK)                     │
│ name (UNIQUE)               │
│ description                 │
│ tags                        │
│ created_at                  │
│ updated_at                  │
└──────────────┬──────────────┘
               │ 1
               │
               │ N
┌──────────────▼──────────────┐
│           runs              │
├─────────────────────────────┤
│ id (PK)                     │
│ experiment_id (FK) ────────►│  (ON DELETE CASCADE)
│ run_name                    │
│ status                      │
│ metrics (JSON)              │
│ parameters (JSON)           │
│ tags (JSON)                 │
│ artifact_uri                │
│ start_time                  │
│ end_time                    │
└─────────────────────────────┘
```

**Relationship:** One experiment has many runs. Deleting an experiment automatically deletes all its runs.

---

## 🧠 The Concepts You Should Understand

### 1. ORM = Object-Relational Mapping
Lets you work with **Python classes** instead of raw SQL:

```python
# Without ORM (raw SQL)
db.execute("INSERT INTO experiments (name) VALUES ('house-prices')")

# With ORM
exp = Experiment(name="house-prices")
db.add(exp)
db.commit()
```

Same result, but the ORM version is **type-checked**, **IDE-friendly**, and works with any database (Postgres, MySQL, SQLite…).

### 2. `Column` types
SQLAlchemy types map to PostgreSQL types:
- `Integer` → `INTEGER`
- `String(255)` → `VARCHAR(255)`
- `Text` → `TEXT` (unlimited length)
- `DateTime(timezone=True)` → `TIMESTAMPTZ` (timezone-aware)

### 3. `ForeignKey(..., ondelete="CASCADE")`
A **database-level rule**: if the parent row is deleted, child rows are deleted **automatically by PostgreSQL itself** (not by your Python code). Faster and more reliable than doing it in code.

### 4. `relationship` and `back_populates`
A Python shortcut that creates a two-way link between two classes:

```python
# Get all runs of an experiment
exp = db.query(Experiment).first()
for run in exp.runs:
    print(run.run_name)

# Get the parent experiment of a run
run = db.query(Run).first()
print(run.experiment.name)
```

Without `relationship`, you'd have to write `db.query(Run).filter(Run.experiment_id == exp.id)` manually every time.

### 5. JSON in a `Text` column
ML metrics and parameters are **arbitrary key-value pairs** — there's no way to make a column for every possible one. Storing as JSON gives full flexibility:

```python
# In Python
run.metrics = {"accuracy": 0.94, "loss": 0.06, "f1": 0.91}

# In PostgreSQL (stored as a string)
metrics = '{"accuracy": 0.94, "loss": 0.06, "f1": 0.91}'
```

We convert between dict ↔ JSON string in the **service layer** (Phase 4) so the rest of the code works with nice Python dicts.

---

## ✅ How to Verify Phase 2 Works

The models are just **definitions** — they don't actually create tables yet. To verify they parse correctly:

```python
>>> from backend.app.models.experiment import Experiment
>>> from backend.app.models.run import Run
>>> Experiment.__tablename__
'experiments'
>>> Run.__tablename__
'runs'
>>> Experiment.__table__.columns.keys()
['id', 'name', 'description', 'tags', 'created_at', 'updated_at']
```

To actually **create** the tables in PostgreSQL, you'd use `Base.metadata.create_all(engine)` (Alembic in Phase 8 will do this properly with migrations).

---

## 🧩 Where Phase 2 Fits in the Big Picture

```
[ Phase 1: skeleton ] ─► [ Phase 2: models ] ─► [ Phase 3: schemas ] ─► [ Phase 4: services ] ─► [ Phase 5: routers ]
        │                        │                       │                       │                       │
   "create the              "define tables         "validate input/      "write business         "expose URL
    folder & DB              that store              output shapes"        logic using             endpoints"
    connection"              our data"                                       these tables"
```

**Phase 2 = the data shape.** No business rules yet, no API yet — just a clear picture of what we're storing.

---

## 📋 Files Inventory

| File | Lines | Purpose |
|---|---|---|
| `backend/app/models/experiment.py` | ~25 | `Experiment` ORM class → `experiments` table |
| `backend/app/models/run.py` | ~30 | `Run` ORM class → `runs` table |

**Total: ~55 lines** defining 2 tables with 13 columns combined.
