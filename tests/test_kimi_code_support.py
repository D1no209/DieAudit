from __future__ import annotations

from pathlib import Path

import yaml

from app.integrations.protocols import AcpRuntimeClient
from app.runtime.agent_runtime_package import AgentRuntimePackageBuilder


ROOT = Path(__file__).resolve().parents[1]


def read_source(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding="utf-8")


def test_kimi_code_agent_templates_use_stdio_acp() -> None:
    template_dir = ROOT / "configs" / "agent-templates"
    expected = {
        "kimi-orchestrator.yaml",
        "kimi-code-auditor.yaml",
        "kimi-source-sink-finder.yaml",
        "kimi-sca-analyst.yaml",
        "kimi-validator.yaml",
        "kimi-judger.yaml",
        "kimi-poc-writer.yaml",
        "kimi-poc-verifier.yaml",
        "kimi-recon-auditor.yaml",
    }

    for name in expected:
        template = yaml.safe_load((template_dir / name).read_text(encoding="utf-8"))
        assert template["image"] == "dieaudit/kimi-code-agent:local"
        assert template["command"] == ["python", "/app/acp_runner.py"]
        assert template["protocol"]["kind"] == "agent-client-protocol"
        assert template["protocol"]["transport"] == "stdio"
        assert template["protocol"]["runtime"] == "kimi"
        assert template["protocol"]["stdio_command"] == ["kimi-code", "acp"]
        assert template["runtime_mount"]["target"] == "/dieaudit/runtime"
        assert "whiteboard-mcp" in template.get("required_mcp", [])


def test_kimi_code_agent_is_dockerized() -> None:
    dockerfile = read_source("services/agents/kimi-code-agent/Dockerfile")
    compose = read_source("docker-compose.yml")

    assert 'ACP_ARGS="acp"' in dockerfile
    assert "bunx --version" in dockerfile
    assert "COPY services/agents/kimi-code-agent/acp_runner.py /app/acp_runner.py" in dockerfile
    assert "COPY services/agents/kimi-code-agent/kimi_acp_runtime_server.py /app/kimi_acp_runtime_server.py" in dockerfile
    assert "uvicorn" in dockerfile
    assert "kimi-code-agent-image:" in compose
    assert "dieaudit/kimi-code-agent:local" in compose


def test_kimi_runtime_server_injects_model_environment() -> None:
    orchestrator = read_source("services/platform/app/runtime/orchestrator.py")

    runner_start = orchestrator.index("    async def _start_agent_runtime_runner")
    agent_start = orchestrator.index("\n    async def _start_agent(", runner_start)
    runner_source = orchestrator[runner_start:agent_start]

    assert "runtime_home=runtime_target" in runner_source
    assert "KIMI_CODE_HOME" in read_source("services/platform/app/runtime/agent_runtime_package.py")
    assert "set_session_model" in read_source("services/agents/kimi-code-agent/kimi_acp_runtime_server.py")


def test_agent_model_provider_types_match_admin_surface() -> None:
    source = read_source("services/web-api/app/application/agent_model_profiles.py")
    assert 'KIMI_MODEL_PROVIDER_TYPES = ("openai", "openai_responses", "anthropic")' in source
    assert '"value": "kimi"' not in source


def test_acp_command_env_uses_template_stdio_command() -> None:
    template = {
        "protocol": {
            "kind": "agent-client-protocol",
            "transport": "stdio",
            "runtime": "kimi",
            "stdio_command": ["bunx", "@moonshot-ai/kimi-code", "acp"],
        }
    }

    env = AcpRuntimeClient().command_env(template)

    assert env["ACP_RUNTIME_NAME"] == "kimi"
    assert env["ACP_COMMAND"] == "bunx"
    assert env["ACP_ARGS"] == "@moonshot-ai/kimi-code acp"


def test_runtime_package_keeps_stdio_mcp_out_of_runtime_config() -> None:
    mcp_config = AgentRuntimePackageBuilder._mcp_config(
        {
            "codebase-memory-mcp": {
                "transport": "stdio",
                "command": "codebase-memory-mcp",
                "args": [],
                "env": {"CBM_CACHE_DIR": "/artifacts/codebase-memory"},
            },
            "whiteboard-mcp": {
                "transport": "http",
                "url": "http://whiteboard-mcp:8001/mcp",
            },
        }
    )

    assert "codebase-memory-mcp" not in mcp_config
    assert mcp_config["whiteboard-mcp"]["type"] == "remote"


def test_kimi_runtime_env_uses_explicit_model_channel(monkeypatch, tmp_path) -> None:
    config_root = tmp_path / "configs"
    config_root.mkdir()
    (config_root / "model-providers.yaml").write_text(
        """
providers:
  moonshot:
    type: kimi
    base_url: https://api.moonshot.ai/v1
    api_key_env: KIMI_API_KEY
    default_model: kimi-k2
profiles:
  auditor-strong:
    provider: moonshot
    model: kimi-k2
""",
        encoding="utf-8",
    )
    monkeypatch.setenv("KIMI_API_KEY", "sk-test")
    settings = type("Settings", (), {"config_root": config_root, "artifact_root": tmp_path / "artifacts"})()
    builder = AgentRuntimePackageBuilder(settings)

    env = builder.runtime_env({"model_profile": "auditor-strong", "protocol": {"runtime": "kimi"}})

    assert env["KIMI_MODEL_NAME"] == "kimi-k2"
    assert env["KIMI_MODEL_PROVIDER_TYPE"] == "kimi"
    assert env["KIMI_MODEL_API_KEY"] == "sk-test"
    assert env["KIMI_MODEL_BASE_URL"] == "https://api.moonshot.ai/v1"


def test_kimi_config_toml_contains_all_agent_profile_aliases(tmp_path) -> None:
    config_root = tmp_path / "configs"
    config_root.mkdir()
    (config_root / "model-providers.yaml").write_text(
        """
providers:
  openai:
    type: openai
    base_url: https://api.openai.com/v1
    api_key_env: OPENAI_API_KEY
    default_model: gpt-4.1
profiles:
  auditor-strong:
    provider: openai
    model: gpt-4.1
""",
        encoding="utf-8",
    )
    settings = type("Settings", (), {"config_root": config_root, "artifact_root": tmp_path / "artifacts"})()
    builder = AgentRuntimePackageBuilder(settings)
    template = {
        "name": "kimi-code-auditor",
        "env": {"AGENT_ROLE": "code-auditor"},
        "model_profile": "auditor-strong",
        "protocol": {"runtime": "kimi"},
    }
    payload = {
        "config": {
            "model_overrides": {
                "orchestrator": {
                    "provider": "openai_responses",
                    "model": "gpt-4.1",
                    "base_url": "https://api.openai.com/v1",
                    "api_key": "sk-orchestrator",
                    "context_window": 128000,
                    "max_output_tokens": 8192,
                },
                "code-auditor": {
                    "provider": "anthropic",
                    "model": "claude-3-5-sonnet",
                    "base_url": "https://api.anthropic.com",
                    "api_key": "sk-auditor",
                    "context_window": 200000,
                    "max_output_tokens": 8192,
                },
            }
        }
    }

    toml = builder.kimi_config_toml(template, payload)

    assert 'default_model = "dieaudit/code-auditor"' in toml
    assert '[providers."dieaudit-orchestrator"]' in toml
    assert 'type = "openai_responses"' in toml
    assert '[providers."dieaudit-code-auditor"]' in toml
    assert 'type = "anthropic"' in toml
    assert '[models."dieaudit/orchestrator"]' in toml
    assert '[models."dieaudit/code-auditor"]' in toml
    assert 'model = "claude-3-5-sonnet"' in toml
