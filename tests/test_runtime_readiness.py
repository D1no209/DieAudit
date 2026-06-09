from __future__ import annotations

from app.api.routes import _template_readiness_checks


def test_template_readiness_accepts_opencode_and_tool_mcp_templates() -> None:
    agent_templates = [
        {
            "name": name,
            "image": "dieaudit/opencode-agent:local",
            "protocol": {"kind": "agent-client-protocol", "runtime": "opencode"},
        }
        for name in [
            "opencode-orchestrator",
            "opencode-recon-auditor",
            "opencode-sca-analyst",
            "opencode-validator",
            "opencode-judger",
            "opencode-poc-writer",
        ]
    ]
    mcp_templates = [
        {"name": name, "image": "dieaudit/tool-mcp:local"}
        for name in [
            "filesystem-mcp",
            "code-search-mcp",
            "semgrep-mcp",
            "sca-mcp",
            "kb-mcp",
            "http-test-mcp",
            "sandbox-mcp",
        ]
    ]

    checks = {check["id"]: check for check in _template_readiness_checks(agent_templates, mcp_templates)}

    assert checks["opencode_agent_templates"]["status"] == "pass"
    assert checks["production_mcp_templates"]["status"] == "pass"


def test_template_readiness_fails_missing_or_mock_production_templates() -> None:
    checks = {
        check["id"]: check
        for check in _template_readiness_checks(
            [
                {
                    "name": "opencode-validator",
                    "image": "dieaudit/mock-agent:local",
                    "protocol": {"kind": "legacy-http", "runtime": "mock"},
                }
            ],
            [{"name": "filesystem-mcp", "image": "dieaudit/mock-mcp:local"}],
        )
    }

    assert checks["opencode_agent_templates"]["status"] == "fail"
    assert "opencode-validator" in checks["opencode_agent_templates"]["detail"]["invalid"]
    assert "opencode-recon-auditor" in checks["opencode_agent_templates"]["detail"]["missing"]
    assert checks["production_mcp_templates"]["status"] == "fail"
    assert "filesystem-mcp" in checks["production_mcp_templates"]["detail"]["mock_images"]
    assert "code-search-mcp" in checks["production_mcp_templates"]["detail"]["missing"]
