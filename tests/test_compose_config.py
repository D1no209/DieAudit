from __future__ import annotations

from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]


def test_platform_services_receive_sandbox_runtime_environment() -> None:
    compose = yaml.safe_load((ROOT / "docker-compose.yml").read_text(encoding="utf-8"))
    services = compose["services"]
    platform_services = [
        "web-api",
        "workflow-worker",
        "agent-gateway",
        "workspace-engine",
        "sandbox-runner",
        "kb-indexer",
    ]
    required = {"DEFAULT_SANDBOX_RUNTIME", "ENABLE_GVISOR", "ALLOW_RUNC_SANDBOX"}

    for service_name in platform_services:
        environment = services[service_name]["environment"]
        missing = required.difference(environment)
        assert not missing, f"{service_name} missing sandbox env vars: {sorted(missing)}"
