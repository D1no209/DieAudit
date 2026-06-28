from __future__ import annotations

from collections import defaultdict, deque
from collections.abc import Iterable
from typing import Protocol

from dieaudit_common.domain.enums import FailurePolicy
from dieaudit_common.schemas.pipeline import StageResult

from app.pipeline.context import PipelineContext


class PipelineStage(Protocol):
    name: str
    depends_on: tuple[str, ...]
    failure_policy: FailurePolicy
    concurrency_key: str | None

    async def enabled(self, ctx: PipelineContext) -> bool: ...

    async def run(self, ctx: PipelineContext) -> StageResult: ...


class StageRegistry:
    def __init__(self, stages: Iterable[PipelineStage]) -> None:
        self.stages = {stage.name: stage for stage in stages}

    def ordered(self) -> list[PipelineStage]:
        indegree = {name: 0 for name in self.stages}
        children: dict[str, list[str]] = defaultdict(list)
        for stage in self.stages.values():
            for dependency in stage.depends_on:
                if dependency not in self.stages:
                    raise ValueError(f"stage {stage.name} depends on unknown stage {dependency}")
                indegree[stage.name] += 1
                children[dependency].append(stage.name)
        queue = deque(sorted(name for name, degree in indegree.items() if degree == 0))
        ordered: list[str] = []
        while queue:
            name = queue.popleft()
            ordered.append(name)
            for child in sorted(children[name]):
                indegree[child] -= 1
                if indegree[child] == 0:
                    queue.append(child)
        if len(ordered) != len(self.stages):
            raise ValueError("pipeline stage graph contains a cycle")
        return [self.stages[name] for name in ordered]
