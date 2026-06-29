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

    async def session_update(self, session_id: str, update: Any, **kwargs: Any) -> None:
        self.events.append(
            {
                "event_type": "session_update",
                "session_id": session_id,
                "update": _dump(update),
                "kwargs": kwargs,
            }
        )

    async def request_permission(self, options: list[Any], session_id: str, tool_call: Any, **kwargs: Any) -> Any:
        dumped_tool_call = _dump(tool_call)
        dumped_options = [_dump(option) for option in options]
        allowed_option = _approval_permission_option(dumped_options)
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

    async def read_text_file(
        self, path: str, session_id: str, limit: int | None = None, line: int | None = None, **kwargs: Any
    ) -> Any:
        resolved = _resolve_client_path(path)
        if resolved is None or not _path_is_under_client_read_root(resolved):
            content = ""
        else:
            try:
                text = resolved.read_text(encoding="utf-8", errors="replace")
                lines = text.splitlines(keepends=True)
                if line is not None:
                    start = max(0, line - 1)
                    text = "".join(lines[start:])
                if limit is not None and limit >= 0:
                    text = text[:limit]
                content = text
            except OSError:
                content = ""
        self.events.append({"event_type": "client_read_text_file", "session_id": session_id, "path": path})
        return schema.ReadTextFileResponse(content=content)

    async def write_text_file(self, content: str, path: str, session_id: str, **kwargs: Any) -> Any:
        resolved = _resolve_client_path(path)
        wrote = False
        if resolved is not None and _path_is_under_allowed_workspace(str(resolved)):
            try:
                resolved.parent.mkdir(parents=True, exist_ok=True)
                resolved.write_text(content, encoding="utf-8")
                wrote = True
            except OSError:
                wrote = False
        self.events.append(
            {"event_type": "client_write_text_file", "session_id": session_id, "path": path, "wrote": wrote}
        )
        return schema.WriteTextFileResponse()

    async def ext_method(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        self.events.append({"event_type": "client_ext_method", "method": method, "params": _dump(params)})
        return {}

    async def ext_notification(self, method: str, params: dict[str, Any]) -> None:
        self.events.append({"event_type": "client_ext_notification", "method": method, "params": _dump(params)})


async def main() -> int:
    artifact_dir = Path(os.environ.get("ARTIFACT_DIR", "/artifacts"))
    artifact_dir.mkdir(parents=True, exist_ok=True)
    result_file = artifact_dir / "agent_result.json"

    client = RecordingClient()
    input_payload = _load_input_payload()
    mcp_servers = _load_mcp_servers()
    finding_markdown = _read_finding_markdown()
    runtime_name = os.environ.get("ACP_RUNTIME_NAME") or os.environ.get("OPENCODE_RUNTIME_NAME") or "opencode"
    kimi_prompt_mode = runtime_name == "kimi" and os.environ.get("KIMI_USE_ACP_MODE", "").lower() not in {"1", "true", "yes"}
    prompt = _prompt(
        input_payload,
        finding_markdown=finding_markdown,
        allow_tools=not kimi_prompt_mode,
        include_workspace_context=kimi_prompt_mode,
    )
    result: dict[str, Any] = {
        "status": "running",
        "agent_run_id": os.environ.get("AGENT_RUN_ID"),
        "audit_run_id": os.environ.get("AUDIT_RUN_ID"),
        "project_id": os.environ.get("PROJECT_ID"),
        "events": [],
    }
    process_ref: Any | None = None
    try:
        env = dict(os.environ)
        command = os.environ.get("ACP_COMMAND") or os.environ.get("OPENCODE_ACP_COMMAND", "opencode")
        args = (os.environ.get("ACP_ARGS") or os.environ.get("OPENCODE_ACP_ARGS", "acp")).split()
        stream_limit = int(os.environ.get("ACP_STREAM_LIMIT_BYTES", str(8 * 1024 * 1024)))
        async with acp.spawn_agent_process(
            client,
            command,
            *args,
            env=env,
            cwd="/workspace",
            transport_kwargs={"limit": stream_limit},
        ) as (agent, process):
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
                    "runtime_name": runtime_name,
                    "acp_command": [command, *args],
                }
            )
            _append_finding_markdown(input_payload, result)
        else:
            if runtime_name == "kimi":
                _prepare_kimi_config(env)
            async with acp.spawn_agent_process(client, command, *args, env=env, cwd="/workspace") as (agent, process):
                process_ref = process
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
                        "runtime_name": runtime_name,
                        "acp_command": [command, *args],
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
                    "process_stderr": await _read_process_stderr(process_ref),
                }
            )
            _append_finding_markdown(input_payload, result)
    result_file.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps({"dieaudit_result": str(result_file), "status": result["status"]}), flush=True)
    return 0 if result["status"] == "completed" else 1


async def _read_process_stderr(process: Any | None) -> str:
    stream = getattr(process, "stderr", None)
    if stream is None:
        return ""
    try:
        data = await asyncio.wait_for(stream.read(), timeout=2)
    except Exception:
        return ""
    if isinstance(data, bytes):
        return data.decode("utf-8", errors="replace")
    return str(data)


def _prepare_kimi_config(env: dict[str, str]) -> None:
    api_key = env.get("KIMI_MODEL_API_KEY") or env.get("LOCAL_LLM_API_KEY")
    if not api_key:
        return
    model_name = env.get("KIMI_MODEL_NAME") or "deepseek-v4-flash"
    base_url = env.get("KIMI_MODEL_BASE_URL") or "https://api.deepseek.com/v1"
    max_context = int(env.get("KIMI_MODEL_MAX_CONTEXT_SIZE") or "64000")
    kimi_home = Path(env.get("KIMI_CODE_HOME") or "/tmp/kimi-code-home")
    kimi_home.mkdir(parents=True, exist_ok=True)
    config_file = kimi_home / "config.toml"
    config_file.write_text(
        "\n".join(
            [
                f"default_model = {_toml_quote(model_name)}",
                "default_thinking = false",
                'default_permission_mode = "auto"',
                "default_plan_mode = false",
                "telemetry = false",
                "",
                '[providers.deepseek]',
                'type = "openai"',
                f"base_url = {_toml_quote(base_url)}",
                f"api_key = {_toml_quote(api_key)}",
                "",
                f'[models.{_toml_table_key(model_name)}]',
                'provider = "deepseek"',
                f"model = {_toml_quote(model_name)}",
                f"max_context_size = {max_context}",
                'capabilities = ["tool_use"]',
                "",
                "[thinking]",
                'mode = "off"',
                "",
                "[loop_control]",
                "max_steps_per_turn = 12",
                "max_retries_per_step = 2",
                "reserved_context_size = 8000",
                "",
                "[experimental]",
                "micro_compaction = false",
                "",
                "[background]",
                "keep_alive_on_exit = false",
                "",
                "[[permission.rules]]",
                'decision = "allow"',
                'pattern = "Read"',
                "",
                "[[permission.rules]]",
                'decision = "allow"',
                'pattern = "Glob"',
                "",
                "[[permission.rules]]",
                'decision = "allow"',
                'pattern = "Grep"',
                "",
                "[[permission.rules]]",
                'decision = "allow"',
                'pattern = "LS"',
                "",
            ]
        ),
        encoding="utf-8",
    )
    env["KIMI_CODE_HOME"] = str(kimi_home)
    env.setdefault("HOME", "/root")
    env.setdefault("USER", "root")


def _toml_quote(value: str) -> str:
    return json.dumps(value)


def _toml_table_key(value: str) -> str:
    if all(ch.isalnum() or ch in {"_", "-"} for ch in value):
        return value
    return _toml_quote(value)


async def _run_kimi_prompt_mode(command: str, args: list[str], prompt: str, env: dict[str, str]) -> dict[str, Any]:
    kimi_args = list(args)
    if kimi_args and kimi_args[-1] == "acp":
        kimi_args = kimi_args[:-1]
    timeout = int(os.environ.get("KIMI_PROMPT_TIMEOUT_SECONDS", os.environ.get("OPENCODE_AGENT_TIMEOUT_SECONDS", "1800")))
    child_env = {
        key: value
        for key, value in env.items()
        if key in {"PATH", "HOME", "TERM", "LANG", "BUN_INSTALL", "SHELL"}
        or key.startswith("KIMI_")
        or key in {"HTTP_PROXY", "HTTPS_PROXY", "NO_PROXY", "http_proxy", "https_proxy", "no_proxy"}
    }
    child_env.setdefault("HOME", "/root")
    child_env.setdefault("USER", "root")
    process = await asyncio.create_subprocess_exec(
        command,
        *kimi_args,
        "--add-dir",
        "/workspace",
        "-p",
        prompt,
        "--output-format",
        "text",
        stdin=asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=child_env,
        cwd="/tmp",
    )
    try:
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        process.terminate()
        try:
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=5)
        except asyncio.TimeoutError:
            process.kill()
            stdout, stderr = await process.communicate()
        return {
            "status": "failed",
            "error": f"kimi prompt mode timed out after {timeout}s",
            "process_returncode": process.returncode,
            "process_stdout": _redact_sensitive(stdout.decode("utf-8", errors="replace")),
            "process_stderr": _redact_sensitive(stderr.decode("utf-8", errors="replace")),
            "runtime_name": "kimi",
            "acp_command": [command, *args],
            "execution_mode": "prompt",
        }
    stdout_text = _redact_sensitive(stdout.decode("utf-8", errors="replace"))
    stderr_text = _redact_sensitive(stderr.decode("utf-8", errors="replace"))
    result = {
        "status": "completed" if process.returncode == 0 else "failed",
        "response": {"content": stdout_text},
        "events": [],
        "process_returncode": process.returncode,
        "process_stdout": stdout_text,
        "process_stderr": stderr_text,
        "runtime_name": "kimi",
        "acp_command": [command, *args],
        "execution_mode": "prompt",
        "error": None if process.returncode == 0 else stderr_text[-4000:] or f"kimi exited {process.returncode}",
    }
    attempt = int(env.get("_KIMI_PROMPT_ATTEMPT") or "1")
    max_attempts = int(os.environ.get("KIMI_PROMPT_RETRIES", "2"))
    if (
        result["status"] == "failed"
        and attempt < max_attempts
        and _is_retryable_kimi_empty_exit(stdout_text, stderr_text)
    ):
        retry_env = dict(env)
        retry_env["_KIMI_PROMPT_ATTEMPT"] = str(attempt + 1)
        await asyncio.sleep(2)
        return await _run_kimi_prompt_mode(command, args, prompt, retry_env)
    return result


def _is_retryable_kimi_empty_exit(stdout_text: str, stderr_text: str) -> bool:
    normalized = "\n".join(line.strip() for line in stderr_text.splitlines() if line.strip())
    dependency_only = normalized in {
        "Resolving dependencies\nResolved, downloaded and extracted [41]\nSaved lockfile",
        "Resolving dependencies\nSaved lockfile",
    }
    return not stdout_text.strip() and dependency_only


def _redact_sensitive(text: str) -> str:
    redacted = text
    for name in (
        "KIMI_MODEL_API_KEY",
        "LOCAL_LLM_API_KEY",
        "DIEAUDIT_API_KEY",
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
    ):
        value = os.environ.get(name)
        if value:
            redacted = redacted.replace(value, "***")
    return redacted


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
        elif transport == "stdio":
            env = [
                schema.EnvVariable(name=str(key), value=str(value))
                for key, value in (server.get("env") or {}).items()
            ]
            result.append(
                schema.McpServerStdio(
                    name=name,
                    command=str(server["command"]),
                    args=[str(item) for item in server.get("args", [])],
                    env=env,
                )
            )
    return result


def _prompt(
    input_payload: dict[str, Any],
    *,
    finding_markdown: str | None = None,
    allow_tools: bool = True,
    include_workspace_context: bool = False,
) -> str:
    payload = input_payload.get("payload", input_payload)
    if not allow_tools and isinstance(payload, dict):
        payload = _sanitize_prompt_payload(payload)
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
        if allow_tools:
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
        else:
            structured_output_guidance = (
                "For this Finding-scoped task, return concise Markdown plus optional JSON. "
                "The runner will append your response to the Finding handoff file; do not try to read or write files.\n\n"
            )
            finding_guidance = "\nFinding shared context is provided below. Analyze from the supplied text only.\n"
        if finding_markdown is not None:
            finding_guidance += (
                "\nCurrent `/finding/finding.md` content loaded by the runner before this Agent started:\n"
                "```markdown\n"
                f"{_truncate_text(finding_markdown, 20000)}\n"
                "```\n"
            )
    tool_guidance = (
        "Use authorized MCP servers when useful. "
        if allow_tools
        else "Do not use tools, MCP servers, shell commands, session state, compaction, or interactive approvals. "
    )
    workspace_context = f"\nWorkspace context for pure prompt mode:\n{_workspace_context(Path('/workspace'))}\n" if include_workspace_context else ""
    return (
        "You are running inside DieAudit. Analyze the target project only. "
        "Do not print environment variables, API keys, bearer tokens, or other secrets. "
        f"{tool_guidance}"
        "The full task payload is authoritative; do not rely only on the goal text. "
        f"{structured_output_guidance}"
        f"Goal:\n{goal or 'See full task payload.'}\n"
        f"{workspace_context}"
        f"{finding_guidance}\n"
        f"Full task payload:\n```json\n{task_json}\n```"
    )


def _sanitize_prompt_payload(payload: dict[str, Any]) -> dict[str, Any]:
    blocked_keys = {
        "agent_collaboration",
        "codebase_memory",
        "codebase_memory_mcp",
        "mcp",
        "mcp_servers",
        "structure",
        "whiteboard_mcp",
    }
    sanitized: dict[str, Any] = {}
    for key, value in payload.items():
        if key in blocked_keys:
            continue
        if isinstance(value, dict):
            sanitized[key] = _sanitize_prompt_payload(value)
        elif isinstance(value, list):
            sanitized[key] = [_sanitize_prompt_payload(item) if isinstance(item, dict) else item for item in value]
        else:
            sanitized[key] = value
    sanitized["prompt_mode_constraints"] = {
        "tools_available": False,
        "instruction": "Use only the task text and the workspace context snippets embedded in this prompt. Do not attempt to read files, use MCP, use shell, or start a session.",
    }
    return sanitized


def _workspace_context(root: Path) -> str:
    ignored_dirs = {".git", "vendor", "node_modules", "runtime", "cache", "logs", "public/static", "public/assets"}
    files: list[Path] = []
    try:
        for path in root.rglob("*"):
            if not path.is_file():
                continue
            relative = path.relative_to(root)
            relative_posix = relative.as_posix()
            if any(relative_posix == ignored or relative_posix.startswith(f"{ignored}/") for ignored in ignored_dirs):
                continue
            if path.stat().st_size > 256_000:
                continue
            files.append(relative)
    except Exception as exc:
        return f"Unable to inventory workspace: {exc}"
    files = sorted(files, key=lambda item: item.as_posix())
    listed = [item.as_posix() for item in files[:160]]
    snippets: list[str] = []
    snippet_budget = 24_000
    security_names = {
        "composer.json",
        "composer.lock",
        "config/app.php",
        "config/database.php",
        "config/route.php",
        "route/app.php",
        "public/index.php",
        ".env",
    }
    security_prefixes = ("app/", "application/", "extend/", "config/", "route/", "public/")
    for relative in files:
        relative_posix = relative.as_posix()
        selected = relative_posix in security_names or (
            relative_posix.endswith(".php") and any(relative_posix.startswith(prefix) for prefix in security_prefixes)
        )
        if not selected:
            continue
        text = _read_workspace_snippet(root / relative, limit=1800)
        if not text:
            continue
        block = f"\n--- {relative_posix} ---\n{text}"
        if sum(len(item) for item in snippets) + len(block) > snippet_budget:
            break
        snippets.append(block)
        if len(snippets) >= 18:
            break
    return "\n".join(
        [
            "File inventory sample:",
            "\n".join(f"- {item}" for item in listed) or "- <empty>",
            "",
            "Selected source/config snippets:",
            "\n".join(snippets) or "- <none>",
        ]
    )


def _read_workspace_snippet(path: Path, *, limit: int) -> str:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return ""
    for name in ("KIMI_MODEL_API_KEY", "LOCAL_LLM_API_KEY"):
        value = os.environ.get(name)
        if value:
            text = text.replace(value, "***")
    return text[:limit]


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
    return _approval_permission_option(options)


def _approval_permission_option(options: list[dict[str, Any]]) -> str | None:
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
        Path(path).resolve()
    except OSError:
        return False
    return True


def _resolve_client_path(path: str) -> Path | None:
    try:
        candidate = Path(path)
        if not candidate.is_absolute():
            candidate = Path("/workspace") / candidate
        return candidate.resolve()
    except OSError:
        return None


def _path_is_under_client_read_root(path: Path) -> bool:
    return path.is_absolute()


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
