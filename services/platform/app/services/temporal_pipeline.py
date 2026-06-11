from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from sqlalchemy import select

from app.domain.models import AuditRun, AuditRunEvent
from app.repositories import SessionLocal

try:  # pragma: no cover - import availability is tested through helpers.
    from temporalio import activity, workflow
    from temporalio.client import Client
    from temporalio.worker import Worker
except Exception:  # pragma: no cover
    activity = None  # type: ignore[assignment]
    workflow = None  # type: ignore[assignment]
    Client = None  # type: ignore[assignment]
    Worker = None  # type: ignore[assignment]


TERMINAL_AUDIT_STATUSES = {"completed", "completed_with_warnings", "failed", "cancelled"}
TEMPORAL_PIPELINE_WORKFLOW = "DieAuditPipelineWorkflow"


@dataclass(frozen=True)
class TemporalPipelineConfig:
    address: str
    namespace: str
    task_queue: str


async def connect_temporal_client(config: TemporalPipelineConfig) -> Any:
    if Client is None:
        raise RuntimeError("temporalio package is not installed")
    return await Client.connect(config.address, namespace=config.namespace)


async def start_temporal_pipeline(audit_run_id: str, config: TemporalPipelineConfig) -> dict[str, Any]:
    client = await connect_temporal_client(config)
    workflow_id = temporal_workflow_id(audit_run_id)
    handle = await client.start_workflow(
        DieAuditPipelineWorkflow.run,
        audit_run_id,
        id=workflow_id,
        task_queue=config.task_queue,
    )
    return {
        "audit_run_id": audit_run_id,
        "workflow_id": handle.id,
        "run_id": handle.result_run_id,
        "task_queue": config.task_queue,
        "namespace": config.namespace,
    }


def temporal_workflow_id(audit_run_id: str) -> str:
    return f"dieaudit-audit-run-{audit_run_id}"


async def run_temporal_worker(config: TemporalPipelineConfig, *, stop_event: asyncio.Event | None = None) -> None:
    if Worker is None:
        raise RuntimeError("temporalio package is not installed")
    client = await connect_temporal_client(config)
    worker = Worker(
        client,
        task_queue=config.task_queue,
        workflows=[DieAuditPipelineWorkflow],
        activities=[enqueue_pipeline_activity, wait_for_pipeline_completion_activity],
    )
    if stop_event is None:
        await worker.run()
        return
    worker_task = asyncio.create_task(worker.run())
    stop_task = asyncio.create_task(stop_event.wait())
    done, pending = await asyncio.wait({worker_task, stop_task}, return_when=asyncio.FIRST_COMPLETED)
    for task in pending:
        task.cancel()
    if worker_task in done:
        worker_task.result()


if workflow is not None:

    @workflow.defn
    class DieAuditPipelineWorkflow:
        @workflow.run
        async def run(self, audit_run_id: str) -> dict[str, Any]:
            enqueue_result = await workflow.execute_activity(
                enqueue_pipeline_activity,
                audit_run_id,
                start_to_close_timeout=timedelta(seconds=30),
            )
            completion = await workflow.execute_activity(
                wait_for_pipeline_completion_activity,
                audit_run_id,
                start_to_close_timeout=timedelta(days=7),
                heartbeat_timeout=timedelta(seconds=30),
            )
            return {"audit_run_id": audit_run_id, "enqueue": enqueue_result, "completion": completion}

else:

    class DieAuditPipelineWorkflow:  # type: ignore[no-redef]
        async def run(self, audit_run_id: str) -> dict[str, Any]:
            raise RuntimeError("temporalio package is not installed")


if activity is not None:

    @activity.defn
    async def enqueue_pipeline_activity(audit_run_id: str) -> dict[str, Any]:
        return await enqueue_pipeline_for_worker(audit_run_id)

    @activity.defn
    async def wait_for_pipeline_completion_activity(audit_run_id: str) -> dict[str, Any]:
        return await wait_for_pipeline_completion(audit_run_id)

else:

    async def enqueue_pipeline_activity(audit_run_id: str) -> dict[str, Any]:
        return await enqueue_pipeline_for_worker(audit_run_id)

    async def wait_for_pipeline_completion_activity(audit_run_id: str) -> dict[str, Any]:
        return await wait_for_pipeline_completion(audit_run_id)


async def enqueue_pipeline_for_worker(audit_run_id: str) -> dict[str, Any]:
    async with SessionLocal() as session:
        async with session.begin():
            audit_run = await session.scalar(select(AuditRun).where(AuditRun.audit_run_id == audit_run_id))
            if not audit_run:
                raise RuntimeError(f"audit run not found: {audit_run_id}")
            config = dict(audit_run.config or {})
            pipeline_state = dict(config.get("pipeline_state") or {})
            if audit_run.status not in {"queued", "running"}:
                audit_run.status = "queued"
            pipeline_state.update({"stage": "queued", "status": "queued", "backend": "temporal"})
            config["pipeline_state"] = pipeline_state
            config["temporal"] = {"workflow_id": temporal_workflow_id(audit_run_id)}
            audit_run.config = config
            session.add(
                AuditRunEvent(
                    audit_run_id=audit_run_id,
                    event_type="temporal_pipeline_enqueued",
                    payload={"workflow_id": temporal_workflow_id(audit_run_id)},
                )
            )
    return {"audit_run_id": audit_run_id, "status": "queued", "workflow_id": temporal_workflow_id(audit_run_id)}


async def wait_for_pipeline_completion(audit_run_id: str, *, poll_seconds: float = 2.0) -> dict[str, Any]:
    while True:
        async with SessionLocal() as session:
            audit_run = await session.scalar(select(AuditRun).where(AuditRun.audit_run_id == audit_run_id))
            if not audit_run:
                raise RuntimeError(f"audit run not found: {audit_run_id}")
            status = str(audit_run.status or "")
            config = dict(audit_run.config or {})
            if status in TERMINAL_AUDIT_STATUSES:
                return {
                    "audit_run_id": audit_run_id,
                    "status": status,
                    "pipeline_state": config.get("pipeline_state") or {},
                }
        if activity is not None:
            activity.heartbeat({"audit_run_id": audit_run_id, "status": status})
        await asyncio.sleep(max(0.2, poll_seconds))
