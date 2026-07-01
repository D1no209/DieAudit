from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from dieaudit_common.domain.models import (
    AuditEvent,
    AuditRun,
    PipelineRun,
    PipelineStageRun,
    Project,
    ProjectSnapshot,
    WorkerHeartbeat,
)


def new_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:16]}"


class ProjectRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list(self) -> list[Project]:
        rows = await self.session.execute(select(Project).order_by(Project.created_at.desc()))
        return list(rows.scalars())

    async def get(self, project_id: str) -> Project | None:
        return await self.session.scalar(select(Project).where(Project.project_id == project_id))

    async def create(self, *, name: str, source_type: str, source_uri: str | None, metadata: dict[str, Any]) -> Project:
        project = Project(
            project_id=new_id("project"),
            name=name,
            source_type=source_type,
            source_uri=source_uri,
            status="created",
            metadata_json={"schema_version": 1, **metadata},
        )
        self.session.add(project)
        return project


class AuditRunRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list(self) -> list[AuditRun]:
        rows = await self.session.execute(select(AuditRun).order_by(AuditRun.created_at.desc()))
        return list(rows.scalars())

    async def get(self, audit_run_id: str) -> AuditRun | None:
        return await self.session.scalar(select(AuditRun).where(AuditRun.audit_run_id == audit_run_id))

    async def create(
        self,
        *,
        project_id: str,
        snapshot_id: str | None,
        workspace_path: str | None,
        allow_external_network: bool,
        retain_runtime_on_failure: bool,
        input_payload: dict[str, Any],
        config: dict[str, Any],
    ) -> AuditRun:
        row = AuditRun(
            audit_run_id=new_id("audit"),
            project_id=project_id,
            snapshot_id=snapshot_id,
            status="created",
            pipeline_status="pending",
            workspace_path=workspace_path,
            allow_external_network=allow_external_network,
            retain_runtime_on_failure=retain_runtime_on_failure,
            input_payload={"schema_version": 1, **input_payload},
            config_json={"schema_version": 1, **config},
        )
        self.session.add(row)
        return row

    async def queue(self, audit_run_id: str) -> None:
        row = await self.get(audit_run_id)
        if row:
            row.status = "queued"
            row.pipeline_status = "queued"
            row.cancel_requested = False

    async def cancel(self, audit_run_id: str, reason: str) -> None:
        row = await self.get(audit_run_id)
        if row:
            row.cancel_requested = True
            row.metadata_json = {**(row.metadata_json or {}), "cancel_reason": reason}

    async def claim_next_queued(self, *, worker_id: str) -> AuditRun | None:
        row = await self.session.scalar(select(AuditRun).where(AuditRun.status == "queued").order_by(AuditRun.updated_at.asc()).limit(1))
        if row is None:
            return None
        row.status = "running"
        row.pipeline_status = "running"
        row.worker_id = worker_id
        row.config_json = {
            **(row.config_json or {}),
            "runtime_control": {
                **((row.config_json or {}).get("runtime_control") or {}),
                "worker_id": worker_id,
            },
        }
        return row

    async def set_pipeline_state(self, audit_run_id: str, *, status: str, current_stage: str | None = None, error: str | None = None) -> None:
        row = await self.get(audit_run_id)
        if row is None:
            return
        row.pipeline_status = status
        row.current_stage = current_stage
        if status in {"succeeded", "completed"}:
            row.status = "completed"
        elif status in {"failed", "cancelled"}:
            row.status = status
        elif status in {"running", "queued"}:
            row.status = status
        if error:
            row.metadata_json = {**(row.metadata_json or {}), "pipeline_error": error}


class PipelineRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.audit_runs = AuditRunRepository(session)

    async def create_run(self, audit_run_id: str) -> PipelineRun:
        row = PipelineRun(
            pipeline_run_id=new_id("pipe"),
            audit_run_id=audit_run_id,
            status="running",
            started_at=datetime.now(timezone.utc),
        )
        self.session.add(row)
        return row

    async def record_stage(
        self,
        *,
        pipeline_run_id: str,
        audit_run_id: str,
        stage: str,
        status: str,
        summary: dict[str, Any] | None = None,
        artifact_ids: list[str] | None = None,
        error: str | None = None,
    ) -> PipelineStageRun:
        row = PipelineStageRun(
            pipeline_run_id=pipeline_run_id,
            audit_run_id=audit_run_id,
            stage=stage,
            status=status,
            started_at=datetime.now(timezone.utc),
            completed_at=datetime.now(timezone.utc),
            summary_json=summary or {},
            artifact_ids=artifact_ids or [],
            error=error,
        )
        self.session.add(row)
        return row

    async def finish_run(self, pipeline_run_id: str, status: str, summary: dict[str, Any] | None = None, error: str | None = None) -> None:
        row = await self.session.scalar(select(PipelineRun).where(PipelineRun.pipeline_run_id == pipeline_run_id))
        if row:
            row.status = status
            row.completed_at = datetime.now(timezone.utc)
            row.summary_json = summary or {}
            row.error = error


class EventRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def append(self, *, audit_run_id: str, subject: str, event_type: str, payload: dict[str, Any]) -> AuditEvent:
        row = AuditEvent(audit_run_id=audit_run_id, subject=subject, event_type=event_type, payload_json=payload)
        self.session.add(row)
        return row


class SnapshotRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create_ready(self, *, project_id: str, workspace_path: str, source_type: str = "git", source_ref: str | None = None) -> ProjectSnapshot:
        row = ProjectSnapshot(
            snapshot_id=new_id("snapshot"),
            project_id=project_id,
            source_type=source_type,
            source_ref=source_ref,
            workspace_path=workspace_path,
            status="ready",
            metadata_json={"schema_version": 1},
        )
        self.session.add(row)
        return row


class WorkerHeartbeatRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def upsert(
        self,
        *,
        worker_id: str,
        service_name: str,
        hostname: str,
        status: str,
        current_audit_run_id: str | None,
        metadata: dict[str, Any] | None = None,
    ) -> WorkerHeartbeat:
        row = await self.session.scalar(select(WorkerHeartbeat).where(WorkerHeartbeat.worker_id == worker_id))
        if row is None:
            row = WorkerHeartbeat(
                worker_id=worker_id,
                service_name=service_name,
                hostname=hostname,
                status=status,
                last_seen_at=datetime.now(timezone.utc),
                current_audit_run_id=current_audit_run_id,
                metadata_json={"schema_version": 1, **(metadata or {})},
            )
            self.session.add(row)
        else:
            row.status = status
            row.last_seen_at = datetime.now(timezone.utc)
            row.current_audit_run_id = current_audit_run_id
            row.metadata_json = {**(row.metadata_json or {}), **(metadata or {})}
        return row
