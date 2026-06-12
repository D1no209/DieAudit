from __future__ import annotations

from typing import Any

import pytest

from app.domain.models import AuditRun, AuditRunEvent
from app.services import temporal_pipeline


class _FakeScalarResult:
    def __init__(self, value: Any) -> None:
        self.value = value

    def scalars(self) -> "_FakeScalarResult":
        return self

    def all(self) -> list[Any]:
        return [self.value] if self.value is not None else []


class _FakeSession:
    def __init__(self, audit_run: AuditRun | None) -> None:
        self.audit_run = audit_run
        self.events: list[AuditRunEvent] = []

    async def __aenter__(self) -> "_FakeSession":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None

    def begin(self) -> "_FakeSession":
        return self

    async def scalar(self, query: Any) -> AuditRun | None:
        return self.audit_run

    async def execute(self, query: Any) -> _FakeScalarResult:
        return _FakeScalarResult(self.audit_run)

    def add(self, row: Any) -> None:
        if isinstance(row, AuditRunEvent):
            self.events.append(row)


@pytest.mark.asyncio
async def test_enqueue_pipeline_for_worker_marks_run_queued(monkeypatch: pytest.MonkeyPatch) -> None:
    audit_run = AuditRun(
        audit_run_id="run-1",
        project_id="project-1",
        status="created",
        config={"pipeline_state": {"stage": "created", "status": "created"}},
    )
    session = _FakeSession(audit_run)
    monkeypatch.setattr(temporal_pipeline, "SessionLocal", lambda: session)

    result = await temporal_pipeline.enqueue_pipeline_for_worker("run-1")

    assert result["status"] == "queued"
    assert result["workflow_id"] == "dieaudit-audit-run-run-1"
    assert audit_run.status == "queued"
    assert audit_run.config["pipeline_state"] == {"stage": "queued", "status": "queued", "backend": "temporal"}
    assert audit_run.config["temporal"]["workflow_id"] == "dieaudit-audit-run-run-1"
    assert session.events[0].event_type == "temporal_pipeline_enqueued"


def test_temporal_workflow_id_is_stable() -> None:
    assert temporal_pipeline.temporal_workflow_id("abc") == "dieaudit-audit-run-abc"


@pytest.mark.asyncio
async def test_temporal_pipeline_activities_call_stage_executor_methods() -> None:
    calls: list[tuple[str, Any]] = []

    class _FakeExecutor:
        async def prepare_temporal_pipeline(self, audit_run_id: str) -> dict[str, Any]:
            calls.append(("prepare", audit_run_id))
            return {"audit_run_id": audit_run_id}

        async def execute_temporal_stage(self, audit_run_id: str, stage: str, steps: list[dict[str, Any]]) -> dict[str, Any]:
            calls.append(("stage", {"audit_run_id": audit_run_id, "stage": stage, "steps": steps}))
            return {"step": stage, "result": {"ok": True}}

        async def finalize_temporal_pipeline(
            self,
            audit_run_id: str,
            *,
            steps: list[dict[str, Any]],
            judge_result: dict[str, Any],
            report_result: dict[str, Any],
        ) -> dict[str, Any]:
            calls.append(("finalize", {"audit_run_id": audit_run_id, "steps": steps, "judge": judge_result, "report": report_result}))
            return {"status": "completed"}

        async def execute_temporal_validator_attempt(self, payload: dict[str, Any]) -> dict[str, Any]:
            calls.append(("validator-attempt", payload))
            return {"status": "completed", "finding_id": payload["finding"]["finding_id"], "round": payload["round_index"]}

        async def complete_temporal_validator_stage(
            self,
            audit_run_id: str,
            *,
            project_id: str,
            validator_rounds: int,
            max_parallel_validators: int,
            validator_agent_name: str,
            results: list[dict[str, Any]],
        ) -> dict[str, Any]:
            calls.append(("validator-complete", {"audit_run_id": audit_run_id, "results": results}))
            return {"step": "validators", "result": {"scheduled": len(results)}}

        async def fail_temporal_pipeline(self, audit_run_id: str, *, error: str, steps: list[dict[str, Any]]) -> dict[str, Any]:
            calls.append(("fail", {"audit_run_id": audit_run_id, "error": error, "steps": steps}))
            return {"status": "failed"}

    activities = temporal_pipeline.TemporalPipelineActivities(_FakeExecutor())

    assert await activities.prepare_pipeline("run-1") == {"audit_run_id": "run-1"}
    assert await activities.run_pipeline_stage({"audit_run_id": "run-1", "stage": "joern-cpg", "steps": []}) == {
        "step": "joern-cpg",
        "result": {"ok": True},
    }
    assert await activities.run_validator_attempt(
        {"audit_run_id": "run-1", "finding": {"finding_id": "finding-1"}, "round_index": 1}
    ) == {"status": "completed", "finding_id": "finding-1", "round": 1}
    assert await activities.complete_validator_stage(
        {
            "audit_run_id": "run-1",
            "project_id": "project-1",
            "validator_rounds": 1,
            "max_parallel_validators": 1,
            "validator_agent_name": "opencode-validator",
            "results": [{"status": "completed"}],
        }
    ) == {"step": "validators", "result": {"scheduled": 1}}
    assert await activities.finalize_pipeline(
        {"audit_run_id": "run-1", "steps": [{"step": "joern-cpg"}], "judge_result": {}, "report_result": {}}
    ) == {"status": "completed"}
    assert await activities.fail_pipeline({"audit_run_id": "run-1", "error": "boom", "steps": []}) == {"status": "failed"}
    assert [item[0] for item in calls] == ["prepare", "stage", "validator-attempt", "validator-complete", "finalize", "fail"]


def test_temporal_workflow_uses_stage_activity_names() -> None:
    source = temporal_pipeline.DieAuditPipelineWorkflow.run.__code__.co_names

    assert "PREPARE_PIPELINE_ACTIVITY" in source
    assert "RUN_PIPELINE_STAGE_ACTIVITY" in source
    assert "_run_validator_fanout" in source
    assert "FINALIZE_PIPELINE_ACTIVITY" in source
    assert "FAIL_PIPELINE_ACTIVITY" in source


@pytest.mark.asyncio
async def test_start_temporal_pipeline_uses_configured_task_queue(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}

    class _FakeHandle:
        id = "workflow-1"
        result_run_id = "run-id-1"

    class _FakeClient:
        async def start_workflow(self, workflow, audit_run_id: str, *, id: str, task_queue: str) -> _FakeHandle:
            captured.update({"audit_run_id": audit_run_id, "id": id, "task_queue": task_queue, "workflow": workflow})
            return _FakeHandle()

    async def fake_connect(config: temporal_pipeline.TemporalPipelineConfig) -> _FakeClient:
        captured["config"] = config
        return _FakeClient()

    monkeypatch.setattr(temporal_pipeline, "connect_temporal_client", fake_connect)

    result = await temporal_pipeline.start_temporal_pipeline(
        "run-1",
        temporal_pipeline.TemporalPipelineConfig(
            address="temporal:7233",
            namespace="default",
            task_queue="queue-1",
        ),
    )

    assert result["workflow_id"] == "workflow-1"
    assert result["run_id"] == "run-id-1"
    assert result["task_queue"] == "queue-1"
    assert captured["id"] == "dieaudit-audit-run-run-1"
    assert captured["task_queue"] == "queue-1"
