from typing import Any

from dieaudit_common.persistence.repositories import new_id


class SnapshotService:
    def create_snapshot(self, payload: dict[str, Any]) -> dict[str, Any]:
        return {"snapshot_id": new_id("snapshot"), "status": "ready", **payload}
