from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from dieaudit_common.persistence.repositories import AuditRunRepository


def audit_run_to_bff(row: Any) -> dict[str, Any]:
    return {
        "audit_run_id": row.audit_run_id,
        "project_id": row.project_id,
        "snapshot_id": row.snapshot_id,
        "status": row.status,
        "pipeline_status": row.pipeline_status,
        "current_stage": row.current_stage,
        "worker_id": row.worker_id,
        "cancel_requested": row.cancel_requested,
        "workspace_path": row.workspace_path,
        "allow_external_network": row.allow_external_network,
        "retain_runtime_on_failure": row.retain_runtime_on_failure,
        "config": row.config_json or {},
        "input_payload": row.input_payload or {},
        "metadata": row.metadata_json or {},
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


class AuditRunApplication:
    def __init__(self, session: AsyncSession) -> None:
        self.audit_runs = AuditRunRepository(session)

    async def list_audit_runs(self) -> list[dict[str, Any]]:
        return [audit_run_to_bff(row) for row in await self.audit_runs.list()]

    async def create_audit_run(self, payload: dict[str, Any]) -> dict[str, Any]:
        row = await self.audit_runs.create(
            project_id=payload["project_id"],
            snapshot_id=payload.get("snapshot_id"),
            workspace_path=None,
            allow_external_network=bool(payload.get("allow_external_network")),
            retain_runtime_on_failure=bool(payload.get("retain_runtime_on_failure")),
            input_payload=payload.get("input_payload") or {},
            config=payload.get("config") or {"enabled_agents": payload.get("enabled_agents") or []},
        )
        return audit_run_to_bff(row)

    async def get_audit_run(self, audit_run_id: str) -> dict[str, Any] | None:
        row = await self.audit_runs.get(audit_run_id)
        return audit_run_to_bff(row) if row else None

    async def queue_audit_run(self, audit_run_id: str) -> dict[str, Any] | None:
        await self.audit_runs.queue(audit_run_id)
        row = await self.audit_runs.get(audit_run_id)
        return audit_run_to_bff(row) if row else None

    async def cancel_audit_run(self, audit_run_id: str, reason: str) -> dict[str, Any] | None:
        await self.audit_runs.cancel(audit_run_id, reason)
        row = await self.audit_runs.get(audit_run_id)
        return audit_run_to_bff(row) if row else None
