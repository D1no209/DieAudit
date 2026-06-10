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
    required = {
        "DEFAULT_SANDBOX_RUNTIME",
        "ENABLE_GVISOR",
        "ALLOW_RUNC_SANDBOX",
        "ALLOW_SANDBOX_EXTERNAL_NETWORK",
        "ENABLE_DEMO_TEMPLATES",
    }

    for service_name in platform_services:
        environment = services[service_name]["environment"]
        missing = required.difference(environment)
        assert not missing, f"{service_name} missing sandbox env vars: {sorted(missing)}"


def test_platform_services_receive_workspace_import_policy_environment() -> None:
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
    required = {
        "MAX_REQUEST_BODY_BYTES",
        "MAX_UPLOAD_BYTES",
        "MAX_WORKSPACE_FILES",
        "MAX_WORKSPACE_UNCOMPRESSED_BYTES",
        "ALLOWED_GIT_URL_SCHEMES",
        "ALLOWED_GIT_HOSTS",
    }

    for service_name in platform_services:
        environment = services[service_name]["environment"]
        missing = required.difference(environment)
        assert not missing, f"{service_name} missing workspace import env vars: {sorted(missing)}"


def test_docker_socket_proxy_only_exposes_required_api_groups() -> None:
    compose = yaml.safe_load((ROOT / "docker-compose.yml").read_text(encoding="utf-8"))
    environment = compose["services"]["docker-socket-proxy"]["environment"]

    required_enabled = {"POST", "CONTAINERS", "IMAGES", "NETWORKS", "INFO", "PING", "VERSION", "SYSTEM"}
    for key in required_enabled:
        assert environment.get(key) == "1", f"docker-socket-proxy must enable {key}"

    forbidden_enabled = {
        "AUTH",
        "BUILD",
        "COMMIT",
        "CONFIGS",
        "DISTRIBUTION",
        "EVENTS",
        "EXEC",
        "GRPC",
        "NODES",
        "PLUGINS",
        "SECRETS",
        "SERVICES",
        "SESSION",
        "SWARM",
        "TASKS",
        "VOLUMES",
    }
    unexpectedly_enabled = {key for key in forbidden_enabled if environment.get(key) == "1"}
    assert not unexpectedly_enabled, f"docker-socket-proxy exposes unneeded API groups: {sorted(unexpectedly_enabled)}"
