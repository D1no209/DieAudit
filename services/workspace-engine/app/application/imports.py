from pathlib import Path
import shutil
import subprocess
from typing import Any

from dieaudit_common.persistence.repositories import new_id
from dieaudit_common.settings import get_settings


class ImportService:
    def import_project(self, payload: dict[str, Any]) -> dict[str, Any]:
        settings = get_settings()
        project_id = payload.get("project_id") or new_id("project")
        snapshot_id = payload.get("snapshot_id") or new_id("snapshot")
        workspace = Path(settings.workspace_root) / project_id / snapshot_id
        git_url = payload.get("git_url")
        ref = payload.get("ref")
        if workspace.exists():
            shutil.rmtree(workspace)
        workspace.parent.mkdir(parents=True, exist_ok=True)
        if git_url:
            command = ["git", "clone", "--depth", "1"]
            if ref:
                command.extend(["--branch", str(ref)])
            command.extend(["--", str(git_url), str(workspace)])
            completed = subprocess.run(command, capture_output=True, text=True, timeout=300)
            if completed.returncode != 0:
                raise RuntimeError((completed.stderr or completed.stdout or "git clone failed").strip())
            mode = "git"
        else:
            workspace.mkdir(parents=True, exist_ok=True)
            mode = "manual"
        return {
            "project_id": project_id,
            "snapshot_id": snapshot_id,
            "workspace_path": str(workspace),
            "status": "ready",
            "mode": mode,
        }
