from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class OpenCodeAcpResult:
    status: str
    session_id: str | None = None
    response: dict[str, Any] = field(default_factory=dict)
    events: list[dict[str, Any]] = field(default_factory=list)
    error: str | None = None


class OpenCodeAcpClient:
    runtime_name = "opencode"
    protocol_kind = "agent-client-protocol"
    transport = "stdio"

    def command_env(self) -> dict[str, str]:
        return {
            "OPENCODE_ACP_COMMAND": "opencode",
            "OPENCODE_ACP_ARGS": "acp",
        }

    @staticmethod
    def output_schema() -> dict[str, Any]:
        return {
            "type": "object",
            "required": ["status", "events"],
            "properties": {
                "status": {"type": "string"},
                "response": {"type": "object"},
                "events": {"type": "array"},
                "error": {"type": ["string", "null"]},
            },
        }
