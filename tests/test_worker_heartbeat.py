from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.domain.models import WorkerHeartbeat
from app.services.worker_heartbeat import summarize_worker_health, worker_heartbeat_retention_cutoff, worker_heartbeat_to_dict


def test_worker_health_passes_with_fresh_active_worker() -> None:
    now = datetime(2026, 6, 10, 12, 0, tzinfo=timezone.utc)
    row = WorkerHeartbeat(
        worker_id="worker-1",
        service_name="workflow-worker",
        hostname="host",
        status="idle",
        last_seen_at=now - timedelta(seconds=5),
        metadata_json={"backend": "workflow-worker"},
    )

    health = summarize_worker_health([row], now=now, max_age_seconds=30)

    assert health["ok"] is True
    assert health["active_count"] == 1
    assert health["stale_count"] == 0


def test_worker_health_fails_when_active_worker_is_stale() -> None:
    now = datetime(2026, 6, 10, 12, 0, tzinfo=timezone.utc)
    row = WorkerHeartbeat(
        worker_id="worker-1",
        service_name="workflow-worker",
        hostname="host",
        status="running",
        last_seen_at=now - timedelta(seconds=31),
        current_audit_run_id="run-1",
    )

    health = summarize_worker_health([row], now=now, max_age_seconds=30)

    assert health["ok"] is False
    assert health["active_count"] == 0
    assert health["stale_count"] == 1


def test_worker_health_ignores_stopped_worker_for_readiness() -> None:
    now = datetime(2026, 6, 10, 12, 0, tzinfo=timezone.utc)
    row = WorkerHeartbeat(
        worker_id="worker-1",
        service_name="workflow-worker",
        hostname="host",
        status="stopped",
        last_seen_at=now,
    )

    health = summarize_worker_health([row], now=now, max_age_seconds=30)

    assert health["ok"] is False
    assert health["stopped_count"] == 1


def test_worker_heartbeat_to_dict_normalizes_naive_datetimes() -> None:
    now = datetime(2026, 6, 10, 12, 0, tzinfo=timezone.utc)
    row = WorkerHeartbeat(
        worker_id="worker-1",
        service_name="workflow-worker",
        hostname="host",
        status="idle",
        last_seen_at=datetime(2026, 6, 10, 11, 59, 55),
    )

    result = worker_heartbeat_to_dict(row, now=now)

    assert result["last_seen_at"].endswith("+00:00")
    assert result["age_seconds"] == 5


def test_worker_heartbeat_retention_cutoff_uses_configured_seconds() -> None:
    now = datetime(2026, 6, 10, 12, 0, tzinfo=timezone.utc)

    cutoff = worker_heartbeat_retention_cutoff(now=now, retention_seconds=3600)

    assert cutoff == now - timedelta(seconds=3600)


def test_worker_heartbeat_retention_cutoff_disabled_for_non_positive_values() -> None:
    now = datetime(2026, 6, 10, 12, 0, tzinfo=timezone.utc)

    assert worker_heartbeat_retention_cutoff(now=now, retention_seconds=0) is None
    assert worker_heartbeat_retention_cutoff(now=now, retention_seconds=None) is None
