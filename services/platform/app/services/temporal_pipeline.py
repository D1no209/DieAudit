from __future__ import annotations

import asyncio
import contextlib
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

try:  # pragma: no cover - import availability is tested through helpers.
    from temporalio.common import RetryPolicy
    from temporalio import activity, workflow
    from temporalio.client import Client
    from temporalio.worker import Worker
except Exception:  # pragma: no cover
    RetryPolicy = None  # type: ignore[assignment]
    activity = None  # type: ignore[assignment]
    workflow = None  # type: ignore[assignment]
    Client = None  # type: ignore[assignment]
    Worker = None  # type: ignore[assignment]


TERMINAL_AUDIT_STATUSES = {"completed", "completed_with_warnings", "failed", "cancelled"}
TEMPORAL_PIPELINE_WORKFLOW = "DieAuditPipelineWorkflow"
TEMPORAL_PIPELINE_STAGES = [
    "joern-cpg",
    "agent-audit",
    "code-analysis",
    "sca",
    "semgrep",
    "source-sink-analysis",
    "validators",
    "judgement",
    "poc-writing",
    "poc-verification",
    "report",
]
PREPARE_PIPELINE_ACTIVITY = "dieaudit.prepare_pipeline"
RUN_PIPELINE_STAGE_ACTIVITY = "dieaudit.run_pipeline_stage"
FINALIZE_PIPELINE_ACTIVITY = "dieaudit.finalize_pipeline"
FAIL_PIPELINE_ACTIVITY = "dieaudit.fail_pipeline"
COMPLETE_VALIDATOR_STAGE_ACTIVITY = "dieaudit.complete_validator_stage"
TEMPORAL_VALIDATOR_ATTEMPT_ACTIVITY = "dieaudit.validator_attempt"
TEMPORAL_SWARM_AGENT_ACTIVITY = "dieaudit.swarm_agent"
TEMPORAL_COMPLETE_SWARM_STAGE_ACTIVITY = "dieaudit.complete_swarm_stage"
SHORT_ACTIVITY_RETRY_POLICY = RetryPolicy(maximum_attempts=3) if RetryPolicy is not None else None
AGENT_ACTIVITY_RETRY_POLICY = RetryPolicy(maximum_attempts=2) if RetryPolicy is not None else None
ACTIVITY_HEARTBEAT_INTERVAL_SECONDS = 10.0
SessionLocal = None


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


async def run_temporal_worker(config: TemporalPipelineConfig, *, executor: Any | None = None, stop_event: asyncio.Event | None = None) -> None:
    if Worker is None:
        raise RuntimeError("temporalio package is not installed")
    if executor is None:
        raise RuntimeError("Temporal pipeline worker requires a PipelineExecutor")
    client = await connect_temporal_client(config)
    pipeline_activities = TemporalPipelineActivities(executor)
    worker = Worker(
        client,
        task_queue=config.task_queue,
        workflows=[DieAuditPipelineWorkflow],
        activities=[
            pipeline_activities.prepare_pipeline,
            pipeline_activities.run_pipeline_stage,
            pipeline_activities.run_swarm_agent,
            pipeline_activities.complete_swarm_stage,
            pipeline_activities.run_validator_attempt,
            pipeline_activities.complete_validator_stage,
            pipeline_activities.finalize_pipeline,
            pipeline_activities.fail_pipeline,
        ],
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
            prepare_result = await workflow.execute_activity(
                PREPARE_PIPELINE_ACTIVITY,
                audit_run_id,
                start_to_close_timeout=timedelta(seconds=30),
                retry_policy=SHORT_ACTIVITY_RETRY_POLICY,
            )
            steps: list[dict[str, Any]] = []
            judge_result: dict[str, Any] = {}
            report_result: dict[str, Any] = {}
            try:
                for stage in TEMPORAL_PIPELINE_STAGES:
                    stage_result = await workflow.execute_activity(
                        RUN_PIPELINE_STAGE_ACTIVITY,
                        {"audit_run_id": audit_run_id, "stage": stage, "steps": steps},
                        start_to_close_timeout=timedelta(days=7),
                        heartbeat_timeout=timedelta(seconds=30),
                        retry_policy=AGENT_ACTIVITY_RETRY_POLICY,
                        activity_id=f"{audit_run_id}-stage-{stage}",
                    )
                    if stage_result.get("append_to_steps", True) and stage_result.get("step"):
                        steps.append({"step": stage_result["step"], "result": stage_result.get("result")})
                    fanout = stage_result.get("temporal_fanout") if isinstance(stage_result.get("temporal_fanout"), dict) else {}
                    if fanout.get("kind") == "validator-attempts":
                        validator_result = await self._run_validator_fanout(audit_run_id, fanout)
                        if validator_result.get("append_to_steps", True) and validator_result.get("step"):
                            steps.append({"step": validator_result["step"], "result": validator_result.get("result")})
                    elif fanout.get("kind") == "source-sink-findings":
                        swarm_result = await self._run_swarm_fanout(audit_run_id, fanout)
                        if swarm_result.get("append_to_steps", True) and swarm_result.get("step"):
                            steps.append({"step": swarm_result["step"], "result": swarm_result.get("result")})
                        if isinstance(swarm_result.get("judge_result"), dict):
                            judge_result = swarm_result["judge_result"]
                    elif fanout.get("kind") == "judger-findings":
                        swarm_result = await self._run_swarm_fanout(audit_run_id, fanout)
                        if swarm_result.get("append_to_steps", True) and swarm_result.get("step"):
                            steps.append({"step": swarm_result["step"], "result": swarm_result.get("result")})
                        if isinstance(swarm_result.get("judge_result"), dict):
                            judge_result = swarm_result["judge_result"]
                    elif fanout.get("kind") in {"poc-writer-findings", "poc-verifier-findings"}:
                        swarm_result = await self._run_swarm_fanout(audit_run_id, fanout)
                        if swarm_result.get("append_to_steps", True) and swarm_result.get("step"):
                            steps.append({"step": swarm_result["step"], "result": swarm_result.get("result")})
                    if isinstance(stage_result.get("judge_result"), dict):
                        judge_result = stage_result["judge_result"]
                    if isinstance(stage_result.get("report_result"), dict):
                        report_result = stage_result["report_result"]
                final_result = await workflow.execute_activity(
                    FINALIZE_PIPELINE_ACTIVITY,
                    {
                        "audit_run_id": audit_run_id,
                        "steps": steps,
                        "judge_result": judge_result,
                        "report_result": report_result,
                    },
                    start_to_close_timeout=timedelta(minutes=10),
                    retry_policy=SHORT_ACTIVITY_RETRY_POLICY,
                )
                return {"audit_run_id": audit_run_id, "prepare": prepare_result, "final": final_result}
            except Exception as exc:
                failure_result = await workflow.execute_activity(
                    FAIL_PIPELINE_ACTIVITY,
                    {"audit_run_id": audit_run_id, "error": str(exc), "steps": steps},
                    start_to_close_timeout=timedelta(minutes=10),
                    retry_policy=SHORT_ACTIVITY_RETRY_POLICY,
                )
                return {"audit_run_id": audit_run_id, "prepare": prepare_result, "failure": failure_result}

        async def _run_validator_fanout(self, audit_run_id: str, fanout: dict[str, Any]) -> dict[str, Any]:
            attempts = list(fanout.get("attempts") or [])
            max_parallel = max(1, int(fanout.get("max_parallel") or 1))
            results: list[dict[str, Any]] = []
            for offset in range(0, len(attempts), max_parallel):
                batch = attempts[offset : offset + max_parallel]
                batch_results = await asyncio.gather(
                    *[
                        workflow.execute_activity(
                            TEMPORAL_VALIDATOR_ATTEMPT_ACTIVITY,
                            attempt,
                            start_to_close_timeout=timedelta(days=7),
                            heartbeat_timeout=timedelta(seconds=30),
                            retry_policy=AGENT_ACTIVITY_RETRY_POLICY,
                            activity_id=str(attempt.get("activity_key") or f"{audit_run_id}-validator-{offset}"),
                        )
                        for attempt in batch
                    ]
                )
                results.extend(batch_results)
            first = attempts[0] if attempts else {}
            return await workflow.execute_activity(
                COMPLETE_VALIDATOR_STAGE_ACTIVITY,
                {
                    "audit_run_id": audit_run_id,
                    "project_id": first.get("project_id"),
                    "validator_rounds": first.get("validator_rounds"),
                    "max_parallel_validators": max_parallel,
                    "validator_agent_name": first.get("validator_agent_name"),
                    "results": results,
                },
                start_to_close_timeout=timedelta(minutes=10),
                retry_policy=SHORT_ACTIVITY_RETRY_POLICY,
                activity_id=f"{audit_run_id}-complete-validators",
            )

        async def _run_swarm_fanout(self, audit_run_id: str, fanout: dict[str, Any]) -> dict[str, Any]:
            attempts = list(fanout.get("attempts") or [])
            max_parallel = max(1, int(fanout.get("max_parallel") or 1))
            stage = str(fanout.get("stage") or "")
            kind = str(fanout.get("kind") or "")
            activity_kind = {
                "source-sink-findings": "source-sink-finding",
                "judger-findings": "judger-finding",
                "poc-writer-findings": "poc-writer-finding",
                "poc-verifier-findings": "poc-verifier-finding",
            }.get(kind, kind)
            results: list[dict[str, Any]] = []
            for offset in range(0, len(attempts), max_parallel):
                batch = attempts[offset : offset + max_parallel]
                batch_results = await asyncio.gather(
                    *[
                        workflow.execute_activity(
                            TEMPORAL_SWARM_AGENT_ACTIVITY,
                            {"kind": activity_kind, **attempt},
                            start_to_close_timeout=timedelta(days=7),
                            heartbeat_timeout=timedelta(seconds=30),
                            retry_policy=AGENT_ACTIVITY_RETRY_POLICY,
                            activity_id=str(attempt.get("activity_key") or f"{audit_run_id}-{activity_kind}-{offset}"),
                        )
                        for attempt in batch
                    ]
                )
                results.extend(batch_results)
            return await workflow.execute_activity(
                TEMPORAL_COMPLETE_SWARM_STAGE_ACTIVITY,
                {"audit_run_id": audit_run_id, "stage": stage, "kind": kind, "max_parallel": max_parallel, "results": results},
                start_to_close_timeout=timedelta(minutes=10),
                retry_policy=SHORT_ACTIVITY_RETRY_POLICY,
                activity_id=f"{audit_run_id}-complete-{stage}",
            )

else:

    class DieAuditPipelineWorkflow:  # type: ignore[no-redef]
        async def run(self, audit_run_id: str) -> dict[str, Any]:
            raise RuntimeError("temporalio package is not installed")


class TemporalPipelineActivities:
    def __init__(self, executor: Any) -> None:
        self.executor = executor

    if activity is not None:

        @activity.defn(name=PREPARE_PIPELINE_ACTIVITY)
        async def prepare_pipeline(self, audit_run_id: str) -> dict[str, Any]:
            return await self.executor.prepare_temporal_pipeline(audit_run_id)

        @activity.defn(name=RUN_PIPELINE_STAGE_ACTIVITY)
        async def run_pipeline_stage(self, payload: dict[str, Any]) -> dict[str, Any]:
            audit_run_id = str(payload["audit_run_id"])
            stage = str(payload["stage"])
            return await _await_with_activity_heartbeat(
                self.executor.execute_temporal_stage(
                    audit_run_id,
                    stage,
                    list(payload.get("steps") or []),
                ),
                {
                    "audit_run_id": audit_run_id,
                    "activity": RUN_PIPELINE_STAGE_ACTIVITY,
                    "stage": stage,
                },
            )

        @activity.defn(name=TEMPORAL_SWARM_AGENT_ACTIVITY)
        async def run_swarm_agent(self, payload: dict[str, Any]) -> dict[str, Any]:
            return await _await_with_activity_heartbeat(
                self.executor.execute_temporal_swarm_agent(payload),
                _agent_activity_heartbeat_payload(payload, TEMPORAL_SWARM_AGENT_ACTIVITY),
            )

        @activity.defn(name=TEMPORAL_COMPLETE_SWARM_STAGE_ACTIVITY)
        async def complete_swarm_stage(self, payload: dict[str, Any]) -> dict[str, Any]:
            return await self.executor.complete_temporal_swarm_stage(payload)

        @activity.defn(name=TEMPORAL_VALIDATOR_ATTEMPT_ACTIVITY)
        async def run_validator_attempt(self, payload: dict[str, Any]) -> dict[str, Any]:
            return await _await_with_activity_heartbeat(
                self.executor.execute_temporal_validator_attempt(payload),
                _agent_activity_heartbeat_payload(payload, TEMPORAL_VALIDATOR_ATTEMPT_ACTIVITY),
            )

        @activity.defn(name=COMPLETE_VALIDATOR_STAGE_ACTIVITY)
        async def complete_validator_stage(self, payload: dict[str, Any]) -> dict[str, Any]:
            return await self.executor.complete_temporal_validator_stage(
                str(payload["audit_run_id"]),
                project_id=str(payload.get("project_id") or ""),
                validator_rounds=int(payload.get("validator_rounds") or 0),
                max_parallel_validators=int(payload.get("max_parallel_validators") or 1),
                validator_agent_name=str(payload.get("validator_agent_name") or ""),
                results=list(payload.get("results") or []),
            )

        @activity.defn(name=FINALIZE_PIPELINE_ACTIVITY)
        async def finalize_pipeline(self, payload: dict[str, Any]) -> dict[str, Any]:
            return await self.executor.finalize_temporal_pipeline(
                str(payload["audit_run_id"]),
                steps=list(payload.get("steps") or []),
                judge_result=dict(payload.get("judge_result") or {}),
                report_result=dict(payload.get("report_result") or {}),
            )

        @activity.defn(name=FAIL_PIPELINE_ACTIVITY)
        async def fail_pipeline(self, payload: dict[str, Any]) -> dict[str, Any]:
            return await self.executor.fail_temporal_pipeline(
                str(payload["audit_run_id"]),
                error=str(payload.get("error") or "Temporal pipeline failed"),
                steps=list(payload.get("steps") or []),
            )

    else:

        async def prepare_pipeline(self, audit_run_id: str) -> dict[str, Any]:
            return await self.executor.prepare_temporal_pipeline(audit_run_id)

        async def run_pipeline_stage(self, payload: dict[str, Any]) -> dict[str, Any]:
            return await self.executor.execute_temporal_stage(
                str(payload["audit_run_id"]),
                str(payload["stage"]),
                list(payload.get("steps") or []),
            )

        async def run_swarm_agent(self, payload: dict[str, Any]) -> dict[str, Any]:
            return await self.executor.execute_temporal_swarm_agent(payload)

        async def complete_swarm_stage(self, payload: dict[str, Any]) -> dict[str, Any]:
            return await self.executor.complete_temporal_swarm_stage(payload)

        async def run_validator_attempt(self, payload: dict[str, Any]) -> dict[str, Any]:
            return await self.executor.execute_temporal_validator_attempt(payload)

        async def complete_validator_stage(self, payload: dict[str, Any]) -> dict[str, Any]:
            return await self.executor.complete_temporal_validator_stage(
                str(payload["audit_run_id"]),
                project_id=str(payload.get("project_id") or ""),
                validator_rounds=int(payload.get("validator_rounds") or 0),
                max_parallel_validators=int(payload.get("max_parallel_validators") or 1),
                validator_agent_name=str(payload.get("validator_agent_name") or ""),
                results=list(payload.get("results") or []),
            )

        async def finalize_pipeline(self, payload: dict[str, Any]) -> dict[str, Any]:
            return await self.executor.finalize_temporal_pipeline(
                str(payload["audit_run_id"]),
                steps=list(payload.get("steps") or []),
                judge_result=dict(payload.get("judge_result") or {}),
                report_result=dict(payload.get("report_result") or {}),
            )

        async def fail_pipeline(self, payload: dict[str, Any]) -> dict[str, Any]:
            return await self.executor.fail_temporal_pipeline(
                str(payload["audit_run_id"]),
                error=str(payload.get("error") or "Temporal pipeline failed"),
                steps=list(payload.get("steps") or []),
            )


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
    from sqlalchemy import select

    from app.domain.models import AuditRun, AuditRunEvent

    session_factory = _session_local()
    async with session_factory() as session:
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
    from sqlalchemy import select

    from app.domain.models import AuditRun

    session_factory = _session_local()
    while True:
        async with session_factory() as session:
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


def _session_local() -> Any:
    if SessionLocal is not None:
        return SessionLocal
    from app.repositories import SessionLocal as imported_session_local

    return imported_session_local


def _agent_activity_heartbeat_payload(payload: dict[str, Any], activity_name: str) -> dict[str, Any]:
    finding = payload.get("finding") if isinstance(payload.get("finding"), dict) else {}
    return {
        "audit_run_id": payload.get("audit_run_id"),
        "activity": activity_name,
        "activity_key": payload.get("activity_key"),
        "kind": payload.get("kind"),
        "finding_id": finding.get("finding_id"),
        "round_index": payload.get("round_index"),
    }


async def _await_with_activity_heartbeat(awaitable: Any, payload: dict[str, Any]) -> Any:
    if activity is None:
        return await awaitable

    stop = asyncio.Event()

    async def heartbeat_loop() -> None:
        while not stop.is_set():
            _activity_heartbeat({**payload, "status": "running"})
            with contextlib.suppress(asyncio.TimeoutError):
                await asyncio.wait_for(stop.wait(), timeout=ACTIVITY_HEARTBEAT_INTERVAL_SECONDS)

    _activity_heartbeat({**payload, "status": "started"})
    task = asyncio.create_task(heartbeat_loop())
    try:
        result = await awaitable
    except Exception:
        _activity_heartbeat({**payload, "status": "failed"})
        raise
    finally:
        stop.set()
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
    _activity_heartbeat({**payload, "status": "completed"})
    return result


def _activity_heartbeat(payload: dict[str, Any]) -> None:
    if activity is None:
        return
    with contextlib.suppress(Exception):
        activity.heartbeat({key: value for key, value in payload.items() if value is not None})
