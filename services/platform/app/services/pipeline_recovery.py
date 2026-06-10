from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select

from app.domain.models import AuditRun, AuditRunEvent, WorkerHeartbeat
from app.repositories import SessionLocal
from app.services.worker_heartbeat import ACTIVE_WORKER_STATUSES, ensure_aware


ACTIVE_AUDIT_STATUSES = {"queued", "running", "validating", "cancelling"}
ACTIVE_PIPELINE_STATUSES = {"queued", "running", "validating", "cancelling"}


def is_active_pipeline(status: str | None, config: dict[str, Any] | None, *, include_queued: bool = True) -> bool:
    audit_statuses = ACTIVE_AUDIT_STATUSES if include_queued else ACTIVE_AUDIT_STATUSES - {"queued"}
    pipeline_statuses = ACTIVE_PIPELINE_STATUSES if include_queued else ACTIVE_PIPELINE_STATUSES - {"queued"}
    if status in audit_statuses:
        return True
    pipeline_state = (config or {}).get("pipeline_state") or {}
    return pipeline_state.get("status") in pipeline_statuses


def interrupted_pipeline_config(
    config: dict[str, Any] | None,
    *,
    service_name: str,
    recovered_at: datetime,
    reason: str,
) -> dict[str, Any]:
    updated = dict(config or {})
    previous_state = dict(updated.get("pipeline_state") or {})
    updated["pipeline_state"] = {
        "stage": "interrupted",
        "status": "failed",
        "error": reason,
        "previous": previous_state,
        "recovered_by": service_name,
        "recovered_at": recovered_at.isoformat(),
    }
    runtime_control = dict(updated.get("runtime_control") or {})
    runtime_control["cancel_requested"] = False
    runtime_control["interrupted_on_startup"] = True
    updated["runtime_control"] = runtime_control
    return updated


async def recover_interrupted_pipelines(
    *,
    service_name: str,
    session_factory: Callable = SessionLocal,
    recovered_at: datetime | None = None,
    include_queued: bool = True,
    worker_heartbeat_ttl_seconds: float = 30.0,
) -> dict[str, Any]:
    recovered_at = recovered_at or datetime.now(timezone.utc)
    reason = f"{service_name} restarted while pipeline was active; background execution cannot be resumed automatically"
    recovered: list[dict[str, Any]] = []
    skipped_active: list[dict[str, Any]] = []
    async with session_factory() as session:
        workers = list((await session.execute(select(WorkerHeartbeat))).scalars())
        rows = list((await session.execute(select(AuditRun))).scalars())
        for row in rows:
            if not is_active_pipeline(row.status, row.config, include_queued=include_queued):
                continue
            active_worker = _active_worker_for_pipeline(
                row,
                workers,
                now=recovered_at,
                max_age_seconds=worker_heartbeat_ttl_seconds,
            )
            if active_worker:
                skipped_active.append(
                    {
                        "audit_run_id": row.audit_run_id,
                        "worker_id": active_worker.worker_id,
                        "last_seen_at": ensure_aware(active_worker.last_seen_at).isoformat(),
                    }
                )
                continue
            previous_status = row.status
            previous_state = dict((row.config or {}).get("pipeline_state") or {})
            row.status = "failed"
            row.config = interrupted_pipeline_config(
                row.config,
                service_name=service_name,
                recovered_at=recovered_at,
                reason=reason,
            )
            session.add(
                AuditRunEvent(
                    audit_run_id=row.audit_run_id,
                    event_type="pipeline_interrupted",
                    payload={
                        "reason": reason,
                        "previous_status": previous_status,
                        "previous_state": previous_state,
                        "recovered_by": service_name,
                        "recovered_at": recovered_at.isoformat(),
                    },
                )
            )
            recovered.append(
                {
                    "audit_run_id": row.audit_run_id,
                    "previous_status": previous_status,
                    "previous_state": previous_state,
                }
            )
        await session.commit()
    return {"recovered": len(recovered), "runs": recovered, "skipped_active": skipped_active}


def _active_worker_for_pipeline(
    audit_run: AuditRun,
    workers: list[WorkerHeartbeat],
    *,
    now: datetime,
    max_age_seconds: float,
) -> WorkerHeartbeat | None:
    worker_id = _pipeline_worker_id(audit_run.config)
    for worker in workers:
        if worker.status not in ACTIVE_WORKER_STATUSES:
            continue
        if worker.current_audit_run_id != audit_run.audit_run_id:
            continue
        if worker_id and worker.worker_id != worker_id:
            continue
        age_seconds = (now - ensure_aware(worker.last_seen_at)).total_seconds()
        if age_seconds <= max_age_seconds:
            return worker
    return None


def _pipeline_worker_id(config: dict[str, Any] | None) -> str | None:
    runtime_control = (config or {}).get("runtime_control") or {}
    pipeline_state = (config or {}).get("pipeline_state") or {}
    worker_id = runtime_control.get("worker_id") or pipeline_state.get("worker_id")
    return str(worker_id) if worker_id else None
