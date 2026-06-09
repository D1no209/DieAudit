from typing import Any

from pydantic import BaseModel, Field


class StartAgentRunRequest(BaseModel):
    audit_run_id: str = Field(default="demo-run")
    project_id: str = Field(default="demo-project")
    agent_name: str = Field(default="orchestrator")
    workspace_host_path: str | None = None
    allow_external_network: bool = False
    retain_runtime_on_failure: bool = False
    input_payload: dict[str, Any] = Field(default_factory=dict)


class TemplateBody(BaseModel):
    template: dict[str, Any]


class A2AAgentCardRequest(BaseModel):
    url: str
