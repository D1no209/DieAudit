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
        self.agent_result: dict[str, Any] = {"ok": True, "agent_run_id": "agent-1"}
        self.validator_result: dict[str, Any] | None = None

    async def start_agent_run(self, **kwargs: Any) -> dict[str, Any]:
        self.agent_runs.append(kwargs)
        return self.agent_result

    async def scale_validators(self, **kwargs: Any) -> dict[str, Any]:
        self.validator_runs.append(kwargs)
        return self.validator_result or {"ok": True, "created": len(kwargs.get("findings") or []), "status_counts": {"completed": len(kwargs.get("findings") or [])}}

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

    async def run_code_batch_analysis(self, *args: Any) -> dict[str, Any]:
        return {"ok": True, "planned": 2, "completed": 2, "failed": 0, "findings_created": 1}

    async def run_sca(self, *args: Any) -> dict[str, Any]:
        return {"ok": True, "findings_created": 0}

    async def run_semgrep(self, *args: Any) -> dict[str, Any]:
        return {"ok": True, "findings_created": 0}

    async def run_joern(self, *args: Any) -> dict[str, Any]:
        return {
            "ok": True,
            "available": True,
            "status": "completed",
            "cpg_path": "/artifacts/joern/cpg.bin.zip",
            "artifact_id": "joern-artifact",
        }

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
        run_joern=recorder.run_joern,
        run_code_batch_analysis=recorder.run_code_batch_analysis,
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
        "joern-cpg",
        "agent-audit",
        "code-analysis",
        "sca",
        "semgrep",
        "validators",
        "judgement",
        "report",
        "completed",
    ]
    assert runtime.agent_runs[0]["agent_name"] == "opencode-orchestrator"
    joern_input = runtime.agent_runs[0]["input_payload"]["joern"]
    assert joern_input["mcp"] == "joern-mcp"
    assert joern_input["cpg_path"] == "/artifacts/joern/cpg.bin.zip"
    assert joern_input["cpg_artifact_id"] == "joern-artifact"
    assert joern_input["recommended_query_packs"] == ["entrypoints", "authz", "injection", "file-io", "network", "secrets"]
    assert runtime.validator_runs[0]["validator_rounds"] == 2
    assert runtime.validator_runs[0]["max_parallel_validators"] == 3
    assert callable(runtime.validator_runs[0]["cancel_requested"])
    assert callable(runtime.validator_runs[0]["cancel_reason"])
    assert runtime.cleanup_runs == ["run-1"]
    assert recorder.summary is not None
    assert recorder.events[-1]["event_type"] == "pipeline_completed"
    assert recorder.pipeline_events[-1]["event_type"] == "runtime_cleanup_completed"


@pytest.mark.asyncio
async def test_pipeline_executor_marks_completed_with_warnings_for_parse_warning() -> None:
    runtime = FakeRuntime()
    runtime.agent_result = {
        "ok": True,
        "agent_run_id": "agent-1",
        "structured_ingest": {
            "structured_parse_status": "not_found",
            "structured_parse_warnings": [{"kind": "structured_output_not_found"}],
            "findings_created": 0,
        },
    }
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

    assert recorder.statuses == ["running", "completed_with_warnings"]
    assert recorder.pipeline_states[-1] == {"stage": "completed", "status": "completed_with_warnings"}
    assert recorder.events[-1]["event_type"] == "pipeline_completed_with_warnings"
    assert recorder.summary is not None
    assert recorder.summary["result_quality"]["status"] == "warn"


@pytest.mark.asyncio
async def test_pipeline_executor_marks_completed_with_warnings_for_tool_failure() -> None:
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

    async def failing_sca(*args: Any) -> dict[str, Any]:
        return {"ok": False, "available": False, "error": "syft unavailable"}

    recorder.run_sca = failing_sca  # type: ignore[method-assign]

    await build_executor(recorder).execute("run-1")

    assert recorder.statuses == ["running", "completed_with_warnings"]
    assert recorder.summary is not None
    assert recorder.summary["result_quality"]["metrics"]["tool_failures"] == 1


@pytest.mark.asyncio
async def test_pipeline_executor_fails_when_required_joern_fails() -> None:
    recorder = CallbackRecorder(
        {
            "audit_run_id": "run-1",
            "project_id": "project-1",
            "config": {"workspace_host_path": "/workspace/project", "enable_joern": True, "joern_required": True},
            "allow_external_network": False,
            "retain_runtime_on_failure": False,
            "validator_rounds": 1,
            "max_parallel_validators": 1,
        }
    )

    async def failing_joern(*args: Any) -> dict[str, Any]:
        return {"ok": False, "available": False, "error": "joern missing"}

    recorder.run_joern = failing_joern  # type: ignore[method-assign]

    await build_executor(recorder).execute("run-1")

    assert recorder.statuses == ["running", "failed"]
    assert recorder.pipeline_states[-1]["stage"] == "failed"
    assert "joern missing" in recorder.pipeline_states[-1]["error"]


@pytest.mark.asyncio
async def test_pipeline_executor_continues_when_joern_unavailable_is_allowed() -> None:
    recorder = CallbackRecorder(
        {
            "audit_run_id": "run-1",
            "project_id": "project-1",
            "config": {
                "workspace_host_path": "/workspace/project",
                "enable_joern": True,
                "joern_required": True,
                "allow_joern_unavailable": True,
            },
            "allow_external_network": False,
            "retain_runtime_on_failure": False,
            "validator_rounds": 1,
            "max_parallel_validators": 1,
        }
    )

    async def failing_joern(*args: Any) -> dict[str, Any]:
        return {"ok": False, "available": False, "error": "joern missing"}

    recorder.run_joern = failing_joern  # type: ignore[method-assign]

    await build_executor(recorder).execute("run-1")

    assert recorder.statuses == ["running", "completed_with_warnings"]
    assert recorder.summary is not None
    assert recorder.summary["result_quality"]["metrics"]["tool_failures"] == 1


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
