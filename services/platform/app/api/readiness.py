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


def http_guardrails_readiness_check(settings: Settings) -> dict[str, Any]:
    missing: list[str] = []
    if int(settings.max_request_body_bytes or 0) <= 0:
        missing.append("MAX_REQUEST_BODY_BYTES")
    if int(settings.max_upload_bytes or 0) <= 0:
        missing.append("MAX_UPLOAD_BYTES")
    if int(settings.rate_limit_per_minute or 0) <= 0:
        missing.append("RATE_LIMIT_PER_MINUTE")
    if int(settings.rate_limit_window_seconds or 0) <= 0:
        missing.append("RATE_LIMIT_WINDOW_SECONDS")

    return {
        "id": "http_guardrails",
        "title": "HTTP request guard rails are enabled",
        "status": "fail" if missing else "pass",
        "detail": {
            "max_request_body_bytes": settings.max_request_body_bytes,
            "max_upload_bytes": settings.max_upload_bytes,
            "rate_limit_per_minute": settings.rate_limit_per_minute,
            "rate_limit_window_seconds": settings.rate_limit_window_seconds,
            "missing_or_disabled": missing,
        },
        "remediation": [] if not missing else [
            "Set MAX_REQUEST_BODY_BYTES and MAX_UPLOAD_BYTES to positive byte limits for source uploads.",
            "Set RATE_LIMIT_PER_MINUTE and RATE_LIMIT_WINDOW_SECONDS to positive values for single-node API throttling.",
            "Use nginx, WAF, or ingress-level rate limiting before exposing multi-node deployments.",
        ],
    }


def workspace_import_readiness_check(settings: Settings) -> dict[str, Any]:
    schemes = _csv_values(settings.allowed_git_url_schemes)
    unsafe_schemes = sorted(set(schemes) & {"file", "ftp"})
    missing_limits: list[str] = []
    if int(settings.max_workspace_files or 0) <= 0:
        missing_limits.append("MAX_WORKSPACE_FILES")
    if int(settings.max_workspace_uncompressed_bytes or 0) <= 0:
        missing_limits.append("MAX_WORKSPACE_UNCOMPRESSED_BYTES")
    if not schemes:
        missing_limits.append("ALLOWED_GIT_URL_SCHEMES")

    return {
        "id": "workspace_import_guardrails",
        "title": "Workspace import guard rails are enabled",
        "status": "fail" if missing_limits or unsafe_schemes else "pass",
        "detail": {
            "max_workspace_files": settings.max_workspace_files,
            "max_workspace_uncompressed_bytes": settings.max_workspace_uncompressed_bytes,
            "allowed_git_url_schemes": schemes,
            "allowed_git_hosts": _csv_values(settings.allowed_git_hosts),
            "missing_or_disabled": missing_limits,
            "unsafe_schemes": unsafe_schemes,
        },
        "remediation": [] if not missing_limits and not unsafe_schemes else [
            "Set MAX_WORKSPACE_FILES and MAX_WORKSPACE_UNCOMPRESSED_BYTES to positive limits before accepting Git or zip imports.",
            "Keep ALLOWED_GIT_URL_SCHEMES limited to https,ssh for production unless another remote scheme has been explicitly approved.",
            "Do not allow file:// or local Git paths in production imports.",
        ],
    }


def _csv_values(value: str) -> list[str]:
    return [item.strip().lower() for item in (value or "").split(",") if item.strip()]


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


def vector_store_readiness_remediation(status: dict[str, Any]) -> list[str]:
    if status.get("qdrant_url_configured") is False:
        return ["Set QDRANT_URL to the Qdrant service endpoint before enabling knowledge retrieval."]
    message = str(status.get("message") or "")
    if "vector size" in message or "KNOWLEDGE_VECTOR_SIZE" in message:
        return [
            "Set KNOWLEDGE_COLLECTION_NAME to a new collection name after changing embedding provider or vector dimension.",
            "Reindex uploaded knowledge documents so Qdrant vectors match the configured embedding model.",
            "Delete or archive obsolete Qdrant collections only after confirming no AuditRun depends on them.",
        ]
    if status.get("status") == "warn":
        return ["Upload or reindex at least one knowledge document to initialize the configured Qdrant collection."]
    if status.get("status") == "fail":
        return ["Verify Qdrant is reachable from platform services and that the configured collection can be read."]
    return []


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


def summarize_readiness_checks(checks: list[dict[str, Any]]) -> dict[str, Any]:
    blocking_checks = [check for check in checks if check.get("status") == "fail"]
    warning_checks = [check for check in checks if check.get("status") == "warn"]
    passed_checks = [check for check in checks if check.get("status") == "pass"]
    next_actions: list[dict[str, Any]] = []

    for check in blocking_checks + warning_checks:
        remediation = check.get("remediation") if isinstance(check.get("remediation"), list) else []
        next_actions.append(
            {
                "id": check.get("id"),
                "status": check.get("status"),
                "title": check.get("title"),
                "remediation": remediation[:3],
            }
        )

    return {
        "ok": not blocking_checks,
        "status": "ready" if not blocking_checks else "not_ready",
        "summary": {
            "fail": len(blocking_checks),
            "warn": len(warning_checks),
            "pass": len(passed_checks),
        },
        "blocking_checks": blocking_checks,
        "warning_checks": warning_checks,
        "next_actions": next_actions[:8],
        "checks": checks,
    }


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
