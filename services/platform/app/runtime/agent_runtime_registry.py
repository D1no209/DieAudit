from __future__ import annotations

from dataclasses import asdict, dataclass


REQUIRED_AGENT_ROLES = (
    "orchestrator",
    "code-auditor",
    "recon-auditor",
    "sca-analyst",
    "source-sink-finder",
    "validator",
    "judger",
    "poc-writer",
    "poc-verifier",
)


@dataclass(frozen=True)
class AgentRuntimeAdapter:
    runtime_id: str
    display_name: str
    protocol_kind: str
    template_runtime: str
    image: str
    capabilities: tuple[str, ...]
    default_model_profile: str
    role_templates: dict[str, str]
    enabled: bool = True

    def to_bff_dict(self) -> dict:
        data = asdict(self)
        data["capabilities"] = list(self.capabilities)
        return data


BUILTIN_AGENT_RUNTIMES = (
    AgentRuntimeAdapter(
        runtime_id="kimi-code",
        display_name="Kimi Code",
        protocol_kind="agent-client-protocol",
        template_runtime="kimi",
        image="dieaudit/kimi-code-agent:local",
        capabilities=("acp", "mcp", "transcript-events", "runtime-containers", "model-overrides"),
        default_model_profile="auditor-strong",
        role_templates={
            "orchestrator": "kimi-orchestrator",
            "code-auditor": "kimi-code-auditor",
            "recon-auditor": "kimi-recon-auditor",
            "sca-analyst": "kimi-sca-analyst",
            "source-sink-finder": "kimi-source-sink-finder",
            "validator": "kimi-validator",
            "judger": "kimi-judger",
            "poc-writer": "kimi-poc-writer",
            "poc-verifier": "kimi-poc-verifier",
        },
    ),
)


def enabled_agent_runtimes() -> tuple[AgentRuntimeAdapter, ...]:
    return tuple(runtime for runtime in BUILTIN_AGENT_RUNTIMES if runtime.enabled)


def default_agent_runtime() -> AgentRuntimeAdapter:
    return enabled_agent_runtimes()[0]


def default_agent_template(role: str) -> str:
    return default_agent_runtime().role_templates[role]


def required_agent_template_names() -> set[str]:
    names: set[str] = set()
    for runtime in enabled_agent_runtimes():
        names.update(runtime.role_templates[role] for role in REQUIRED_AGENT_ROLES)
    return names


def template_runtime_for_name(template_name: str) -> str | None:
    for runtime in enabled_agent_runtimes():
        if template_name in runtime.role_templates.values():
            return runtime.template_runtime
    return None
