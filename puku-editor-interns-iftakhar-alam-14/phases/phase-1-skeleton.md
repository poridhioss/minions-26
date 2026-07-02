# Phase 1 — Project Skeleton & Database Connection

## 🎯 What This Phase Did

Phase 1 set up the **empty bones** of the project — the folders, files, and a working database connection. No business logic yet. Just the structure that every later phase will plug into.

Think of it like pouring the **foundation** of a house before building any walls.

---

## 📂 What Was Created

```
ml-tracker/
├── backend/
│   ├── requirements.txt            ← List of Python packages we need
│   ├── alembic/                    ← (empty for now, used in Phase 8)
│   │   └── versions/
│   ├── app/
│   │   ├── __init__.py             ← Makes "app" a Python package
│   │   ├── database.py             ← The DB connection engine ⭐
│   │   ├── core/__init__.py        ← Makes "core" a Python package
│   │   ├── models/__init__.py      ← Makes "models" a Python package
│   │   ├── routers/__init__.py     ← Makes "routers" a Python package
│   │   ├── schemas/__init__.py     ← Makes "schemas" a Python package
│   │   └── services/__init__.py    ← Makes "services" a Python package
│   ├── ml/                         ← (empty for now, used in Phase 7)
│   └── tests/                      ← (empty for now, used in Phase 10)
├── frontend/                       ← (empty, used in Phase 11)
├── nginx/                          ← (empty, used in Phase 9)
└── sdk/
    └── mltracker/                  ← (empty, used in Phase 12)
```

Plus a virtual environment at `venv/` with all packages installed.

---

## ⭐ The Star File: `backend/app/database.py`

This is the **only file with real logic** in Phase 1. Everything else is just empty folders with `__init__.py` markers.

```python
import os
from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

# Load variables from the .env file at the project root into os.environ
load_dotenv()

# Read the connection string, e.g. "postgresql://user:pass@localhost:5432/mltracker"
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://mluser:mlpassword@localhost:5432/mltracker")

# The engine is the "thing that talks to PostgreSQL"
engine = create_engine(DATABASE_URL, echo=True, future=True)

# A factory that creates new DB sessions on demand
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# All model classes will inherit from this Base
Base = declarative_base()


# FastAPI dependency: gives each request its own DB session, closes it after
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
```

### What each piece does

| Line / Block | Why it exists |
|---|---|
| `load_dotenv()` | Reads the `.env` file at project root and puts the variables into `os.environ` so Python can read them. |
| `os.getenv("DATABASE_URL", ...)` | The **default value** (after the comma) is a fallback if the env var isn't set. |
| `create_engine(...)` | Creates a **connection pool** to PostgreSQL. `echo=True` logs every SQL query to the terminal (helpful for learning, off in production). |
| `sessionmaker(...)` | A **factory** for sessions. A session is like a "transaction window" — you do queries through it. |
| `declarative_base()` | Returns a `Base` class. All ORM models (Phase 2) will inherit from this so SQLAlchemy can track them. |
| `get_db()` | A **generator** used by FastAPI. For every API request, it opens a session, lets the endpoint use it, then closes it — even if an error happens. |

---

## 🧠 The Concepts You Should Understand

### 1. Virtual Environment (`venv/`)
A **separate, isolated Python installation** for this project only. So when we install `fastapi`, it doesn't affect other Python projects on your computer.

```bash
python -m venv venv              # create it
source venv/bin/activate          # turn it on (Linux/Mac)
pip install -r backend/requirements.txt  # install packages
```

### 2. `__init__.py` files
A Python file that says "**this folder is a package, not just a random folder**". It can be **completely empty** — its mere presence is what matters. Without it, you can't do `from backend.app.database import ...`.

### 3. The `.env` file
A plain text file at the project root that holds **secrets and config** that shouldn't be hardcoded:

```dotenv
DATABASE_URL=postgresql://mluser:mlpassword@localhost:5432/mltracker
```

> ⚠️ Never commit `.env` to Git. We add it to `.gitignore`.

### 4. SQLAlchemy `engine` vs `Session`
- **Engine** = the **plumbing** to the database. Created **once** at startup, lives forever.
- **Session** = a **short-lived workspace**. You open one, run queries, commit/rollback, close it. FastAPI gives every request its own session.

---

## ✅ How to Verify Phase 1 Works

After this phase, the only thing you can do is confirm the engine can be imported and the connection string is read:

```python
>>> from backend.app.database import engine, DATABASE_URL
>>> print(DATABASE_URL)
postgresql://mluser:mlpassword@localhost:5432/mltracker
>>> print(engine)
Engine(postgresql://mluser:mlpassword@localhost:5432/mltracker)
```

You won't be able to **actually connect** to a database yet unless PostgreSQL is running. That's fine — the structure is in place.

---

## 🧩 Where Phase 1 Fits in the Big Picture

```
[ Phase 1: skeleton ] ─► [ Phase 2: models ] ─► [ Phase 5: services ] ─► [ Phase 6: routers ]
        │                        │                       │                       │
   "create the              "define tables         "write functions       "expose them as
    folder & DB              that store              that use those         URL endpoints
    connection"              our data"               tables"                people can hit"
```

Phase 1 is the **scaffolding**. Without it, nothing else has a place to live.

---

## 📋 Files Inventory

| File | Lines | Purpose |
|---|---|---|
| `backend/app/__init__.py` | 0 | Package marker |
| `backend/app/database.py` | ~25 | Engine, session, `get_db` |
| `backend/app/core/__init__.py` | 0 | Package marker |
| `backend/app/models/__init__.py` | 0 | Package marker |
| `backend/app/routers/__init__.py` | 0 | Package marker |
| `backend/app/schemas/__init__.py` | 0 | Package marker |
| `backend/app/services/__init__.py` | 0 | Package marker |
| `backend/requirements.txt` | ~15 | Python dependencies |
| `.env` | ~10 | Secrets & config |

**Total: ~60 lines of real code** (the rest are empty `__init__.py`).
