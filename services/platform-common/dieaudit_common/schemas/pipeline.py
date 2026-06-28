from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class StageResult(BaseModel):
    stage: str
    status: str
    started_at: datetime | None = None
    completed_at: datetime | None = None
    summary: dict[str, Any] = Field(default_factory=dict)
    artifact_ids: list[str] = Field(default_factory=list)
    error: str | None = None


class PipelineEventPayload(BaseModel):
    schema_version: int = 1
    audit_run_id: str
    pipeline_run_id: str | None = None
    stage: str | None = None
    status: str | None = None
    summary: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None
