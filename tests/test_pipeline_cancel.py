from __future__ import annotations

from app.api.routes import _should_finalize_cancel


def test_cancel_finalizes_when_no_runtime_containers_were_removed() -> None:
    audit_run = {"status": "running", "config": {"pipeline_state": {"status": "running"}}}

    assert _should_finalize_cancel(audit_run, removed_container_count=0) is True


def test_cancel_keeps_cancelling_when_active_runtime_containers_were_removed() -> None:
    audit_run = {"status": "running", "config": {"pipeline_state": {"status": "running"}}}

    assert _should_finalize_cancel(audit_run, removed_container_count=2) is False


def test_cancel_finalizes_for_stale_inactive_pipeline() -> None:
    audit_run = {"status": "completed", "config": {"pipeline_state": {"status": "completed"}}}

    assert _should_finalize_cancel(audit_run, removed_container_count=1) is True
