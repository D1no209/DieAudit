from typing import Any

from pydantic import BaseModel, Field


class ErrorEnvelope(BaseModel):
    error: dict[str, Any]


class CreateProjectPayload(BaseModel):
    name: str = Field(min_length=1)
    git_url: str | None = None
    ref: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class CreateAuditRunPayload(BaseModel):
    project_id: str = Field(min_length=1)
    snapshot_id: str | None = None
    enabled_agents: list[str] = Field(default_factory=list)
    allow_external_network: bool = False
    retain_runtime_on_failure: bool = False
    input_payload: dict[str, Any] = Field(default_factory=dict)
    config: dict[str, Any] = Field(default_factory=dict)


class StartAuditRunPayload(BaseModel):
    force: bool = False


class CancelAuditRunPayload(BaseModel):
    reason: str = "cancelled by user"
