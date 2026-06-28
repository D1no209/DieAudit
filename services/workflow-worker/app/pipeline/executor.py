from __future__ import annotations

from dieaudit_common.domain.enums import FailurePolicy
from dieaudit_common.domain.events import (
    AUDIT_RUN_STAGE_COMPLETED,
    AUDIT_RUN_STAGE_FAILED,
    AUDIT_RUN_STAGE_STARTED,
    AUDIT_RUN_STARTED,
    DomainEvent,
)
from dieaudit_common.events.nats import NullEventPublisher
from dieaudit_common.persistence.repositories import EventRepository, PipelineRepository

from app.pipeline.context import PipelineContext
from app.pipeline.registry import StageRegistry


class PipelineExecutor:
    def __init__(
        self,
        *,
        registry: StageRegistry,
        pipeline_repo: PipelineRepository,
        event_repo: EventRepository,
        publisher: NullEventPublisher,
    ) -> None:
        self.registry = registry
        self.pipeline_repo = pipeline_repo
        self.event_repo = event_repo
        self.publisher = publisher

    async def execute(self, ctx: PipelineContext) -> dict:
        await self._emit(AUDIT_RUN_STARTED, "audit_run.started", ctx, {"status": "running"})
        completed: list[dict] = []
        failed = False
        for stage in self.registry.ordered():
            if ctx.cancelled:
                break
            if not await stage.enabled(ctx):
                await self.pipeline_repo.record_stage(
                    pipeline_run_id=ctx.pipeline_run_id,
                    audit_run_id=ctx.audit_run_id,
                    stage=stage.name,
                    status="skipped",
                    summary={"reason": "disabled"},
                )
                continue
            await self._emit(AUDIT_RUN_STAGE_STARTED, "audit_run.stage.started", ctx, {"stage": stage.name})
            try:
                result = await stage.run(ctx)
            except Exception as exc:
                if stage.failure_policy == FailurePolicy.CONTINUE_WITH_WARNING:
                    result_status = "warning"
                else:
                    result_status = "failed"
                    failed = True
                await self.pipeline_repo.record_stage(
                    pipeline_run_id=ctx.pipeline_run_id,
                    audit_run_id=ctx.audit_run_id,
                    stage=stage.name,
                    status=result_status,
                    error=str(exc),
                )
                await self._emit(AUDIT_RUN_STAGE_FAILED, "audit_run.stage.failed", ctx, {"stage": stage.name, "error": str(exc)})
                if stage.failure_policy == FailurePolicy.FAIL_FAST:
                    break
                continue
            await self.pipeline_repo.record_stage(
                pipeline_run_id=ctx.pipeline_run_id,
                audit_run_id=ctx.audit_run_id,
                stage=result.stage,
                status=result.status,
                summary=result.summary,
                artifact_ids=result.artifact_ids,
                error=result.error,
            )
            completed.append(result.model_dump(mode="json"))
            await self._emit(
                AUDIT_RUN_STAGE_COMPLETED,
                "audit_run.stage.completed",
                ctx,
                {"stage": result.stage, "status": result.status, "summary": result.summary},
            )
        status = "failed" if failed else "succeeded"
        await self.pipeline_repo.finish_run(ctx.pipeline_run_id, status, {"stages": completed})
        return {"status": status, "stages": completed}

    async def _emit(self, subject: str, event_type: str, ctx: PipelineContext, payload: dict) -> None:
        event = DomainEvent(subject=subject, event_type=event_type, audit_run_id=ctx.audit_run_id, payload=payload)
        await self.event_repo.append(audit_run_id=ctx.audit_run_id, subject=subject, event_type=event_type, payload=event.to_payload())
        await self.publisher.publish(event)
