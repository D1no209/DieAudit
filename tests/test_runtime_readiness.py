from __future__ import annotations

from pathlib import Path

import yaml

from app.api.routes import (
    _embedding_readiness_remediation,
    _sandbox_readiness_remediation,
    _summarize_readiness_checks,
    _template_readiness_checks,
    _vector_store_readiness_remediation,
)


ROOT = Path(__file__).resolve().parents[1]


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


def test_heavy_analyzer_readiness_passes_when_required_binaries_available() -> None:
    checks = {
        check["id"]: check
        for check in _template_readiness_checks(
            [],
            [
                {"name": "joern-mcp", "image": "dieaudit/tool-mcp:local", "required_binaries": ["joern"]},
                {"name": "codeql-mcp", "image": "dieaudit/tool-mcp:local", "required_binaries": ["codeql"]},
            ],
            {
                "ok": True,
                "templates": {
                    "joern-mcp": {"available": True, "missing_binaries": []},
                    "codeql-mcp": {"available": True, "missing_binaries": []},
                },
            },
        )
    }

    assert checks["heavy_analyzers"]["status"] == "pass"


def test_heavy_analyzer_templates_use_dedicated_images() -> None:
    codeql = yaml.safe_load((ROOT / "configs/mcp-templates/codeql-mcp.yaml").read_text(encoding="utf-8"))
    joern = yaml.safe_load((ROOT / "configs/mcp-templates/joern-mcp.yaml").read_text(encoding="utf-8"))

    assert codeql["image"] == "dieaudit/tool-mcp-codeql:local"
    assert joern["image"] == "dieaudit/tool-mcp-joern:local"
    assert codeql["required_binaries"] == ["codeql"]
    assert joern["required_binaries"] == ["joern"]


def test_bare_role_agent_templates_use_opencode_runtime() -> None:
    for role in ["orchestrator", "recon-auditor", "sca-analyst", "validator", "judger", "poc-writer"]:
        template = yaml.safe_load((ROOT / f"configs/agent-templates/{role}.yaml").read_text(encoding="utf-8"))

        assert template["image"] == "dieaudit/opencode-agent:local"
        assert template["protocol"]["kind"] == "agent-client-protocol"
        assert template["protocol"]["runtime"] == "opencode"
        assert template["command"] == ["python", "/app/opencode_acp_runner.py"]
        assert template["instruction"] == f"{role}.md"


def test_mock_orchestrator_is_demo_only() -> None:
    template = yaml.safe_load((ROOT / "configs/agent-templates/mock-orchestrator.yaml").read_text(encoding="utf-8"))

    assert template["profile"] == "demo"
    assert template["image"] == "dieaudit/mock-agent:local"
    assert template["protocol"]["runtime"] == "mock"


def test_heavy_analyzer_readiness_warns_when_required_binaries_missing() -> None:
    checks = {
        check["id"]: check
        for check in _template_readiness_checks(
            [],
            [
                {"name": "joern-mcp", "image": "dieaudit/tool-mcp:local", "required_binaries": ["joern"]},
                {"name": "codeql-mcp", "image": "dieaudit/tool-mcp:local", "required_binaries": ["codeql"]},
            ],
            {
                "ok": False,
                "templates": {
                    "joern-mcp": {"available": False, "missing_binaries": ["joern"]},
                    "codeql-mcp": {"available": False, "missing_binaries": ["codeql"]},
                },
            },
        )
    }

    assert checks["heavy_analyzers"]["status"] == "warn"
    assert checks["heavy_analyzers"]["detail"]["missing_binaries"] == {
        "codeql-mcp": ["codeql"],
        "joern-mcp": ["joern"],
    }


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


def test_sandbox_readiness_remediation_points_to_runsc_when_only_runc_exists() -> None:
    remediation = _sandbox_readiness_remediation(
        {
            "requested_runtime": "runc",
            "docker_runtimes": ["runc", "io.containerd.runc.v2"],
            "strong_isolation_available": False,
            "requested_runtime_available": True,
        }
    )

    assert any("runsc" in item for item in remediation)
    assert any("ALLOW_RUNC_SANDBOX=false" in item for item in remediation)


def test_embedding_readiness_remediation_rejects_hash_for_production() -> None:
    remediation = _embedding_readiness_remediation({"provider": "hash", "status": "warn"})

    assert any("openai-compatible" in item for item in remediation)
    assert any("embedding model" in item for item in remediation)


def test_vector_store_readiness_remediation_handles_dimension_mismatch() -> None:
    remediation = _vector_store_readiness_remediation(
        {"status": "fail", "message": "Qdrant collection vector size 1024 does not match KNOWLEDGE_VECTOR_SIZE=1536"}
    )

    assert any("KNOWLEDGE_COLLECTION_NAME" in item for item in remediation)
    assert any("Reindex" in item for item in remediation)


def test_readiness_summary_promotes_blocking_checks_and_actions() -> None:
    checks = [
        {
            "id": "api_key",
            "title": "API key is configured",
            "status": "fail",
            "detail": {},
            "remediation": ["set key", "restart services"],
        },
        {
            "id": "heavy_analyzers",
            "title": "Heavy analyzers have required tool CLIs",
            "status": "warn",
            "detail": {},
            "remediation": ["pull tool image"],
        },
        {"id": "docker", "title": "Docker runtime is reachable", "status": "pass", "detail": {}},
    ]

    summary = _summarize_readiness_checks(checks)

    assert summary["ok"] is False
    assert summary["status"] == "not_ready"
    assert summary["summary"] == {"fail": 1, "warn": 1, "pass": 1}
    assert [item["id"] for item in summary["blocking_checks"]] == ["api_key"]
    assert [item["id"] for item in summary["warning_checks"]] == ["heavy_analyzers"]
    assert [item["id"] for item in summary["next_actions"]] == ["api_key", "heavy_analyzers"]
    assert summary["next_actions"][0]["remediation"] == ["set key", "restart services"]
