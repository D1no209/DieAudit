from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select

from app.domain.models import AuditRun, AuditRunEvent
from app.repositories import SessionLocal


ACTIVE_AUDIT_STATUSES = {"queued", "running", "validating", "cancelling"}
ACTIVE_PIPELINE_STATUSES = {"queued", "running", "validating", "cancelling"}


def is_active_pipeline(status: str | None, config: dict[str, Any] | None) -> bool:
    if status in ACTIVE_AUDIT_STATUSES:
        return True
    pipeline_state = (config or {}).get("pipeline_state") or {}
    return pipeline_state.get("status") in ACTIVE_PIPELINE_STATUSES


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
) -> dict[str, Any]:
    recovered_at = recovered_at or datetime.now(timezone.utc)
    reason = f"{service_name} restarted while pipeline was active; background execution cannot be resumed automatically"
    recovered: list[dict[str, Any]] = []
    async with session_factory() as session:
        rows = (await session.execute(select(AuditRun))).scalars()
        for row in rows:
            if not is_active_pipeline(row.status, row.config):
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
    return {"recovered": len(recovered), "runs": recovered}
