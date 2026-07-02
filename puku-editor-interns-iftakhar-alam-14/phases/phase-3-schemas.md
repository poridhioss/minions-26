# Phase 3 — API Schemas (Pydantic Validation)

## 🎯 What This Phase Did

Phase 3 created the **shapes of data that travel in and out of the API**. These are NOT database tables — they're **validation contracts** that say "the client must send JSON that looks exactly like THIS, and we'll only return JSON shaped like THAT."

> 🧠 Think of schemas as the **forms you fill out at a government office**: blank fields you must complete, with rules about what's valid. The form is NOT your data — it's just the format for getting data in and out.

---

## 📂 What Was Created

```
backend/app/schemas/
├── __init__.py
├── experiment.py    ← ExperimentCreate, ExperimentUpdate, ExperimentResponse
└── run.py           ← RunCreate, RunUpdate, RunResponse
```

---

## ⭐ File 1: `backend/app/schemas/experiment.py`

```python
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field, ConfigDict


class ExperimentBase(BaseModel):
    """Shared fields used by create/read schemas."""
    name: str = Field(..., min_length=1, max_length=255, description="Unique experiment name")
    description: Optional[str] = Field(None, description="What this experiment is about")
    tags: Optional[str] = Field(None, description="Free-form tags (comma-separated or JSON string)")


class ExperimentCreate(ExperimentBase):
    """Schema used when creating a new experiment via POST /experiments."""
    pass


class ExperimentUpdate(BaseModel):
    """Schema used when partially updating an experiment via PATCH /experiments/{id}."""
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None
    tags: Optional[str] = None


class ExperimentResponse(ExperimentBase):
    """Schema used when returning an experiment to the client."""
    id: int
    created_at: datetime
    updated_at: Optional[datetime] = None

    # Allows Pydantic to read data directly from a SQLAlchemy ORM object
    model_config = ConfigDict(from_attributes=True)
```

### The 4 schemas, explained

| Schema | Used for | Required fields | Why this shape |
|---|---|---|---|
| `ExperimentBase` | A **shared parent** — DRY principle | `name` | Holds the 3 fields every experiment has. |
| `ExperimentCreate` | `POST /experiments` (creating) | `name`, plus optional others | Inherits from `Base` — same fields. Used as the body of the create endpoint. |
| `ExperimentUpdate` | `PATCH /experiments/{id}` (updating) | All optional | User might update just the description, so all fields must be optional. |
| `ExperimentResponse` | The **response** we return | `id`, `created_at` included | Includes server-generated fields the client never sends (id, timestamps). |

The key line is `model_config = ConfigDict(from_attributes=True)`. It tells Pydantic: "if someone hands you a SQLAlchemy ORM object (which has its fields as class attributes, not dict keys), still figure out how to read it." This is what lets us write:

```python
return ExperimentResponse.model_validate(db_experiment)  # works because of from_attributes
```

---

## ⭐ File 2: `backend/app/schemas/run.py`

```python
from datetime import datetime
from typing import Optional, Dict, Any
from pydantic import BaseModel, Field, ConfigDict


class RunBase(BaseModel):
    """Shared fields used by create/read schemas."""
    run_name: Optional[str] = Field(None, max_length=255)
    status: Optional[str] = Field("RUNNING", description="RUNNING | FINISHED | FAILED")
    artifact_uri: Optional[str] = Field(None, max_length=500)


class RunCreate(RunBase):
    """Schema used when creating a new run via POST /runs."""
    experiment_id: int = Field(..., description="ID of the parent experiment")
    metrics: Optional[Dict[str, Any]] = Field(None, description="Key-value metrics, e.g. {'accuracy': 0.95}")
    parameters: Optional[Dict[str, Any]] = Field(None, description="Hyperparameters used")
    tags: Optional[Dict[str, Any]] = Field(None, description="Arbitrary tags for the run")


class RunUpdate(BaseModel):
    """Schema used when updating a run (e.g. marking it FINISHED)."""
    run_name: Optional[str] = None
    status: Optional[str] = None
    end_time: Optional[datetime] = None
    metrics: Optional[Dict[str, Any]] = None
    parameters: Optional[Dict[str, Any]] = None
    tags: Optional[Dict[str, Any]] = None
    artifact_uri: Optional[str] = None


class RunResponse(RunBase):
    """Schema used when returning a run to the client."""
    id: int
    experiment_id: int
    metrics: Optional[Dict[str, Any]] = None
    parameters: Optional[Dict[str, Any]] = None
    tags: Optional[Dict[str, Any]] = None
    start_time: datetime
    end_time: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)
```

### The same 4-schema pattern, with one important difference

The Run schemas use `Dict[str, Any]` for metrics/parameters/tags because **ML metrics are arbitrary key-value pairs**:

```json
{
  "metrics": {
    "accuracy": 0.94,
    "loss": 0.06,
    "f1_score": 0.91,
    "per_class": {"cat": 0.95, "dog": 0.93}
  }
}
```

You can put **anything** in there. Pydantic doesn't enforce specific keys, just that the value is valid JSON.

---

## 🧠 The Concepts You Should Understand

### 1. Schemas ≠ Models

| | Schema (Pydantic) | Model (SQLAlchemy) |
|---|---|---|
| Purpose | Validate API input/output | Define DB table structure |
| Lives in | `app/schemas/` | `app/models/` |
| Used by | Routers (HTTP layer) | Services (data layer) |
| Example | `ExperimentCreate` | `Experiment` |
| Magic | `Field(..., min_length=1)` | `Column(String(255), unique=True)` |

**The rule of thumb:** a schema is what the **outside world** sees; a model is what **our database** stores.

### 2. `Field(...)` syntax
The `...` (Ellipsis) means **"this field is required"**:

```python
name: str = Field(..., min_length=1, max_length=255)
#      ^^^ required   ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^ validation rules
```

If a client sends `{"description": "..."}` without a `name`, FastAPI automatically returns a **422 Unprocessable Entity** with a clear error message.

### 3. The 4-schema pattern (Base / Create / Update / Response)
This is a **Pydantic best practice** for any resource. It separates concerns:

- `Base` → the common shape
- `Create` → what clients send when **creating** (no id, no timestamps)
- `Update` → what clients send when **patching** (everything optional, so partial updates work)
- `Response` → what we send **back** (includes server-generated fields like id and timestamps)

### 4. `model_config = ConfigDict(from_attributes=True)`
This is Pydantic v2 syntax. It enables the **ORM mode**: Pydantic can read fields straight off a SQLAlchemy object, not just a dict.

```python
# Without from_attributes: this would fail
# With from_attributes: Pydantic sees .name, .id, .created_at on the ORM object
ExperimentResponse.model_validate(orm_experiment)
```

### 5. `Dict[str, Any]`
A Python type hint meaning "a dictionary where keys are strings and values can be any JSON-compatible type". Used for fields where the structure is too flexible to formalize.

---

## ✅ How to Verify Phase 3 Works

```python
>>> from backend.app.schemas.experiment import ExperimentCreate
>>> from datetime import datetime
>>> exp = ExperimentCreate(name="house-prices", description="Predict prices")
>>> exp.name
'house-prices'
>>> exp.model_dump()
{'name': 'house-prices', 'description': 'Predict prices', 'tags': None}

# What happens with bad input?
>>> try:
...     ExperimentCreate(name="")  # too short
... except Exception as e:
...     print("Validation failed:", type(e).__name__)
Validation failed: ValidationError
```

---

## 🔄 Schemas in the Request Lifecycle

```
POST /api/v1/experiments
body: {"name": "house-prices", "description": "..."}
        │
        ▼
┌──────────────────────────┐
│ ExperimentCreate         │  ← Phase 3 validates the body
│ (Pydantic)               │
└────────┬─────────────────┘
         │  Validated dict
         ▼
┌──────────────────────────┐
│ experiment_service       │  ← Phase 4 uses the dict
│ .create_experiment(...)  │
└────────┬─────────────────┘
         │  SQLAlchemy ORM object
         ▼
┌──────────────────────────┐
│ Experiment (Model)       │  ← Phase 2 stores it
└────────┬─────────────────┘
         │  ORM object
         ▼
┌──────────────────────────┐
│ ExperimentResponse       │  ← Phase 3 serializes the response
│ (Pydantic)               │
└────────┬─────────────────┘
         │  JSON
         ▼
HTTP 201 + {"id": 1, "name": "house-prices", ...}
```

**Schemas are the gatekeepers.** They catch bad input before it ever touches our database, and they format the output before it goes back to the client.

---

## 🧩 Where Phase 3 Fits in the Big Picture

```
[ Phase 1: skeleton ] ─► [ Phase 2: models ] ─► [ Phase 3: schemas ] ─► [ Phase 4: services ] ─► [ Phase 5: routers ]
        │                        │                       │                       │                       │
   "create the              "define tables         "validate input/      "write business         "expose URL
    folder & DB              that store              output shapes"        logic using             endpoints"
    connection"              our data"                                       these tables"
```

---

## 📋 Files Inventory

| File | Lines | Purpose |
|---|---|---|
| `backend/app/schemas/__init__.py` | 0 | Package marker |
| `backend/app/schemas/experiment.py` | ~33 | 4 schemas for experiment I/O |
| `backend/app/schemas/run.py` | ~43 | 4 schemas for run I/O |

**Total: ~76 lines** of validation contracts.
