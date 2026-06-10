from __future__ import annotations

from typing import Any

from app.settings import Settings


PRODUCTION_AGENT_TEMPLATES = {
    "opencode-orchestrator",
    "opencode-recon-auditor",
    "opencode-sca-analyst",
    "opencode-validator",
    "opencode-judger",
    "opencode-poc-writer",
}
PRODUCTION_MCP_TEMPLATES = {
    "filesystem-mcp",
    "code-search-mcp",
    "semgrep-mcp",
    "sca-mcp",
    "kb-mcp",
    "http-test-mcp",
    "sandbox-mcp",
}
OPTIONAL_HEAVY_MCP_TEMPLATES = {"joern-mcp", "codeql-mcp"}


def sandbox_readiness_remediation(detail: dict[str, Any]) -> list[str]:
    requested_runtime = str(detail.get("requested_runtime") or "runc")
    runtimes = detail.get("docker_runtimes") or []
    remediation: list[str] = []
    if not detail.get("strong_isolation_available"):
        remediation.append("Install a strong container runtime on the Docker host, preferably gVisor runsc for the first production target.")
        if "runsc" not in runtimes:
            remediation.append("After installing gVisor, register runsc in Docker daemon.json and restart Docker Engine.")
        remediation.append("Set ENABLE_GVISOR=true and DEFAULT_SANDBOX_RUNTIME=runsc, then restart the core Compose services.")
    if requested_runtime == "runc":
        remediation.append("Keep ALLOW_RUNC_SANDBOX=false for production; runc is acceptable only for explicit local testing with trusted PoCs.")
    elif not detail.get("requested_runtime_available"):
        remediation.append(
            f"Install or register the configured Docker runtime '{requested_runtime}', or change DEFAULT_SANDBOX_RUNTIME to an available strong runtime."
        )
    return remediation


def embedding_readiness_remediation(status: dict[str, Any]) -> list[str]:
    provider = str(status.get("provider") or "hash")
    if provider in {"hash", "local-hash", ""}:
        return [
            "Configure KNOWLEDGE_EMBEDDING_PROVIDER=openai-compatible for production RAG quality.",
            "Set KNOWLEDGE_EMBEDDING_BASE_URL to an endpoint exposing /embeddings, KNOWLEDGE_EMBEDDING_MODEL to a real embedding model, and KNOWLEDGE_VECTOR_SIZE to the model dimension.",
            "Set KNOWLEDGE_EMBEDDING_API_KEY when the embedding endpoint requires authentication.",
        ]
    if provider not in {"openai", "openai-compatible"}:
        return ["Use KNOWLEDGE_EMBEDDING_PROVIDER=openai-compatible or add a tested provider implementation before enabling production RAG."]
    remediation: list[str] = []
    if not status.get("base_url_configured"):
        remediation.append("Set KNOWLEDGE_EMBEDDING_BASE_URL to the OpenAI-compatible embedding API base URL.")
    if not status.get("model"):
        remediation.append("Set KNOWLEDGE_EMBEDDING_MODEL to the embedding model name.")
    probe = status.get("probe") if isinstance(status.get("probe"), dict) else {}
    if probe.get("attempted") and not probe.get("ok"):
        remediation.append("Fix embedding endpoint reachability, credentials, or vector dimension mismatch shown in the readiness detail.")
    if not remediation and status.get("status") != "pass":
        remediation.append("Review the embedding readiness detail and configure a semantic embedding provider before production RAG use.")
    return remediation


def template_readiness_checks(
    agent_templates: list[dict[str, Any]],
    mcp_templates: list[dict[str, Any]],
    tool_capabilities: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    agents = {str(item.get("name") or ""): item for item in agent_templates}
    mcps = {str(item.get("name") or ""): item for item in mcp_templates}

    missing_agents = sorted(PRODUCTION_AGENT_TEMPLATES - set(agents))
    invalid_agents = sorted(
        name
        for name in PRODUCTION_AGENT_TEMPLATES & set(agents)
        if (agents[name].get("protocol") or {}).get("kind") != "agent-client-protocol"
        or (agents[name].get("protocol") or {}).get("runtime") != "opencode"
        or "mock-agent" in str(agents[name].get("image") or "")
    )
    missing_mcps = sorted(PRODUCTION_MCP_TEMPLATES - set(mcps))
    mock_mcps = sorted(
        name
        for name in PRODUCTION_MCP_TEMPLATES & set(mcps)
        if "mock-mcp" in str(mcps[name].get("image") or "")
    )
    optional_heavy = sorted(OPTIONAL_HEAVY_MCP_TEMPLATES & set(mcps))
    heavy_missing = {
        name: (tool_capabilities.get("templates", {}).get(name) or {}).get("missing_binaries", [])
        for name in optional_heavy
    } if tool_capabilities else {}
    heavy_unavailable = sorted(name for name, missing in heavy_missing.items() if missing)
    heavy_probe_error = bool(tool_capabilities and tool_capabilities.get("error"))
    legacy_mock_agents = sorted(
        name
        for name, template in agents.items()
        if name and name not in PRODUCTION_AGENT_TEMPLATES and "mock-agent" in str(template.get("image") or "")
    )

    checks = [
        {
            "id": "opencode_agent_templates",
            "title": "OpenCode ACP agent templates are configured",
            "status": "fail" if missing_agents or invalid_agents else "pass",
            "detail": {
                "required": sorted(PRODUCTION_AGENT_TEMPLATES),
                "missing": missing_agents,
                "invalid": invalid_agents,
            },
        },
        {
            "id": "production_mcp_templates",
            "title": "Production MCP templates are configured",
            "status": "fail" if missing_mcps or mock_mcps else "pass",
            "detail": {
                "required": sorted(PRODUCTION_MCP_TEMPLATES),
                "missing": missing_mcps,
                "mock_images": mock_mcps,
            },
        },
    ]
    if optional_heavy:
        status = "pass"
        message = "Heavy analyzer templates have required CLIs available in their configured tool images."
        if tool_capabilities is None:
            status = "warn"
            message = "Heavy analyzer templates are present, but tool image capabilities were not probed."
        elif heavy_probe_error or heavy_unavailable:
            status = "warn"
            message = "Heavy analyzer templates are present, but one or more required CLIs are unavailable in their configured images."
        checks.append(
            {
                "id": "heavy_analyzers",
                "title": "Heavy analyzers have required tool CLIs",
                "status": status,
                "detail": {
                    "templates": optional_heavy,
                    "unavailable": heavy_unavailable,
                    "missing_binaries": heavy_missing,
                    "tool_capabilities": tool_capabilities,
                    "message": message,
                },
            }
        )
    if legacy_mock_agents:
        checks.append(
            {
                "id": "legacy_mock_templates",
                "title": "Legacy mock templates are still available",
                "status": "warn",
                "detail": {
                    "templates": legacy_mock_agents,
                    "message": "Keep mock templates for demo only; production audit runs should use opencode-* templates.",
                },
            }
        )
    return checks


def pipeline_backend_readiness_check(settings: Settings, worker_health: dict[str, Any] | None = None) -> dict[str, Any]:
    backend = normalized_pipeline_backend(settings)
    supported_backends = {"background-tasks", "workflow-worker"}
    production_backends = {"workflow-worker"}
    if backend not in supported_backends:
        status = "fail"
        message = f"Unsupported pipeline execution backend '{backend}'. Supported backends: {sorted(supported_backends)}."
    elif backend in production_backends:
        if worker_health and worker_health.get("ok"):
            status = "pass"
            message = "Audit pipelines are claimed by at least one fresh workflow-worker heartbeat."
        elif worker_health is None:
            status = "fail"
            message = "Workflow-worker backend is configured, but worker heartbeat health was not checked."
        else:
            status = "fail"
            message = worker_health.get("message") or "No fresh workflow-worker heartbeat is available."
    else:
        status = "fail"
        message = (
            "FastAPI background task execution can lose in-flight work on restart. "
            "Use workflow-worker before treating this deployment as production-ready."
        )
    return {
        "id": "pipeline_execution_backend",
        "title": "Audit pipeline execution is not tied to FastAPI background tasks",
        "status": status,
        "detail": {
            "backend": backend,
            "production_backends": sorted(production_backends),
            "supported_backends": sorted(supported_backends),
            "recovery_on_startup": settings.pipeline_recovery_on_startup,
            "worker_health": worker_health,
            "message": message,
        },
        "remediation": [] if status == "pass" else [
            "Set PIPELINE_EXECUTION_BACKEND=workflow-worker and keep workflow-worker enabled in the core Compose profile.",
            "Verify /runtime/workers reports at least one fresh running worker heartbeat.",
        ],
    }


def normalized_pipeline_backend(settings: Settings) -> str:
    return (settings.pipeline_execution_backend or "workflow-worker").strip().lower()
