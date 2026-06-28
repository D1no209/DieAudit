from __future__ import annotations

from typing import Any

from dieaudit_common.persistence.repositories import new_id


class AgentRunService:
    async def start(self, payload: dict[str, Any]) -> dict[str, Any]:
        return {
            "agent_run_id": new_id("agent"),
            "status": "queued",
            "mode": "skeleton",
            "input": payload,
        }
