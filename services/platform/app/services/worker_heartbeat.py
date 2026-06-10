from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import delete, select

from app.domain.models import WorkerHeartbeat
from app.repositories import SessionLocal


ACTIVE_WORKER_STATUSES = {"starting", "idle", "running"}


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def worker_heartbeat_to_dict(row: WorkerHeartbeat, *, now: datetime | None = None) -> dict[str, Any]:
    now = now or utc_now()
    last_seen_at = ensure_aware(row.last_seen_at)
    return {
        "worker_id": row.worker_id,
        "service_name": row.service_name,
        "hostname": row.hostname,
        "status": row.status,
        "last_seen_at": last_seen_at.isoformat(),
        "age_seconds": max(0.0, (now - last_seen_at).total_seconds()),
        "current_audit_run_id": row.current_audit_run_id,
        "metadata": row.metadata_json or {},
    }


def summarize_worker_health(
    rows: list[WorkerHeartbeat],
    *,
    now: datetime | None = None,
    max_age_seconds: float = 30.0,
) -> dict[str, Any]:
    now = now or utc_now()
    workers = [worker_heartbeat_to_dict(row, now=now) for row in rows]
    active_workers = [
        worker
        for worker in workers
        if worker["status"] in ACTIVE_WORKER_STATUSES and worker["age_seconds"] <= max_age_seconds
    ]
    stale_workers = [
        worker
        for worker in workers
        if worker["status"] in ACTIVE_WORKER_STATUSES and worker["age_seconds"] > max_age_seconds
    ]
    stopped_workers = [worker for worker in workers if worker["status"] not in ACTIVE_WORKER_STATUSES]
    return {
        "ok": bool(active_workers),
        "max_age_seconds": max_age_seconds,
        "active_count": len(active_workers),
        "stale_count": len(stale_workers),
        "stopped_count": len(stopped_workers),
        "workers": workers,
        "message": "At least one workflow worker heartbeat is fresh."
        if active_workers
        else "No fresh workflow-worker heartbeat is available.",
    }


def worker_heartbeat_retention_cutoff(*, now: datetime, retention_seconds: float | None) -> datetime | None:
    if retention_seconds is None or retention_seconds <= 0:
        return None
    return now - timedelta(seconds=retention_seconds)


async def record_worker_heartbeat(
    *,
    worker_id: str,
    service_name: str,
    hostname: str,
    status: str,
    current_audit_run_id: str | None = None,
    metadata: dict[str, Any] | None = None,
    seen_at: datetime | None = None,
    retention_seconds: float | None = None,
    session_factory: Callable = SessionLocal,
) -> dict[str, Any]:
    seen_at = seen_at or utc_now()
    async with session_factory() as session:
        row = await session.scalar(select(WorkerHeartbeat).where(WorkerHeartbeat.worker_id == worker_id))
        if row is None:
            row = WorkerHeartbeat(
                worker_id=worker_id,
                service_name=service_name,
                hostname=hostname,
                status=status,
                last_seen_at=seen_at,
                current_audit_run_id=current_audit_run_id,
                metadata_json=metadata or {},
            )
            session.add(row)
        else:
            row.service_name = service_name
            row.hostname = hostname
            row.status = status
            row.last_seen_at = seen_at
            row.current_audit_run_id = current_audit_run_id
            row.metadata_json = metadata or {}
        cutoff = worker_heartbeat_retention_cutoff(now=seen_at, retention_seconds=retention_seconds)
        if cutoff is not None:
            await session.execute(
                delete(WorkerHeartbeat).where(
                    WorkerHeartbeat.worker_id != worker_id,
                    WorkerHeartbeat.last_seen_at < cutoff,
                )
            )
        await session.commit()
        return worker_heartbeat_to_dict(row, now=seen_at)


async def list_worker_heartbeats(
    *,
    service_name: str | None = "workflow-worker",
    session_factory: Callable = SessionLocal,
) -> list[dict[str, Any]]:
    now = utc_now()
    async with session_factory() as session:
        statement = select(WorkerHeartbeat).order_by(WorkerHeartbeat.last_seen_at.desc())
        if service_name:
            statement = statement.where(WorkerHeartbeat.service_name == service_name)
        rows = (await session.execute(statement)).scalars().all()
    return [worker_heartbeat_to_dict(row, now=now) for row in rows]


async def workflow_worker_health(
    *,
    max_age_seconds: float = 30.0,
    session_factory: Callable = SessionLocal,
) -> dict[str, Any]:
    async with session_factory() as session:
        rows = (
            (await session.execute(select(WorkerHeartbeat).where(WorkerHeartbeat.service_name == "workflow-worker")))
            .scalars()
            .all()
        )
    return summarize_worker_health(rows, max_age_seconds=max_age_seconds)


def ensure_aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
