from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from dieaudit_common.domain.models import AuditRun
from dieaudit_common.events.nats import NullEventPublisher
from dieaudit_common.persistence.repositories import EventRepository, PipelineRepository

from app.pipeline.context import PipelineContext
from app.pipeline.executor import PipelineExecutor
from app.pipeline.registry import StageRegistry
from app.pipeline.stages.default import default_stages


class PipelineService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def run(self, audit_run: AuditRun) -> dict:
        pipeline_repo = PipelineRepository(self.session)
        pipeline_run = await pipeline_repo.create_run(audit_run.audit_run_id)
        audit_run.status = "running"
        audit_run.pipeline_status = "running"
        ctx = PipelineContext(
            audit_run_id=audit_run.audit_run_id,
            pipeline_run_id=pipeline_run.pipeline_run_id,
            project_id=audit_run.project_id,
            snapshot_id=audit_run.snapshot_id,
            workspace_path=audit_run.workspace_path,
            config=audit_run.config_json or {},
            input_payload=audit_run.input_payload or {},
            cancelled=audit_run.cancel_requested,
        )
        executor = PipelineExecutor(
            registry=StageRegistry(default_stages()),
            pipeline_repo=pipeline_repo,
            event_repo=EventRepository(self.session),
            publisher=NullEventPublisher(),
        )
        result = await executor.execute(ctx)
        audit_run.status = "failed" if result["status"] == "failed" else "succeeded"
        audit_run.pipeline_status = result["status"]
        audit_run.current_stage = None
        return result
