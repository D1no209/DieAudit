from __future__ import annotations

from typing import Any

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from dieaudit_common.persistence.repositories import ProjectRepository, SnapshotRepository
from dieaudit_common.settings import get_settings

from app.application.serializers import project_to_bff, snapshot_to_bff


class ProjectApplication:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.projects = ProjectRepository(session)
        self.snapshots = SnapshotRepository(session)

    async def list_projects(self) -> list[dict[str, Any]]:
        return [project_to_bff(row) for row in await self.projects.list()]

    async def create_project(self, payload: dict[str, Any]) -> dict[str, Any]:
        git_url = payload.get("git_url")
        ref = payload.get("ref")
        row = await self.projects.create(
            name=payload["name"],
            source_type="git" if git_url else "manual",
            source_uri=git_url,
            metadata=payload.get("metadata") or {},
        )
        snapshot_payload = await self._create_workspace_snapshot(row.project_id, git_url=git_url, ref=ref)
        snapshot = await self.snapshots.create_ready(
            project_id=row.project_id,
            workspace_path=snapshot_payload["workspace_path"],
            source_type="git" if git_url else "manual",
            source_ref=ref or git_url,
        )
        row.status = "ready"
        row.metadata_json = {**(row.metadata_json or {}), "latest_snapshot_id": snapshot.snapshot_id}
        return {"project": project_to_bff(row), "snapshot": snapshot_to_bff(snapshot)}

    async def _create_workspace_snapshot(self, project_id: str, *, git_url: str | None, ref: str | None) -> dict[str, Any]:
        settings = get_settings()
        payload = {"project_id": project_id, "git_url": git_url, "ref": ref}
        async with httpx.AsyncClient(base_url=str(settings.workspace_engine_url), timeout=300) as client:
            response = await client.post("/internal/imports", json=payload)
        response.raise_for_status()
        result = response.json()
        if not result.get("workspace_path"):
            raise RuntimeError("workspace-engine did not return workspace_path")
        return result
