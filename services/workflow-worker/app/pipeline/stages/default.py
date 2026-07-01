from __future__ import annotations

from datetime import datetime, timezone
from collections.abc import Awaitable, Callable
from typing import Any

from dieaudit_common.domain.enums import FailurePolicy
from dieaudit_common.schemas.pipeline import StageResult

from app.pipeline.context import PipelineContext


StageRunner = Callable[[PipelineContext, str], Awaitable[dict[str, Any]]]


class ServiceStage:
    def __init__(
        self,
        name: str,
        *,
        depends_on: tuple[str, ...] = (),
        failure_policy: FailurePolicy = FailurePolicy.FAIL_FAST,
        concurrency_key: str | None = None,
        runner: StageRunner | None = None,
    ) -> None:
        self.name = name
        self.depends_on = depends_on
        self.failure_policy = failure_policy
        self.concurrency_key = concurrency_key
        self.runner = runner

    async def enabled(self, ctx: PipelineContext) -> bool:
        disabled = set(ctx.config.get("disabled_stages") or [])
        return self.name not in disabled

    async def run(self, ctx: PipelineContext) -> StageResult:
        now = datetime.now(timezone.utc)
        summary = await self.runner(ctx, self.name) if self.runner else self._planned_summary()
        return StageResult(
            stage=self.name,
            status="succeeded",
            started_at=now,
            completed_at=datetime.now(timezone.utc),
            summary=summary,
        )

    def _planned_summary(self) -> dict[str, Any]:
        return {
            "mode": "registry-only",
            "message": f"{self.name} stage is registered; production execution injects a stage adapter runner",
        }


def default_stages(runner: StageRunner | None = None) -> list[ServiceStage]:
    return [
        ServiceStage("snapshot-ready", runner=runner),
        ServiceStage("structure-discovery", depends_on=("snapshot-ready",), runner=runner),
        ServiceStage("agent-audit", depends_on=("structure-discovery",), runner=runner),
        ServiceStage("code-analysis", depends_on=("agent-audit",), runner=runner),
        ServiceStage("value-triage", depends_on=("code-analysis",), runner=runner),
        ServiceStage("whiteboard-swarm", depends_on=("value-triage",), failure_policy=FailurePolicy.CONTINUE_WITH_WARNING, runner=runner),
        ServiceStage("validation-judgement", depends_on=("whiteboard-swarm",), runner=runner),
        ServiceStage("feedback-loop", depends_on=("validation-judgement",), failure_policy=FailurePolicy.CONTINUE_WITH_WARNING, runner=runner),
        ServiceStage("poc-writing", depends_on=("feedback-loop",), runner=runner),
        ServiceStage("poc-verification", depends_on=("poc-writing",), runner=runner),
        ServiceStage("report", depends_on=("poc-verification",), runner=runner),
        ServiceStage("runtime-cleanup", depends_on=("report",), failure_policy=FailurePolicy.ALWAYS_RUN, runner=runner),
    ]
