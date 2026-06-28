from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from dieaudit_common.persistence.repositories import ProjectRepository


def project_to_bff(row: Any) -> dict[str, Any]:
    return {
        "project_id": row.project_id,
        "name": row.name,
        "source_type": row.source_type,
        "source_uri": row.source_uri,
        "default_branch": row.default_branch,
        "status": row.status,
        "metadata": row.metadata_json or {},
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


class ProjectApplication:
    def __init__(self, session: AsyncSession) -> None:
        self.projects = ProjectRepository(session)

    async def list_projects(self) -> list[dict[str, Any]]:
        return [project_to_bff(row) for row in await self.projects.list()]

    async def create_project(self, payload: dict[str, Any]) -> dict[str, Any]:
        row = await self.projects.create(
            name=payload["name"],
            source_type="git" if payload.get("git_url") else "manual",
            source_uri=payload.get("git_url"),
            metadata=payload.get("metadata") or {},
        )
        return project_to_bff(row)
