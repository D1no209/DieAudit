from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import socket
import uuid

from dieaudit_common.persistence.base import SessionLocal
from dieaudit_common.persistence.repositories import AuditRunRepository, WorkerHeartbeatRepository
from dieaudit_common.settings import get_settings

from app.application.pipeline_service import PipelineService

logger = logging.getLogger("dieaudit.workflow_worker")


async def run_worker() -> None:
    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
    settings = get_settings()
    worker_id = os.getenv("WORKER_ID") or f"workflow-{socket.gethostname()}-{uuid.uuid4().hex[:8]}"
    hostname = socket.gethostname()
    current_audit_run_id: str | None = None
    status = "starting"
    stop_event = asyncio.Event()

    async def heartbeat() -> None:
        nonlocal status, current_audit_run_id
        while not stop_event.is_set():
            async with SessionLocal() as session:
                await WorkerHeartbeatRepository(session).upsert(
                    worker_id=worker_id,
                    service_name="workflow-worker",
                    hostname=hostname,
                    status=status,
                    current_audit_run_id=current_audit_run_id,
                    metadata={"pipeline_model": "dag-registry"},
                )
                await session.commit()
            with contextlib.suppress(asyncio.TimeoutError):
                await asyncio.wait_for(stop_event.wait(), timeout=5)

    heartbeat_task = asyncio.create_task(heartbeat())
    logger.info("workflow-worker started worker_id=%s", worker_id)
    try:
        status = "idle"
        while not stop_event.is_set():
            async with SessionLocal() as session:
                repo = AuditRunRepository(session)
                claimed = await repo.claim_next_queued(worker_id=worker_id)
                if claimed is None:
                    await session.commit()
                    with contextlib.suppress(asyncio.TimeoutError):
                        await asyncio.wait_for(stop_event.wait(), timeout=2)
                    continue
                audit_run_id = claimed.audit_run_id
                current_audit_run_id = audit_run_id
                status = "running"
                await session.commit()
            try:
                async with SessionLocal() as session:
                    audit_run = await AuditRunRepository(session).get(audit_run_id)
                    if audit_run is None:
                        continue
                    await PipelineService(session).run(audit_run)
                    await session.commit()
            except Exception:
                logger.exception("pipeline execution crashed audit_run_id=%s", audit_run_id)
                async with SessionLocal() as session:
                    await AuditRunRepository(session).set_pipeline_state(audit_run_id, status="failed", current_stage=None, error="workflow worker crashed")
                    await session.commit()
            finally:
                current_audit_run_id = None
                status = "idle"
    finally:
        status = "stopped"
        stop_event.set()
        heartbeat_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await heartbeat_task


def main() -> None:
    asyncio.run(run_worker())


if __name__ == "__main__":
    main()
