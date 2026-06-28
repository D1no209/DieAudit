from pathlib import Path
from typing import Any

from dieaudit_common.persistence.repositories import new_id
from dieaudit_common.settings import get_settings


class ImportService:
    def import_project(self, payload: dict[str, Any]) -> dict[str, Any]:
        settings = get_settings()
        project_id = payload.get("project_id") or new_id("project")
        workspace = Path(settings.workspace_root) / project_id
        return {
            "project_id": project_id,
            "workspace_path": str(workspace),
            "status": "accepted",
            "mode": "skeleton",
        }
