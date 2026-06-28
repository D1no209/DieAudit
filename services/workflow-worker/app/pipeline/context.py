from dataclasses import dataclass, field
from typing import Any


@dataclass
class PipelineContext:
    audit_run_id: str
    pipeline_run_id: str
    project_id: str
    snapshot_id: str | None
    workspace_path: str | None
    config: dict[str, Any] = field(default_factory=dict)
    input_payload: dict[str, Any] = field(default_factory=dict)
    cancelled: bool = False
