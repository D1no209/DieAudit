from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class StartAgentRunRequest(BaseModel):
    audit_run_id: str | None = None
    project_id: str = Field(min_length=1)
    agent_name: str = Field(default="orchestrator")
    workspace_host_path: str | None = None
    allow_external_network: bool = False
    retain_runtime_on_failure: bool = False
    input_payload: dict[str, Any] = Field(default_factory=dict)


class CreateProjectRequest(BaseModel):
    name: str = Field(min_length=1)
    git_url: str | None = None
    ref: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class CreateAuditRunRequest(BaseModel):
    snapshot_id: str | None = None
    agent_name: str = "opencode-orchestrator"
    enabled_agents: list[str] = Field(
        default_factory=lambda: [
            "orchestrator",
            "code-auditor",
            "source-sink-finder",
            "validator",
            "judger",
            "poc-writer",
            "poc-verifier",
        ]
    )
    preflight_prompt: str | None = None
    validator_rounds: int = Field(default=1, ge=1)
    max_parallel_validators: int = Field(default=2, ge=1)
    validator_agent_name: str = "opencode-validator"
    enable_validation_judgement: bool = True
    validation_judgement_agent_name: str = "opencode-validator"
    enable_feedback_loop: bool = True
    max_feedback_rounds: int = Field(default=2, ge=0, le=10)
    enable_code_batch_analysis: bool = True
    enable_batch_internal_semgrep: bool = True
    enable_batch_internal_sca: bool = True
    max_code_audit_tasks: int = Field(default=8, ge=1, le=100)
    max_files_per_code_audit_task: int = Field(default=25, ge=1, le=200)
    max_parallel_code_auditors: int = Field(default=2, ge=1, le=20)
    code_auditor_agent_name: str = "opencode-code-auditor"
    enable_source_sink_analysis: bool = True
    source_sink_finder_agent_name: str = "opencode-source-sink-finder"
    max_parallel_source_sink_finders: int = Field(default=2, ge=1, le=20)
    max_source_sink_findings: int = Field(default=50, ge=1, le=500)
    enable_validators: bool = True
    enable_judgement: bool = True
    judger_agent_name: str = "opencode-judger"
    max_parallel_judgers: int = Field(default=2, ge=1, le=20)
    enable_poc_writing: bool = True
    poc_writer_agent_name: str = "opencode-poc-writer"
    max_parallel_poc_writers: int = Field(default=2, ge=1, le=20)
    max_poc_findings: int = Field(default=25, ge=1, le=500)
    enable_poc_verification: bool = True
    poc_verifier_agent_name: str = "opencode-poc-verifier"
    max_parallel_poc_verifiers: int = Field(default=2, ge=1, le=20)
    enable_decompilation: bool = True
    decompiled_source_dir: str = ".dieaudit/decompiled"
    decompile_max_artifact_size_mb: int = Field(default=200, ge=1, le=4096)
    decompile_timeout_seconds: int = Field(default=300, ge=1, le=7200)
    decompile_max_artifacts: int = Field(default=50, ge=1, le=500)
    allow_external_network: bool = False
    retain_runtime_on_failure: bool = False
    input_payload: dict[str, Any] = Field(default_factory=dict)
    start_agent: bool = True


class CodeBatchAnalysisRequest(BaseModel):
    max_tasks: int = Field(default=8, ge=1, le=100)
    max_files_per_task: int = Field(default=25, ge=1, le=200)
    max_parallel_agents: int = Field(default=2, ge=1, le=20)
    agent_name: str = "opencode-code-auditor"
    wait_for_completion: bool = True


class CreateFindingRequest(BaseModel):
    title: str = Field(min_length=1)
    severity: str = "unknown"
    status: str = "candidate"
    file_path: str | None = None
    line_start: int | None = None
    line_end: int | None = None
    rule_id: str | None = None
    description: str | None = None
    source: str = "manual"
    raw: dict[str, Any] = Field(default_factory=dict)


class CreateApiKeyRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    scopes: list[str] = Field(default_factory=lambda: ["admin"])
    metadata: dict[str, Any] = Field(default_factory=dict)


class KnowledgeSearchRequest(BaseModel):
    query: str = Field(min_length=1)
    project_id: str | None = None
    include_global: bool = True
    limit: int = Field(default=8, ge=1, le=50)


class TemplateBody(BaseModel):
    template: dict[str, Any]


class A2AAgentCardRequest(BaseModel):
    url: str


class StorageCleanupRequest(BaseModel):
    dry_run: bool = True
    runtime_package_retention_days: int | None = Field(default=None, ge=0, le=3650)
    upload_staging_retention_days: int | None = Field(default=None, ge=0, le=3650)
    unreferenced_workspace_retention_days: int | None = Field(default=None, ge=0, le=3650)
    unreferenced_snapshot_retention_days: int | None = Field(default=None, ge=0, le=3650)
    max_entries: int | None = Field(default=None, ge=1, le=10000)


class WhiteboardAttachmentInput(BaseModel):
    path: str = Field(min_length=1, max_length=2048)
    label: str | None = Field(default=None, max_length=255)
    content_type: str | None = Field(default=None, max_length=255)
    metadata: dict[str, Any] = Field(default_factory=dict)


class WhiteboardLinkCandidateInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(default=None, max_length=255)
    card_ids: list[str] = Field(default_factory=list)
    status: str = Field(default="not_ready", max_length=32)
    agent_run_id: str | None = Field(default=None, max_length=128)
    agent_id: str | None = Field(default=None, max_length=128)
    rationale: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class CreateWhiteboardCardRequest(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    card_type: str = Field(default="observation", max_length=64)
    status: str = Field(default="open", max_length=64)
    author: str | None = Field(default=None, max_length=255)
    agent_run_id: str | None = Field(default=None, max_length=128)
    event_time: str | None = None
    content: str | None = None
    confidence: str | None = Field(default=None, max_length=32)
    finding_id: str | None = Field(default=None, max_length=128)
    file_path: str | None = None
    line_start: int | None = Field(default=None, ge=1)
    line_end: int | None = Field(default=None, ge=1)
    expected_predecessors: list[WhiteboardLinkCandidateInput] = Field(default_factory=list)
    possible_successors: list[WhiteboardLinkCandidateInput] = Field(default_factory=list)
    requirements: list[str] = Field(default_factory=list)
    attachments: list[WhiteboardAttachmentInput] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class UpdateWhiteboardCardRequest(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    card_type: str | None = Field(default=None, max_length=64)
    status: str | None = Field(default=None, max_length=64)
    content: str | None = None
    confidence: str | None = Field(default=None, max_length=32)
    expected_predecessors: list[WhiteboardLinkCandidateInput] | None = None
    possible_successors: list[WhiteboardLinkCandidateInput] | None = None
    requirements: list[str] | None = None
    metadata: dict[str, Any] | None = None


class CreateWhiteboardEdgeRequest(BaseModel):
    source_card_id: str = Field(min_length=1, max_length=128)
    target_card_id: str = Field(min_length=1, max_length=128)
    edge_type: str = Field(default="supports", max_length=64)
    author: str | None = Field(default=None, max_length=255)
    agent_run_id: str | None = Field(default=None, max_length=128)
    rationale: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class CreateWhiteboardNoteRequest(BaseModel):
    card_id: str | None = Field(default=None, max_length=128)
    author: str | None = Field(default=None, max_length=255)
    agent_run_id: str | None = Field(default=None, max_length=128)
    content: str = Field(min_length=1)
    metadata: dict[str, Any] = Field(default_factory=dict)


class RunWhiteboardTasksRequest(BaseModel):
    rounds: int | None = Field(default=None, ge=1, le=10)
    max_tasks_per_round: int | None = Field(default=None, ge=1, le=50)


class CreateWhiteboardSubscriptionRequest(BaseModel):
    subscriber_task_id: str | None = Field(default=None, max_length=128)
    subscriber_agent_run_id: str | None = Field(default=None, max_length=128)
    task_id: str | None = Field(default=None, max_length=128)
    agent_run_id: str | None = Field(default=None, max_length=128)
    filter: dict[str, Any] = Field(default_factory=dict)
    cursor_event_id: str | None = Field(default=None, max_length=128)
    status: str = Field(default="active", max_length=32)


class UpdateWhiteboardNotificationRequest(BaseModel):
    status: str = Field(max_length=32)
    claimed_by_agent_run_id: str | None = Field(default=None, max_length=128)
    lease_seconds: int | None = Field(default=None, ge=30, le=86400)


class CreateWhiteboardScheduleRequest(BaseModel):
    requested_by_task_id: str | None = Field(default=None, max_length=128)
    requested_by_agent_run_id: str | None = Field(default=None, max_length=128)
    task_id: str | None = Field(default=None, max_length=128)
    agent_run_id: str | None = Field(default=None, max_length=128)
    suggested_agent_name: str | None = Field(default=None, max_length=128)
    goal: str = Field(min_length=1)
    reason: str | None = None
    related_card_ids: list[str] = Field(default_factory=list)


class DecideWhiteboardScheduleRequest(BaseModel):
    status: str = Field(default="approved", max_length=32)
    decision: dict[str, Any] = Field(default_factory=dict)
    task_id: str | None = Field(default=None, max_length=128)
    parent_task_id: str | None = Field(default=None, max_length=128)
    root_task_id: str | None = Field(default=None, max_length=128)
    task_group: str | None = Field(default=None, max_length=128)
    agent_name: str | None = Field(default=None, max_length=128)


class SubmitWhiteboardEvidenceRequest(BaseModel):
    card_ids: list[str] = Field(default_factory=list)
    edge_ids: list[str] = Field(default_factory=list)
    finding_id: str | None = Field(default=None, max_length=128)
    summary: str | None = None
    mark_cards_submitted: bool = True


class SearchWhiteboardCardsRequest(BaseModel):
    query: str | None = None
    card_type: str | None = Field(default=None, max_length=64)
    status: str | None = Field(default=None, max_length=64)
    finding_id: str | None = Field(default=None, max_length=128)
    file_path: str | None = None
    candidate_status: str | None = Field(default=None, max_length=32)
    limit: int = Field(default=20, ge=1, le=100)


class ValidatorScaleRequest(BaseModel):
    project_id: str = Field(min_length=1)
    findings: list[dict[str, Any]] = Field(default_factory=list)
    workspace_host_path: str | None = None
    validator_rounds: int = Field(default=1, ge=1)
    max_parallel_validators: int = Field(default=2, ge=1)
    validator_agent_name: str = "opencode-validator"
    allow_external_network: bool = False
    retain_runtime_on_failure: bool = False
    wait_for_completion: bool = False


class RunPocRequest(BaseModel):
    image: str = "python:3.12-slim"
    command: list[str] = Field(min_length=1)
    env: dict[str, str] = Field(default_factory=dict)
    allow_external_network: bool = False
    retain_runtime_on_failure: bool = False
    timeout_seconds: int = Field(default=120, ge=1, le=3600)
    mount_workspace: bool = True
    expected_exit_code: int = 0
    mark_confirmed_on_success: bool = False
    network_name: str | None = None
    target_url: str | None = None
    allow_weak_isolation: bool = False


class StartSandboxServiceRequest(BaseModel):
    image: str = "python:3.12-slim"
    command: list[str] = Field(min_length=1)
    env: dict[str, str] = Field(default_factory=dict)
    service_name: str = Field(default="target", pattern=r"^[a-zA-Z0-9][a-zA-Z0-9_.-]{0,62}$")
    port: int = Field(default=8080, ge=1, le=65535)
    allow_external_network: bool = False
    retain_runtime_on_failure: bool = True
    mount_workspace: bool = True
    healthcheck_path: str | None = None
    startup_timeout_seconds: int = Field(default=30, ge=1, le=300)
    allow_weak_isolation: bool = False


class StartSandboxComposeRequest(BaseModel):
    compose_yaml: str = Field(min_length=1)
    service_name: str | None = Field(default=None, pattern=r"^[a-zA-Z0-9][a-zA-Z0-9_.-]{0,62}$")
    allow_external_network: bool = False
    retain_runtime_on_failure: bool = True
    mount_workspace: bool = True
    startup_timeout_seconds: int = Field(default=30, ge=1, le=300)
    allow_weak_isolation: bool = False
