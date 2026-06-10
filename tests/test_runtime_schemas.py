import pytest
from pydantic import ValidationError

from app.schemas import CreateAuditRunRequest, RunPocRequest, StartAgentRunRequest, StartSandboxServiceRequest, ValidatorScaleRequest


def test_runtime_requests_default_to_no_external_network() -> None:
    assert CreateAuditRunRequest().allow_external_network is False
    assert StartAgentRunRequest().allow_external_network is False
    assert ValidatorScaleRequest().allow_external_network is False
    assert RunPocRequest(command=["python", "-V"]).allow_external_network is False
    assert StartSandboxServiceRequest(command=["python", "-m", "http.server", "8080"]).allow_external_network is False


def test_sandbox_execution_requests_require_explicit_commands() -> None:
    with pytest.raises(ValidationError):
        RunPocRequest()
    with pytest.raises(ValidationError):
        StartSandboxServiceRequest()
