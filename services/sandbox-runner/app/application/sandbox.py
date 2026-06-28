from typing import Any

from dieaudit_common.persistence.repositories import new_id


class SandboxService:
    async def run_poc(self, payload: dict[str, Any]) -> dict[str, Any]:
        return {"sandbox_run_id": new_id("sandbox"), "status": "queued", "mode": "skeleton", "input": payload}
