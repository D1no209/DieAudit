import pytest
from pydantic import ValidationError

from app.schemas import (
    CodeBatchAnalysisRequest,
    CreateAuditRunRequest,
    RunPocRequest,
    StartAgentRunRequest,
    StartSandboxServiceRequest,
    ValidatorScaleRequest,
)


def test_runtime_requests_default_to_no_external_network() -> None:
    assert CreateAuditRunRequest().allow_external_network is False
    assert StartAgentRunRequest(project_id="project-1").allow_external_network is False
    assert ValidatorScaleRequest(project_id="project-1").allow_external_network is False
    assert RunPocRequest(command=["python", "-V"]).allow_external_network is False
    assert StartSandboxServiceRequest(command=["python", "-m", "http.server", "8080"]).allow_external_network is False


def test_runtime_requests_do_not_default_to_demo_project_ids() -> None:
    with pytest.raises(ValidationError):
        StartAgentRunRequest()
    with pytest.raises(ValidationError):
        ValidatorScaleRequest()
    assert StartAgentRunRequest(project_id="project-1").audit_run_id is None
    assert ValidatorScaleRequest(project_id="project-1").project_id == "project-1"


def test_code_batch_analysis_defaults_are_bounded_and_enabled_on_audit_runs() -> None:
    audit_run = CreateAuditRunRequest()
    code_batch = CodeBatchAnalysisRequest()

    assert audit_run.enable_code_batch_analysis is True
    assert audit_run.max_code_audit_tasks == 8
    assert audit_run.max_files_per_code_audit_task == 25
    assert audit_run.max_parallel_code_auditors == 2
    assert audit_run.code_auditor_agent_name == "opencode-code-auditor"
    assert code_batch.max_tasks == 8
    assert code_batch.max_files_per_task == 25
    assert code_batch.max_parallel_agents == 2
    assert code_batch.agent_name == "opencode-code-auditor"


def test_sandbox_execution_requests_require_explicit_commands() -> None:
    with pytest.raises(ValidationError):
        RunPocRequest()
    with pytest.raises(ValidationError):
        StartSandboxServiceRequest()
