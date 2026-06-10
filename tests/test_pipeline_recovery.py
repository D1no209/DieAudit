from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.domain.models import AuditRun
from app.services.pipeline_recovery import interrupted_pipeline_config, is_active_pipeline, recover_interrupted_pipelines


def test_active_pipeline_detects_audit_status() -> None:
    assert is_active_pipeline("running", {}) is True
    assert is_active_pipeline("completed", {"pipeline_state": {"status": "completed"}}) is False


def test_active_pipeline_detects_pipeline_state_even_when_audit_status_is_stale() -> None:
    assert is_active_pipeline("created", {"pipeline_state": {"status": "queued"}}) is True
    assert is_active_pipeline("created", {"pipeline_state": {"status": "running"}}) is True
    assert is_active_pipeline("created", {"pipeline_state": {"status": "failed"}}) is False


def test_active_pipeline_can_preserve_durable_queue_entries() -> None:
    assert is_active_pipeline("queued", {}, include_queued=False) is False
    assert is_active_pipeline("created", {"pipeline_state": {"status": "queued"}}, include_queued=False) is False
    assert is_active_pipeline("created", {"pipeline_state": {"status": "running"}}, include_queued=False) is True


def test_interrupted_pipeline_config_preserves_previous_state_and_clears_cancel_request() -> None:
    recovered_at = datetime(2026, 6, 10, 1, 2, 3, tzinfo=timezone.utc)
    config = {
        "pipeline_state": {"stage": "validators", "status": "running"},
        "runtime_control": {"cancel_requested": True, "cancel_reason": "user_requested"},
    }

    updated = interrupted_pipeline_config(
        config,
        service_name="agent-gateway",
        recovered_at=recovered_at,
        reason="restart",
    )

    assert updated["pipeline_state"]["stage"] == "interrupted"
    assert updated["pipeline_state"]["status"] == "failed"
    assert updated["pipeline_state"]["previous"] == {"stage": "validators", "status": "running"}
    assert updated["pipeline_state"]["recovered_by"] == "agent-gateway"
    assert updated["runtime_control"]["cancel_requested"] is False
    assert updated["runtime_control"]["interrupted_on_startup"] is True


@pytest.mark.asyncio
async def test_recover_interrupted_pipelines_handles_stale_audit_status() -> None:
    stale = AuditRun(
        audit_run_id="run-stale",
        project_id="project-1",
        status="created",
        config={"pipeline_state": {"stage": "validators", "status": "running"}},
    )
    completed = AuditRun(
        audit_run_id="run-completed",
        project_id="project-1",
        status="completed",
        config={"pipeline_state": {"stage": "completed", "status": "completed"}},
    )
    session = _FakeSession([stale, completed])

    result = await recover_interrupted_pipelines(
        service_name="agent-gateway",
        session_factory=lambda: session,
        recovered_at=datetime(2026, 6, 10, 1, 2, 3, tzinfo=timezone.utc),
    )

    assert result["recovered"] == 1
    assert result["runs"][0]["audit_run_id"] == "run-stale"
    assert stale.status == "failed"
    assert stale.config["pipeline_state"]["stage"] == "interrupted"
    assert stale.config["pipeline_state"]["previous"] == {"stage": "validators", "status": "running"}
    assert completed.status == "completed"
    assert session.committed is True
    assert len(session.added) == 1
    assert session.added[0].event_type == "pipeline_interrupted"


@pytest.mark.asyncio
async def test_recover_interrupted_pipelines_preserves_queued_when_configured() -> None:
    queued = AuditRun(
        audit_run_id="run-queued",
        project_id="project-1",
        status="queued",
        config={"pipeline_state": {"stage": "queued", "status": "queued"}},
    )
    running = AuditRun(
        audit_run_id="run-running",
        project_id="project-1",
        status="running",
        config={"pipeline_state": {"stage": "validators", "status": "running"}},
    )
    session = _FakeSession([queued, running])

    result = await recover_interrupted_pipelines(
        service_name="workflow-worker",
        session_factory=lambda: session,
        recovered_at=datetime(2026, 6, 10, 1, 2, 3, tzinfo=timezone.utc),
        include_queued=False,
    )

    assert result["recovered"] == 1
    assert result["runs"][0]["audit_run_id"] == "run-running"
    assert queued.status == "queued"
    assert queued.config["pipeline_state"]["status"] == "queued"
    assert running.status == "failed"
    assert len(session.added) == 1


class _FakeScalarResult:
    def __init__(self, rows: list[AuditRun]) -> None:
        self._rows = rows

    def scalars(self) -> list[AuditRun]:
        return self._rows


class _FakeSession:
    def __init__(self, rows: list[AuditRun]) -> None:
        self._rows = rows
        self.added = []
        self.committed = False

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        return False

    async def execute(self, statement):
        return _FakeScalarResult(self._rows)

    def add(self, row) -> None:
        self.added.append(row)

    async def commit(self) -> None:
        self.committed = True
