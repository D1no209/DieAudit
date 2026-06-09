import asyncio
import json
import os
import traceback
from pathlib import Path
from typing import Any

import acp
from acp import schema


class RecordingClient(acp.Client):
    def __init__(self) -> None:
        super().__init__()
        self.events: list[dict[str, Any]] = []

    def session_update(self, session_id: str, update: Any, **kwargs: Any) -> None:
        self.events.append(
            {
                "event_type": "session_update",
                "session_id": session_id,
                "update": _dump(update),
                "kwargs": kwargs,
            }
        )

    def request_permission(self, options: list[Any], session_id: str, tool_call: Any, **kwargs: Any) -> Any:
        self.events.append(
            {
                "event_type": "permission_request",
                "session_id": session_id,
                "tool_call": _dump(tool_call),
                "options": [_dump(option) for option in options],
            }
        )
        return schema.RequestPermissionResponse(outcome=schema.DeniedOutcome(outcome="cancelled"))


async def main() -> int:
    artifact_dir = Path(os.environ.get("ARTIFACT_DIR", "/artifacts"))
    artifact_dir.mkdir(parents=True, exist_ok=True)
    result_file = artifact_dir / "agent_result.json"

    client = RecordingClient()
    input_payload = _load_input_payload()
    mcp_servers = _load_mcp_servers()
    prompt = _prompt(input_payload)
    result: dict[str, Any] = {
        "status": "running",
        "agent_run_id": os.environ.get("AGENT_RUN_ID"),
        "audit_run_id": os.environ.get("AUDIT_RUN_ID"),
        "project_id": os.environ.get("PROJECT_ID"),
        "events": [],
    }
    try:
        env = dict(os.environ)
        command = os.environ.get("OPENCODE_ACP_COMMAND", "opencode")
        args = os.environ.get("OPENCODE_ACP_ARGS", "acp").split()
        async with acp.spawn_agent_process(client, command, *args, env=env, cwd="/workspace") as (agent, process):
            initialize = await _maybe_await(
                agent.initialize(
                    protocol_version=acp.PROTOCOL_VERSION,
                    client_capabilities=schema.ClientCapabilities(terminal=False),
                    client_info=schema.Implementation(name="dieaudit-opencode-runner", version="0.1.0"),
                )
            )
            session = await _maybe_await(agent.new_session(cwd="/workspace", mcp_servers=mcp_servers))
            response = await _maybe_await(
                agent.prompt(
                    prompt=[schema.TextContentBlock(type="text", text=prompt)],
                    session_id=session.sessionId,
                )
            )
            result.update(
                {
                    "status": "completed",
                    "initialize": _dump(initialize),
                    "session": _dump(session),
                    "response": _dump(response),
                    "events": client.events,
                    "process_returncode": getattr(process, "returncode", None),
                }
            )
    except Exception as exc:
        result.update(
            {
                "status": "failed",
                "error": repr(exc),
                "traceback": traceback.format_exc(),
                "events": client.events,
            }
        )
    result_file.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps({"dieaudit_result": str(result_file), "status": result["status"]}), flush=True)
    return 0 if result["status"] == "completed" else 1


def _load_input_payload() -> dict[str, Any]:
    runtime_dir = Path(os.environ.get("DIEAUDIT_RUNTIME_DIR", "/dieaudit/runtime"))
    input_file = runtime_dir / "input.json"
    if input_file.exists():
        return json.loads(input_file.read_text(encoding="utf-8"))
    raw = os.environ.get("AGENT_INPUT_JSON", "{}")
    return {"payload": json.loads(raw)}


def _load_mcp_servers() -> list[Any]:
    raw = os.environ.get("MCP_SERVERS_JSON", "{}")
    servers = json.loads(raw)
    result: list[Any] = []
    for name, server in servers.items():
        transport = server.get("transport", "http")
        if transport == "sse":
            result.append(schema.SseMcpServer(name=name, url=server["url"], headers=[], type="sse"))
        elif transport == "http":
            result.append(schema.HttpMcpServer(name=name, url=server["url"], headers=[], type="http"))
    return result


def _prompt(input_payload: dict[str, Any]) -> str:
    payload = input_payload.get("payload", input_payload)
    if isinstance(payload, dict) and payload.get("goal"):
        goal = payload["goal"]
    else:
        goal = json.dumps(payload, indent=2, sort_keys=True)
    return (
        "You are running inside DieAudit. Analyze only the mounted /workspace source tree. "
        "Use authorized MCP servers when useful. Write concise structured output.\n\n"
        f"Task:\n{goal}"
    )


async def _maybe_await(value: Any) -> Any:
    if hasattr(value, "__await__"):
        return await value
    return value


def _dump(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, list):
        return [_dump(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _dump(item) for key, item in value.items()}
    return repr(value)


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
