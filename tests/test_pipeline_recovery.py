from __future__ import annotations

from datetime import datetime, timezone

from app.api.routes import _is_active_pipeline_state
from app.services.pipeline_recovery import interrupted_pipeline_config, is_active_pipeline


def test_active_pipeline_detects_audit_status() -> None:
    assert is_active_pipeline("running", {}) is True
    assert is_active_pipeline("completed", {"pipeline_state": {"status": "completed"}}) is False


def test_active_pipeline_detects_pipeline_state_even_when_audit_status_is_stale() -> None:
    assert is_active_pipeline("created", {"pipeline_state": {"status": "queued"}}) is True
    assert _is_active_pipeline_state({"pipeline_state": {"status": "running"}}) is True
    assert _is_active_pipeline_state({"pipeline_state": {"status": "failed"}}) is False


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
