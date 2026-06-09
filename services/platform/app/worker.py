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
    _get_audit_run,
    _is_cancel_requested,
    _judge_audit_run_internal,
    _list_findings,
    _mark_audit_run_status,
    _raise_if_cancelled,
    _record_audit_run_event,
    _record_pipeline_event,
    _record_pipeline_summary,
    _run_sca_mcp,
    _run_semgrep_mcp,
    _set_pipeline_state,
)
from app.repositories import init_db
from app.runtime import RuntimeOrchestrator
from app.services.pipeline_executor import PipelineExecutor
from app.services.pipeline_queue import claim_next_queued_pipeline
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
        run_sca=_run_sca_mcp,
        run_semgrep=_run_semgrep_mcp,
        judge_audit_run=_judge_audit_run_internal,
        generate_report=_generate_report_internal,
        compact_event_payload=_compact_event_payload,
    )


async def run_worker() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    settings = get_settings()
    worker_id = f"{settings.service_name}-{socket.gethostname()}-{uuid.uuid4().hex[:8]}"
    stop_event = asyncio.Event()

    def request_stop() -> None:
        stop_event.set()

    loop = asyncio.get_running_loop()
    for signum in (signal.SIGINT, signal.SIGTERM):
        with contextlib.suppress(NotImplementedError):
            loop.add_signal_handler(signum, request_stop)

    await init_db()
    runtime = RuntimeOrchestrator(settings)
    executor = build_pipeline_executor(settings, runtime)
    logger.info("workflow worker started worker_id=%s backend=%s", worker_id, settings.pipeline_execution_backend)
    try:
        while not stop_event.is_set():
            claimed = await claim_next_queued_pipeline(worker_id=worker_id)
            if not claimed:
                with contextlib.suppress(asyncio.TimeoutError):
                    await asyncio.wait_for(stop_event.wait(), timeout=settings.pipeline_worker_poll_interval_seconds)
                continue
            audit_run_id = claimed["audit_run_id"]
            logger.info("claimed audit pipeline audit_run_id=%s worker_id=%s", audit_run_id, worker_id)
            try:
                await executor.execute(audit_run_id)
            except Exception:
                logger.exception("pipeline execution crashed audit_run_id=%s", audit_run_id)
                await _mark_audit_run_status(audit_run_id, "failed")
                await _set_pipeline_state(audit_run_id, stage="failed", status="failed", error="workflow worker crashed")
                await _record_audit_run_event(audit_run_id, "pipeline_failed", {"error": "workflow worker crashed"})
    finally:
        await runtime.close()
        logger.info("workflow worker stopped worker_id=%s", worker_id)


def main() -> None:
    asyncio.run(run_worker())


if __name__ == "__main__":
    main()
