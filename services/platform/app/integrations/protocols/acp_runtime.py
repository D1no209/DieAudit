from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class AcpRuntimeResult:
    status: str
    session_id: str | None = None
    response: dict[str, Any] = field(default_factory=dict)
    events: list[dict[str, Any]] = field(default_factory=list)
    error: str | None = None


class AcpRuntimeClient:
    runtime_name = "acp"
    protocol_kind = "agent-client-protocol"
    transport = "stdio"

    def command_env(self, template: dict[str, Any] | None = None) -> dict[str, str]:
        protocol = (template or {}).get("protocol") if isinstance((template or {}).get("protocol"), dict) else {}
        command = protocol.get("stdio_command") if isinstance(protocol, dict) else None
        runtime = str(protocol.get("runtime") or self.runtime_name) if isinstance(protocol, dict) else self.runtime_name
        if isinstance(command, list) and command:
            return {
                "ACP_RUNTIME_NAME": runtime,
                "ACP_COMMAND": str(command[0]),
                "ACP_ARGS": " ".join(str(item) for item in command[1:]) or "acp",
            }
        return {
            "ACP_RUNTIME_NAME": runtime,
            "ACP_COMMAND": "agent-runtime",
            "ACP_ARGS": "acp",
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
