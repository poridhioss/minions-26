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
