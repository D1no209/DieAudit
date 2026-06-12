from __future__ import annotations

import asyncio
import contextlib
import logging
import signal
import socket
import uuid

from app.api.routes import (
    _cancel_reason,
    _compact_event_payload,
    _generate_report_internal,
    _generate_pocs_internal,
    _get_audit_run,
    _is_cancel_requested,
    _judge_audit_run_internal,
    _list_findings,
    _mark_audit_run_status,
    _raise_if_cancelled,
    _record_audit_run_event,
    _record_pipeline_event,
    _record_pipeline_summary,
    _run_code_batch_analysis,
    _run_joern_mcp,
    _run_sca_mcp,
    _run_semgrep_mcp,
    _run_source_sink_analysis,
    _set_pipeline_state,
    _verify_pocs_internal,
)
from app.repositories import init_db
from app.runtime import RuntimeOrchestrator
from app.services.pipeline_executor import PipelineExecutor
from app.services.pipeline_queue import claim_next_queued_pipeline
from app.services.pipeline_recovery import recover_interrupted_pipelines
from app.services.temporal_pipeline import TemporalPipelineConfig, run_temporal_worker
from app.services.worker_heartbeat import record_worker_heartbeat
from app.settings import get_settings


logger = logging.getLogger("dieaudit.workflow_worker")


def build_pipeline_executor(settings, runtime: RuntimeOrchestrator) -> PipelineExecutor:
    return PipelineExecutor(
        settings=settings,
        runtime=runtime,
        get_audit_run=_get_audit_run,
        mark_audit_run_status=_mark_audit_run_status,
        set_pipeline_state=_set_pipeline_state,
        record_audit_run_event=_record_audit_run_event,
        record_pipeline_event=_record_pipeline_event,
        record_pipeline_summary=_record_pipeline_summary,
        raise_if_cancelled=_raise_if_cancelled,
        is_cancel_requested=_is_cancel_requested,
        cancel_reason=_cancel_reason,
        list_findings=_list_findings,
        run_joern=_run_joern_mcp,
        run_code_batch_analysis=_run_code_batch_analysis,
        run_source_sink_analysis=_run_source_sink_analysis,
        run_sca=_run_sca_mcp,
        run_semgrep=_run_semgrep_mcp,
        judge_audit_run=_judge_audit_run_internal,
        generate_pocs=_generate_pocs_internal,
        verify_pocs=_verify_pocs_internal,
        generate_report=_generate_report_internal,
        compact_event_payload=_compact_event_payload,
    )


async def run_worker() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    settings = get_settings()
    hostname = socket.gethostname()
    worker_id = f"{settings.service_name}-{hostname}-{uuid.uuid4().hex[:8]}"
    stop_event = asyncio.Event()
    current_audit_run_id: str | None = None
    worker_status = "starting"

    def request_stop() -> None:
        stop_event.set()

    loop = asyncio.get_running_loop()
    for signum in (signal.SIGINT, signal.SIGTERM):
        with contextlib.suppress(NotImplementedError):
            loop.add_signal_handler(signum, request_stop)

    await init_db()
    if settings.pipeline_recovery_on_startup:
        recovery = await recover_interrupted_pipelines(
            service_name=settings.service_name,
            include_queued=False,
            worker_heartbeat_ttl_seconds=settings.pipeline_worker_heartbeat_ttl_seconds,
        )
        if recovery.get("recovered"):
            logger.warning("recovered interrupted worker pipelines result=%s", recovery)
    runtime = RuntimeOrchestrator(settings)
    executor = build_pipeline_executor(settings, runtime)
    heartbeat_interval = max(1.0, settings.pipeline_worker_heartbeat_interval_seconds)

    async def heartbeat_loop() -> None:
        while not stop_event.is_set():
            try:
                await record_worker_heartbeat(
                    worker_id=worker_id,
                    service_name=settings.service_name,
                    hostname=hostname,
                    status=worker_status,
                    current_audit_run_id=current_audit_run_id,
                    metadata={
                        "backend": settings.pipeline_execution_backend,
                        "poll_interval_seconds": settings.pipeline_worker_poll_interval_seconds,
                    },
                    retention_seconds=settings.pipeline_worker_heartbeat_retention_seconds,
                )
            except Exception:
                logger.exception("failed to record worker heartbeat worker_id=%s", worker_id)
            with contextlib.suppress(asyncio.TimeoutError):
                await asyncio.wait_for(stop_event.wait(), timeout=heartbeat_interval)

    heartbeat_task = asyncio.create_task(heartbeat_loop())
    temporal_task: asyncio.Task | None = None
    if (settings.pipeline_execution_backend or "").strip().lower() == "temporal":
        temporal_task = asyncio.create_task(
            run_temporal_worker(
                TemporalPipelineConfig(
                    address=settings.temporal_address,
                    namespace=settings.temporal_namespace,
                    task_queue=settings.temporal_task_queue,
                ),
                executor=executor,
                stop_event=stop_event,
            )
        )
    logger.info("workflow worker started worker_id=%s backend=%s", worker_id, settings.pipeline_execution_backend)
    try:
        worker_status = "idle"
        while not stop_event.is_set():
            if temporal_task is not None:
                if temporal_task.done():
                    temporal_task.result()
                with contextlib.suppress(asyncio.TimeoutError):
                    await asyncio.wait_for(stop_event.wait(), timeout=settings.pipeline_worker_poll_interval_seconds)
                continue
            claimed = await claim_next_queued_pipeline(worker_id=worker_id)
            if not claimed:
                with contextlib.suppress(asyncio.TimeoutError):
                    await asyncio.wait_for(stop_event.wait(), timeout=settings.pipeline_worker_poll_interval_seconds)
                continue
            audit_run_id = claimed["audit_run_id"]
            current_audit_run_id = audit_run_id
            worker_status = "running"
            logger.info("claimed audit pipeline audit_run_id=%s worker_id=%s", audit_run_id, worker_id)
            try:
                await executor.execute(audit_run_id)
            except Exception:
                logger.exception("pipeline execution crashed audit_run_id=%s", audit_run_id)
                await _mark_audit_run_status(audit_run_id, "failed")
                await _set_pipeline_state(audit_run_id, stage="failed", status="failed", error="workflow worker crashed")
                await _record_audit_run_event(audit_run_id, "pipeline_failed", {"error": "workflow worker crashed"})
            finally:
                current_audit_run_id = None
                worker_status = "idle"
    finally:
        worker_status = "stopped"
        stop_event.set()
        with contextlib.suppress(Exception):
            await record_worker_heartbeat(
                worker_id=worker_id,
                service_name=settings.service_name,
                hostname=hostname,
                status=worker_status,
                current_audit_run_id=None,
                metadata={"backend": settings.pipeline_execution_backend},
                retention_seconds=settings.pipeline_worker_heartbeat_retention_seconds,
            )
        heartbeat_task.cancel()
        if temporal_task is not None:
            temporal_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await heartbeat_task
        if temporal_task is not None:
            with contextlib.suppress(asyncio.CancelledError):
                await temporal_task
        await runtime.close()
        logger.info("workflow worker stopped worker_id=%s", worker_id)


def main() -> None:
    asyncio.run(run_worker())


if __name__ == "__main__":
    main()
