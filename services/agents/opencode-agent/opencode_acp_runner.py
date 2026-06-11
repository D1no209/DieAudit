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
        dumped_tool_call = _dump(tool_call)
        dumped_options = [_dump(option) for option in options]
        allowed_option = _allowed_permission_option(dumped_tool_call, dumped_options)
        self.events.append(
            {
                "event_type": "permission_request",
                "session_id": session_id,
                "tool_call": dumped_tool_call,
                "options": dumped_options,
                "decision": "allow_once" if allowed_option else "deny",
            }
        )
        if allowed_option:
            return schema.RequestPermissionResponse(
                outcome=schema.AllowedOutcome(optionId=allowed_option, outcome="selected")
            )
        return schema.RequestPermissionResponse(outcome=schema.DeniedOutcome(outcome="cancelled"))


async def main() -> int:
    artifact_dir = Path(os.environ.get("ARTIFACT_DIR", "/artifacts"))
    artifact_dir.mkdir(parents=True, exist_ok=True)
    result_file = artifact_dir / "agent_result.json"

    client = RecordingClient()
    input_payload = _load_input_payload()
    mcp_servers = _load_mcp_servers()
    finding_markdown = _read_finding_markdown()
    prompt = _prompt(input_payload, finding_markdown=finding_markdown)
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
            _append_finding_markdown(input_payload, result)
    except Exception as exc:
        if result.get("status") == "completed" and result.get("response"):
            result.update(
                {
                    "close_error": repr(exc),
                    "close_traceback": traceback.format_exc(),
                    "events": client.events,
                }
            )
            _append_finding_markdown(input_payload, result)
        else:
            result.update(
                {
                    "status": "failed",
                    "error": repr(exc),
                    "traceback": traceback.format_exc(),
                    "events": client.events,
                }
            )
            _append_finding_markdown(input_payload, result)
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


def _prompt(input_payload: dict[str, Any], *, finding_markdown: str | None = None) -> str:
    payload = input_payload.get("payload", input_payload)
    task_json = json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False)
    goal = payload.get("goal") if isinstance(payload, dict) else None
    finding_contract = payload.get("finding_artifact_contract") if isinstance(payload, dict) else None
    finding_guidance = ""
    structured_output_guidance = (
        "Write concise structured output. "
        "When reporting vulnerabilities, include a JSON object with this shape: "
        '{"summary": "...", "findings": [{"title": "...", "severity": "high|medium|low|unknown", '
        '"file_path": "relative/path", "line_start": 1, "line_end": 1, "description": "...", '
        '"confidence": 0.0, "source": "agent", "evidence": [{"kind": "code", "summary": "...", "payload": {}}]}], '
        '"evidence": []}. Do not omit required finding fields.\n\n'
    )
    if isinstance(finding_contract, dict) and finding_contract.get("finding_markdown_path"):
        structured_output_guidance = (
            "For this Finding-scoped task, `/finding/finding.md` is the authoritative output and handoff. "
            "Structured JSON is optional; provide it only if it is reliable. Do not let JSON formatting prevent you "
            "from updating the Markdown with the actual analysis.\n\n"
        )
        finding_guidance = (
            "\nFinding shared workspace:\n"
            "- `/finding` is mounted read/write and persists for this specific Finding across Validator, Judger, PoCWriter, and Verifier Agents.\n"
            f"- Before analysis, read `{finding_contract['finding_markdown_path']}` and inspect relevant files under `/finding`.\n"
            f"- After analysis, edit `{finding_contract['finding_markdown_path']}` in place with your conclusions, evidence, blockers, and next-agent handoff notes.\n"
            "- Store Finding-specific notes, PoC drafts, and helper artifacts under `/finding` when useful.\n"
            f"- Also write your stage report to `{finding_contract.get('agent_writable_report_path', '/artifacts/stage-report.md')}`.\n"
        )
        if finding_markdown is not None:
            finding_guidance += (
                "\nCurrent `/finding/finding.md` content loaded by the runner before this Agent started:\n"
                "```markdown\n"
                f"{_truncate_text(finding_markdown, 20000)}\n"
                "```\n"
            )
    return (
        "You are running inside DieAudit. Analyze only the mounted /workspace source tree. "
        "Use authorized MCP servers when useful. "
        "The full task payload is authoritative; do not rely only on the goal text. "
        f"{structured_output_guidance}"
        f"Goal:\n{goal or 'See full task payload.'}\n"
        f"{finding_guidance}\n"
        f"Full task payload:\n```json\n{task_json}\n```"
    )


def _read_finding_markdown() -> str | None:
    markdown_path = os.environ.get("FINDING_MARKDOWN")
    if not markdown_path:
        return None
    path = Path(markdown_path)
    try:
        if path.exists():
            return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    return None


def _append_finding_markdown(input_payload: dict[str, Any], result: dict[str, Any]) -> None:
    markdown_path = os.environ.get("FINDING_MARKDOWN")
    if not markdown_path:
        return
    path = Path(markdown_path)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
    except OSError:
        return

    payload = input_payload.get("payload", input_payload)
    contract = payload.get("finding_artifact_contract") if isinstance(payload, dict) else None
    if not isinstance(contract, dict):
        return

    role = os.environ.get("AGENT_ROLE") or os.environ.get("AGENT_NAME") or "agent"
    section_title = _stage_section_title(role)
    agent_run_id = os.environ.get("AGENT_RUN_ID") or "-"
    status = result.get("status", "unknown")
    response_text = _extract_response_text(result.get("response"))
    if not response_text:
        response_text = _extract_event_transcript(result.get("events", []))
    if not response_text:
        response_text = json.dumps(_compact_result(result), indent=2, sort_keys=True, ensure_ascii=False)

    lines = [
        "",
        f"## {section_title}",
        "",
        f"- Agent role: `{role}`",
        f"- AgentRun: `{agent_run_id}`",
        f"- Status: `{status}`",
    ]
    report_path = contract.get("agent_writable_report_path")
    json_path = contract.get("agent_writable_json_path")
    if report_path:
        lines.append(f"- Stage report path: `{report_path}`")
    if json_path:
        lines.append(f"- Structured result path: `{json_path}`")
    if result.get("error"):
        lines.append(f"- Error: `{result.get('error')}`")
    if result.get("close_error"):
        lines.append(f"- Close error: `{result.get('close_error')}`")
    lines.extend(
        [
            "",
            "### Agent Output",
            "",
            _truncate_text(response_text.strip(), 12000) or "-",
            "",
        ]
    )

    try:
        with path.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write("\n".join(lines))
    except OSError:
        return


def _stage_section_title(role: str) -> str:
    normalized = role.replace("_", "-").lower()
    mapping = {
        "source-sink-finder": "Source-Sink Finder Update",
        "validator": "Validator Update",
        "judger": "Judger Update",
        "poc-writer": "PoC Writer Update",
        "poc-verifier": "PoC Verifier Update",
    }
    return mapping.get(normalized, f"{role} Update")


def _extract_response_text(value: Any) -> str:
    dumped = _dump(value)
    pieces: list[str] = []
    _collect_text(dumped, pieces)
    return "\n\n".join(piece for piece in pieces if piece).strip()


def _extract_event_transcript(events: Any) -> str:
    if not isinstance(events, list):
        return ""
    pieces: list[str] = []
    for event in events:
        if not isinstance(event, dict):
            continue
        update = event.get("update")
        if not isinstance(update, dict):
            continue
        update_kind = update.get("session_update")
        if update_kind not in {"agent_message_chunk", "agent_thought_chunk"}:
            continue
        content = update.get("content")
        if isinstance(content, dict):
            text = content.get("text")
            if isinstance(text, str):
                pieces.append(text)
    return "".join(pieces).strip()


def _collect_text(value: Any, pieces: list[str]) -> None:
    if isinstance(value, str):
        return
    if isinstance(value, list):
        for item in value:
            _collect_text(item, pieces)
        return
    if not isinstance(value, dict):
        return
    text = value.get("text")
    if isinstance(text, str) and text.strip():
        pieces.append(text.strip())
    content = value.get("content")
    if content is not value:
        _collect_text(content, pieces)
    message = value.get("message")
    if message is not value:
        _collect_text(message, pieces)
    output = value.get("output")
    if output is not value:
        _collect_text(output, pieces)


def _compact_result(result: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": result.get("status"),
        "agent_run_id": result.get("agent_run_id"),
        "audit_run_id": result.get("audit_run_id"),
        "project_id": result.get("project_id"),
        "error": result.get("error"),
        "close_error": result.get("close_error"),
        "event_count": len(result.get("events", [])) if isinstance(result.get("events"), list) else 0,
        "response": _dump(result.get("response")),
    }


def _truncate_text(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n\n[truncated {len(text) - limit} chars]"


def _allowed_permission_option(tool_call: dict[str, Any], options: list[dict[str, Any]]) -> str | None:
    if not _permission_targets_allowed_path(tool_call):
        return None
    for option in options:
        if option.get("kind") == "allow_once" and isinstance(option.get("option_id"), str):
            return option["option_id"]
    for option in options:
        if option.get("kind") == "allow_always" and isinstance(option.get("option_id"), str):
            return option["option_id"]
    return None


def _permission_targets_allowed_path(value: Any) -> bool:
    paths = _collect_permission_paths(value)
    if not paths:
        return False
    return all(_path_is_under_allowed_workspace(path) for path in paths)


def _collect_permission_paths(value: Any) -> list[str]:
    paths: list[str] = []
    if isinstance(value, dict):
        for key, item in value.items():
            if key in {"filepath", "filePath", "path", "parentDir", "cwd"} and isinstance(item, str):
                paths.append(item)
            else:
                paths.extend(_collect_permission_paths(item))
    elif isinstance(value, list):
        for item in value:
            paths.extend(_collect_permission_paths(item))
    return paths


def _path_is_under_allowed_workspace(path: str) -> bool:
    try:
        resolved = Path(path).resolve()
    except OSError:
        return False
    allowed_roots = [Path("/finding").resolve(), Path("/artifacts").resolve(), Path("/dieaudit/artifacts").resolve()]
    return any(resolved == root or root in resolved.parents for root in allowed_roots)


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
