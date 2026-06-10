from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from app.services.pipeline_executor import PipelineExecutor


class FakeRuntime:
    def __init__(self) -> None:
        self.agent_runs: list[dict[str, Any]] = []
        self.validator_runs: list[dict[str, Any]] = []
        self.cleanup_runs: list[str] = []

    async def start_agent_run(self, **kwargs: Any) -> dict[str, Any]:
        self.agent_runs.append(kwargs)
        return {"ok": True, "agent_run_id": "agent-1"}

    async def scale_validators(self, **kwargs: Any) -> dict[str, Any]:
        self.validator_runs.append(kwargs)
        return {"ok": True, "created": len(kwargs.get("findings") or [])}

    async def cleanup_run(self, audit_run_id: str) -> dict[str, Any]:
        self.cleanup_runs.append(audit_run_id)
        return {"audit_run_id": audit_run_id, "removed_containers": [], "removed_networks": []}


class FailingRuntime(FakeRuntime):
    async def start_agent_run(self, **kwargs: Any) -> dict[str, Any]:
        self.agent_runs.append(kwargs)
        raise RuntimeError("agent crashed")


class CallbackRecorder:
    def __init__(self, audit_run: dict[str, Any]) -> None:
        self.audit_run = audit_run
        self.statuses: list[str] = []
        self.pipeline_states: list[dict[str, Any]] = []
        self.events: list[dict[str, Any]] = []
        self.pipeline_events: list[dict[str, Any]] = []
        self.summary: dict[str, Any] | None = None

    async def get_audit_run(self, audit_run_id: str) -> dict[str, Any] | None:
        return self.audit_run

    async def mark_status(self, audit_run_id: str, status: str) -> None:
        self.statuses.append(status)

    async def set_pipeline_state(self, audit_run_id: str, **state: Any) -> None:
        self.pipeline_states.append(state)

    async def record_event(self, audit_run_id: str, event_type: str, payload: dict[str, Any]) -> None:
        self.events.append({"event_type": event_type, "payload": payload})

    async def record_pipeline_event(self, audit_run_id: str, event_type: str, payload: dict[str, Any]) -> None:
        self.pipeline_events.append({"event_type": event_type, "payload": payload})

    async def record_pipeline_summary(self, audit_run_id: str, summary: dict[str, Any]) -> None:
        self.summary = summary

    async def raise_if_cancelled(self, audit_run_id: str) -> None:
        return None

    async def is_cancel_requested(self, audit_run_id: str) -> bool:
        return False

    async def cancel_reason(self, audit_run_id: str) -> str | None:
        return None

    async def list_findings(self, audit_run_id: str) -> list[dict[str, Any]]:
        return [{"finding_id": "finding-1", "title": "test"}]

    async def run_sca(self, *args: Any) -> dict[str, Any]:
        return {"ok": True, "findings_created": 0}

    async def run_semgrep(self, *args: Any) -> dict[str, Any]:
        return {"ok": True, "findings_created": 0}

    async def judge(self, audit_run_id: str, runtime: Any) -> dict[str, Any]:
        return {"ok": True, "decisions": []}

    async def report(self, audit_run_id: str, settings: Any) -> dict[str, Any]:
        return {"ok": True, "report_id": "report-1"}


def build_executor(recorder: CallbackRecorder, runtime: FakeRuntime | None = None) -> PipelineExecutor:
    return PipelineExecutor(
        settings=SimpleNamespace(),
        runtime=runtime or FakeRuntime(),
        get_audit_run=recorder.get_audit_run,
        mark_audit_run_status=recorder.mark_status,
        set_pipeline_state=recorder.set_pipeline_state,
        record_audit_run_event=recorder.record_event,
        record_pipeline_event=recorder.record_pipeline_event,
        record_pipeline_summary=recorder.record_pipeline_summary,
        raise_if_cancelled=recorder.raise_if_cancelled,
        is_cancel_requested=recorder.is_cancel_requested,
        cancel_reason=recorder.cancel_reason,
        list_findings=recorder.list_findings,
        run_sca=recorder.run_sca,
        run_semgrep=recorder.run_semgrep,
        judge_audit_run=recorder.judge,
        generate_report=recorder.report,
        compact_event_payload=lambda value: value,
    )


@pytest.mark.asyncio
async def test_pipeline_executor_marks_missing_workspace_failed() -> None:
    recorder = CallbackRecorder({"audit_run_id": "run-1", "config": {}})

    await build_executor(recorder).execute("run-1")

    assert recorder.statuses == ["failed"]
    assert recorder.pipeline_states == [{"stage": "failed", "status": "failed", "error": "audit run has no workspace path"}]
    assert recorder.events[-1]["event_type"] == "pipeline_failed"


@pytest.mark.asyncio
async def test_pipeline_executor_runs_fixed_pipeline_to_completion() -> None:
    runtime = FakeRuntime()
    recorder = CallbackRecorder(
        {
            "audit_run_id": "run-1",
            "project_id": "project-1",
            "config": {"workspace_host_path": "/workspace/project"},
            "allow_external_network": False,
            "retain_runtime_on_failure": False,
            "validator_rounds": 2,
            "max_parallel_validators": 3,
        }
    )

    await build_executor(recorder, runtime).execute("run-1")

    assert recorder.statuses == ["running", "completed"]
    assert [item["stage"] for item in recorder.pipeline_states] == [
        "agent-audit",
        "sca",
        "semgrep",
        "validators",
        "judgement",
        "report",
        "completed",
    ]
    assert runtime.agent_runs[0]["agent_name"] == "opencode-orchestrator"
    assert runtime.validator_runs[0]["validator_rounds"] == 2
    assert runtime.validator_runs[0]["max_parallel_validators"] == 3
    assert callable(runtime.validator_runs[0]["cancel_requested"])
    assert callable(runtime.validator_runs[0]["cancel_reason"])
    assert runtime.cleanup_runs == ["run-1"]
    assert recorder.summary is not None
    assert recorder.events[-1]["event_type"] == "pipeline_completed"
    assert recorder.pipeline_events[-1]["event_type"] == "runtime_cleanup_completed"


@pytest.mark.asyncio
async def test_pipeline_executor_cleans_runtime_after_failure_by_default() -> None:
    runtime = FailingRuntime()
    recorder = CallbackRecorder(
        {
            "audit_run_id": "run-1",
            "project_id": "project-1",
            "config": {"workspace_host_path": "/workspace/project"},
            "allow_external_network": False,
            "retain_runtime_on_failure": False,
            "validator_rounds": 1,
            "max_parallel_validators": 1,
        }
    )

    await build_executor(recorder, runtime).execute("run-1")

    assert recorder.statuses == ["running", "failed"]
    assert runtime.cleanup_runs == ["run-1"]
    assert recorder.pipeline_events[-1]["event_type"] == "runtime_cleanup_completed"
    assert recorder.pipeline_events[-1]["payload"]["terminal_status"] == "failed"


@pytest.mark.asyncio
async def test_pipeline_executor_retains_runtime_after_failure_when_requested() -> None:
    runtime = FailingRuntime()
    recorder = CallbackRecorder(
        {
            "audit_run_id": "run-1",
            "project_id": "project-1",
            "config": {"workspace_host_path": "/workspace/project"},
            "allow_external_network": False,
            "retain_runtime_on_failure": True,
            "validator_rounds": 1,
            "max_parallel_validators": 1,
        }
    )

    await build_executor(recorder, runtime).execute("run-1")

    assert recorder.statuses == ["running", "failed"]
    assert runtime.cleanup_runs == []
    assert recorder.pipeline_events[-1]["event_type"] == "runtime_cleanup_skipped"
    assert recorder.pipeline_events[-1]["payload"]["reason"] == "retain_runtime_on_failure"
