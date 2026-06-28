from __future__ import annotations

from typing import Any

from dieaudit_common.persistence.repositories import new_id


class McpToolService:
    async def run(self, payload: dict[str, Any]) -> dict[str, Any]:
        return {"tool_run_id": new_id("tool"), "status": "queued", "mode": "skeleton", "input": payload}
