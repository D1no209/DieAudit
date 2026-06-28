from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from dieaudit_common.domain.enums import FailurePolicy
from dieaudit_common.schemas.pipeline import StageResult

from app.pipeline.context import PipelineContext


class NoopStage:
    def __init__(
        self,
        name: str,
        *,
        depends_on: tuple[str, ...] = (),
        failure_policy: FailurePolicy = FailurePolicy.FAIL_FAST,
        concurrency_key: str | None = None,
    ) -> None:
        self.name = name
        self.depends_on = depends_on
        self.failure_policy = failure_policy
        self.concurrency_key = concurrency_key

    async def enabled(self, ctx: PipelineContext) -> bool:
        disabled = set(ctx.config.get("disabled_stages") or [])
        return self.name not in disabled

    async def run(self, ctx: PipelineContext) -> StageResult:
        now = datetime.now(timezone.utc)
        return StageResult(
            stage=self.name,
            status="succeeded",
            started_at=now,
            completed_at=now,
            summary={"mode": "skeleton", "message": f"{self.name} stage completed by DAG skeleton"},
        )


def default_stages() -> list[NoopStage]:
    return [
        NoopStage("snapshot-ready"),
        NoopStage("structure-discovery", depends_on=("snapshot-ready",)),
        NoopStage("agent-audit", depends_on=("structure-discovery",)),
        NoopStage("code-analysis", depends_on=("agent-audit",)),
        NoopStage("whiteboard-swarm", depends_on=("code-analysis",), failure_policy=FailurePolicy.CONTINUE_WITH_WARNING),
        NoopStage("validation-judgement", depends_on=("whiteboard-swarm",)),
        NoopStage("feedback-loop", depends_on=("validation-judgement",), failure_policy=FailurePolicy.CONTINUE_WITH_WARNING),
        NoopStage("poc-writer-fanout", depends_on=("feedback-loop",)),
        NoopStage("poc-verifier-fanout", depends_on=("poc-writer-fanout",)),
        NoopStage("report", depends_on=("poc-verifier-fanout",)),
        NoopStage("runtime-cleanup", depends_on=("report",), failure_policy=FailurePolicy.ALWAYS_RUN),
    ]
