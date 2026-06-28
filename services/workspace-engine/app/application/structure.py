from pathlib import Path


class StructureService:
    def inventory(self, workspace_path: str) -> dict:
        path = Path(workspace_path)
        return {"workspace_path": workspace_path, "exists": path.exists(), "files": []}
