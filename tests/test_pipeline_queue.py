from __future__ import annotations

import pytest

from app.domain.models import AuditRun
from app.services import pipeline_queue


@pytest.mark.asyncio
async def test_claim_next_queued_pipeline_marks_run_claimed(monkeypatch: pytest.MonkeyPatch) -> None:
    audit_run = AuditRun(
        audit_run_id="run-1",
        project_id="project-1",
        status="queued",
        config={"pipeline_state": {"stage": "queued", "status": "queued"}},
    )
    session = _FakeSession(audit_run)
    monkeypatch.setattr(pipeline_queue, "SessionLocal", lambda: session)

    claimed = await pipeline_queue.claim_next_queued_pipeline(worker_id="worker-1")

    assert claimed == {"audit_run_id": "run-1"}
    assert audit_run.status == "running"
    assert audit_run.config["pipeline_state"]["stage"] == "claimed"
    assert audit_run.config["pipeline_state"]["status"] == "running"
    assert audit_run.config["runtime_control"]["worker_id"] == "worker-1"
    assert session.committed is True
    assert session.added[0].event_type == "pipeline_claimed"


@pytest.mark.asyncio
async def test_claim_next_queued_pipeline_returns_none_when_queue_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    session = _FakeSession(None)
    monkeypatch.setattr(pipeline_queue, "SessionLocal", lambda: session)

    claimed = await pipeline_queue.claim_next_queued_pipeline(worker_id="worker-1")

    assert claimed is None
    assert session.committed is True
    assert session.added == []


class _FakeBegin:
    def __init__(self, session: "_FakeSession") -> None:
        self.session = session

    async def __aenter__(self):
        return self.session

    async def __aexit__(self, exc_type, exc, traceback):
        if exc_type is None:
            self.session.committed = True
        return False


class _FakeSession:
    def __init__(self, audit_run: AuditRun | None) -> None:
        self.audit_run = audit_run
        self.added = []
        self.committed = False

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        return False

    def begin(self):
        return _FakeBegin(self)

    async def scalar(self, statement):
        return self.audit_run

    def add(self, row) -> None:
        self.added.append(row)
