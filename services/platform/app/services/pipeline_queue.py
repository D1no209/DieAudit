from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select

from app.domain.models import AuditRun, AuditRunEvent
from app.repositories import SessionLocal


async def claim_next_queued_pipeline(*, worker_id: str) -> dict[str, Any] | None:
    claimed_at = datetime.now(timezone.utc).isoformat()
    async with SessionLocal() as session:
        async with session.begin():
            query = (
                select(AuditRun)
                .where(AuditRun.status == "queued")
                .order_by(AuditRun.created_at.asc())
                .with_for_update(skip_locked=True)
                .limit(1)
            )
            audit_run = await session.scalar(query)
            if not audit_run:
                return None
            config = dict(audit_run.config or {})
            runtime_control = dict(config.get("runtime_control") or {})
            runtime_control.update(
                {
                    "worker_id": worker_id,
                    "claimed_at": claimed_at,
                }
            )
            config["runtime_control"] = runtime_control
            config["pipeline_state"] = {
                "stage": "claimed",
                "status": "running",
                "worker_id": worker_id,
                "claimed_at": claimed_at,
            }
            audit_run.status = "running"
            audit_run.config = config
            session.add(
                AuditRunEvent(
                    audit_run_id=audit_run.audit_run_id,
                    event_type="pipeline_claimed",
                    payload={"worker_id": worker_id, "claimed_at": claimed_at},
                )
            )
            return {"audit_run_id": audit_run.audit_run_id}
