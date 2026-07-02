import json
from datetime import datetime
from typing import Optional, Dict, Any
from pydantic import BaseModel, Field, ConfigDict, field_validator


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

    @field_validator("metrics", "parameters", "tags", mode="before")
    @classmethod
    def _parse_json(cls, v):
        """
        The DB stores metrics/parameters/tags as JSON TEXT. When we read the
        attribute back, we get a string. The API contract promises a dict,
        so parse on the way out.
        """
        if v is None or v == "":
            return None
        if isinstance(v, (dict, list)):
            return v
        if isinstance(v, str):
            try:
                return json.loads(v)
            except json.JSONDecodeError:
                return None
        return v
