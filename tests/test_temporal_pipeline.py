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
