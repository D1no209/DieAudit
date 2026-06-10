from app.schemas import CreateAuditRunRequest, RunPocRequest, StartAgentRunRequest, StartSandboxServiceRequest, ValidatorScaleRequest


def test_runtime_requests_default_to_no_external_network() -> None:
    assert CreateAuditRunRequest().allow_external_network is False
    assert StartAgentRunRequest().allow_external_network is False
    assert ValidatorScaleRequest().allow_external_network is False
    assert RunPocRequest().allow_external_network is False
    assert StartSandboxServiceRequest().allow_external_network is False
