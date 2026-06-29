import asyncio
import json
import os
import traceback
from pathlib import Path
from typing import Any

import acp
import httpx
from acp import schema
from fastapi import FastAPI
from pydantic import BaseModel, Field

from opencode_acp_runner import RecordingClient, _dump, _maybe_await, _prompt


class RunSessionRequest(BaseModel):
    agent_run_id: str = Field(min_length=1)
    audit_run_id: str = Field(min_length=1)
    project_id: str = Field(min_length=1)
    runtime_id: str | None = None
    input_payload: dict[str, Any] = Field(default_factory=dict)
    mcp_servers: dict[str, dict[str, Any]] = Field(default_factory=dict)


app = FastAPI(title="DieAudit Kimi ACP Runtime", version="0.1.0")
_lock = asyncio.Lock()
_agent: Any = None
_process: Any = None
_client: "RuntimeRecordingClient | None" = None
_manager: Any = None


class RuntimeRecordingClient(RecordingClient):
    def __init__(self) -> None:
        super().__init__()
        self._body: RunSessionRequest | None = None
        self._session_id: str | None = None
        self._flushed_index = 0
        self._seq = 0

    def begin_session(self, body: RunSessionRequest) -> None:
        self._body = body
        self._session_id = None
        self._flushed_index = len(self.events)
        self._seq = 0

    def set_session_id(self, session_id: str | None) -> None:
        self._session_id = session_id

    async def session_update(self, session_id: str, update: Any, **kwargs: Any) -> None:
        await super().session_update(session_id, update, **kwargs)
        self._session_id = session_id or self._session_id
        await self.flush()

    async def request_permission(self, options: list[Any], session_id: str, tool_call: Any, **kwargs: Any) -> Any:
        response = await super().request_permission(options, session_id, tool_call, **kwargs)
        self._session_id = session_id or self._session_id
        await self.flush()
        return response

    async def read_text_file(
        self, path: str, session_id: str, limit: int | None = None, line: int | None = None, **kwargs: Any
    ) -> Any:
        response = await super().read_text_file(path, session_id, limit=limit, line=line, **kwargs)
        self._session_id = session_id or self._session_id
        await self.flush()
        return response

    async def write_text_file(self, content: str, path: str, session_id: str, **kwargs: Any) -> Any:
        response = await super().write_text_file(content, path, session_id, **kwargs)
        self._session_id = session_id or self._session_id
        await self.flush()
        return response

    async def ext_method(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        response = await super().ext_method(method, params)
        await self.flush()
        return response

    async def ext_notification(self, method: str, params: dict[str, Any]) -> None:
        await super().ext_notification(method, params)
        await self.flush()

    async def flush(self) -> None:
        if not self._body:
            return
        pending = self.events[self._flushed_index :]
        if not pending:
            return
        events = _events_for_platform(pending, self._body, session_id=self._session_id, start_seq=self._seq)
        await _post_events(self._body, events, session_id=self._session_id)
        self._flushed_index = len(self.events)
        self._seq += len(events)


@app.get("/health")
async def health() -> dict[str, Any]:
    return {"ok": True, "runtime": os.environ.get("ACP_RUNTIME_NAME") or "kimi"}


@app.post("/run-session")
async def run_session(body: RunSessionRequest) -> dict[str, Any]:
    async with _lock:
        agent, client = await _ensure_agent()
        client.begin_session(body)
        session_id = None
        try:
            session = await _maybe_await(agent.new_session(cwd="/workspace", mcp_servers=_mcp_servers(body.mcp_servers)))
            session_id = getattr(session, "sessionId", None) or getattr(session, "session_id", None)
            client.set_session_id(session_id)
            await client.flush()
            response = await _maybe_await(
                agent.prompt(
                    prompt=[schema.TextContentBlock(type="text", text=_prompt({"payload": body.input_payload}))],
                    session_id=session.sessionId,
                )
            )
            await client.flush()
            return {
                "status": "completed",
                "agent_run_id": body.agent_run_id,
                "runtime_id": body.runtime_id,
                "acp_session_id": session_id,
                "response": _dump(response),
                "event_count": client._seq,
            }
        except Exception as exc:
            await client.flush()
            await _post_events(
                body,
                [
                    {
                        "seq": client._seq,
                        "event_type": "runtime_error",
                        "session_id": session_id,
                        "runtime_id": body.runtime_id,
                        "payload": {"error": repr(exc), "traceback": traceback.format_exc()},
                        "content_text": repr(exc),
                    }
                ],
                session_id=session_id,
            )
            return {
                "status": "failed",
                "agent_run_id": body.agent_run_id,
                "runtime_id": body.runtime_id,
                "acp_session_id": session_id,
                "error": repr(exc),
                "event_count": client._seq + 1,
            }


async def _ensure_agent() -> tuple[Any, RuntimeRecordingClient]:
    global _agent, _process, _client, _manager
    if _agent is not None and _client is not None:
        return _agent, _client
    client = RuntimeRecordingClient()
    command = os.environ.get("ACP_COMMAND") or os.environ.get("OPENCODE_ACP_COMMAND", "kimi-code")
    args = (os.environ.get("ACP_ARGS") or os.environ.get("OPENCODE_ACP_ARGS", "acp")).split()
    stream_limit = int(os.environ.get("ACP_STREAM_LIMIT_BYTES", str(8 * 1024 * 1024)))
    _manager = acp.spawn_agent_process(
        client,
        command,
        *args,
        env=dict(os.environ),
        cwd="/workspace",
        transport_kwargs={"limit": stream_limit},
    )
    _agent, _process = await _manager.__aenter__()
    await _maybe_await(
        _agent.initialize(
            protocol_version=acp.PROTOCOL_VERSION,
            client_capabilities=schema.ClientCapabilities(terminal=False),
            client_info=schema.Implementation(name="dieaudit-kimi-runtime", version="0.1.0"),
        )
    )
    _client = client
    return _agent, client


def _mcp_servers(servers: dict[str, dict[str, Any]]) -> list[Any]:
    result: list[Any] = []
    for name, server in servers.items():
        transport = server.get("transport", "http")
        if transport == "sse":
            result.append(schema.SseMcpServer(name=name, url=server["url"], headers=[], type="sse"))
        elif transport == "http":
            result.append(schema.HttpMcpServer(name=name, url=server["url"], headers=[], type="http"))
        elif transport == "stdio":
            env = [schema.EnvVariable(name=str(key), value=str(value)) for key, value in (server.get("env") or {}).items()]
            result.append(
                schema.McpServerStdio(
                    name=name,
                    command=str(server["command"]),
                    args=[str(item) for item in server.get("args", [])],
                    env=env,
                )
            )
    return result


def _events_for_platform(
    events: list[dict[str, Any]],
    body: RunSessionRequest,
    *,
    session_id: str | None,
    start_seq: int = 0,
) -> list[dict[str, Any]]:
    result = []
    for index, event in enumerate(events):
        payload = dict(event)
        content = payload.pop("content_text", None)
        result.append(
            {
                "seq": start_seq + index,
                "event_type": str(payload.get("event_type") or "event"),
                "session_id": payload.get("session_id") or session_id,
                "runtime_id": body.runtime_id,
                "payload": payload,
                "content_text": content,
            }
        )
    return result


async def _post_events(body: RunSessionRequest, events: list[dict[str, Any]], *, session_id: str | None) -> None:
    if not events:
        return
    base_url = os.environ.get("AGENT_GATEWAY_URL") or os.environ.get("PLATFORM_API_URL") or "http://agent-gateway:8000"
    headers = {}
    api_key = os.environ.get("DIEAUDIT_API_KEY")
    api_key_header = os.environ.get("API_KEY_HEADER", "X-API-Key")
    if api_key:
        headers[api_key_header] = api_key
    async with httpx.AsyncClient(timeout=30, headers=headers) as client:
        await client.post(
            f"{base_url.rstrip('/')}/internal/agent-runs/{body.agent_run_id}/transcript-events",
            json={"runtime_id": body.runtime_id, "acp_session_id": session_id, "events": events},
        )


if __name__ == "__main__":
    import uvicorn

    Path("/workspace").mkdir(parents=True, exist_ok=True)
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", "8080")))
