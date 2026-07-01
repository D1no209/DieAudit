from __future__ import annotations

from typing import Any

import httpx

from dieaudit_common.settings import get_settings


class InternalClients:
    def __init__(self) -> None:
        self.settings = get_settings()

    async def workspace_structure(self, workspace_path: str) -> dict[str, Any]:
        return await self._post(str(self.settings.workspace_engine_url), "/internal/structure", {"workspace_path": workspace_path})

    async def start_agent_run(self, payload: dict[str, Any]) -> dict[str, Any]:
        return await self._post(str(self.settings.agent_gateway_url), "/internal/agent-runs", payload)

    async def cleanup_runtime(self, audit_run_id: str) -> dict[str, Any]:
        return await self._post(str(self.settings.sandbox_runner_url), "/internal/cleanup", {"audit_run_id": audit_run_id})

    async def _post(self, base_url: str, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        async with httpx.AsyncClient(base_url=base_url, timeout=900) as client:
            response = await client.post(path, json=payload)
        response.raise_for_status()
        data = response.json()
        return data if isinstance(data, dict) else {"result": data}
