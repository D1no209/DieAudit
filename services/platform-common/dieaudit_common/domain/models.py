from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from dieaudit_common.persistence.base import Base


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class Project(TimestampMixin, Base):
    __tablename__ = "projects"

    project_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), index=True)
    source_type: Mapped[str] = mapped_column(String(32))
    source_uri: Mapped[str | None] = mapped_column(Text, nullable=True)
    default_branch: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="created", index=True)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class ProjectSnapshot(TimestampMixin, Base):
    __tablename__ = "project_snapshots"

    snapshot_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.project_id"), index=True)
    source_type: Mapped[str] = mapped_column(String(32))
    source_ref: Mapped[str | None] = mapped_column(Text, nullable=True)
    workspace_path: Mapped[str] = mapped_column(Text)
    artifact_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    content_hash: Mapped[str | None] = mapped_column(String(128), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="ready", index=True)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class AuditRun(TimestampMixin, Base):
    __tablename__ = "audit_runs"

    audit_run_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.project_id"), index=True)
    snapshot_id: Mapped[str | None] = mapped_column(String(128), index=True, nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="created", index=True)
    pipeline_status: Mapped[str] = mapped_column(String(32), default="pending", index=True)
    current_stage: Mapped[str | None] = mapped_column(String(128), index=True, nullable=True)
    worker_id: Mapped[str | None] = mapped_column(String(128), index=True, nullable=True)
    cancel_requested: Mapped[bool] = mapped_column(default=False, index=True)
    workspace_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    allow_external_network: Mapped[bool] = mapped_column(default=False)
    retain_runtime_on_failure: Mapped[bool] = mapped_column(default=False)
    config_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    input_payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class PipelineRun(TimestampMixin, Base):
    __tablename__ = "pipeline_runs"

    pipeline_run_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    audit_run_id: Mapped[str] = mapped_column(ForeignKey("audit_runs.audit_run_id"), index=True)
    status: Mapped[str] = mapped_column(String(32), default="running", index=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    summary_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)


class PipelineStageRun(TimestampMixin, Base):
    __tablename__ = "pipeline_stage_runs"
    __table_args__ = (UniqueConstraint("pipeline_run_id", "stage", name="uq_pipeline_stage_run"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    pipeline_run_id: Mapped[str] = mapped_column(ForeignKey("pipeline_runs.pipeline_run_id"), index=True)
    audit_run_id: Mapped[str] = mapped_column(String(128), index=True)
    stage: Mapped[str] = mapped_column(String(128), index=True)
    status: Mapped[str] = mapped_column(String(32), default="pending", index=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    summary_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    artifact_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)


class AuditEvent(TimestampMixin, Base):
    __tablename__ = "audit_events"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    audit_run_id: Mapped[str] = mapped_column(String(128), index=True)
    subject: Mapped[str] = mapped_column(String(255), index=True)
    event_type: Mapped[str] = mapped_column(String(128), index=True)
    payload_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class AgentRun(TimestampMixin, Base):
    __tablename__ = "agent_runs"

    agent_run_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    audit_run_id: Mapped[str] = mapped_column(String(128), index=True)
    project_id: Mapped[str] = mapped_column(String(128), index=True)
    agent_name: Mapped[str] = mapped_column(String(128), index=True)
    template_name: Mapped[str] = mapped_column(String(128))
    protocol_kind: Mapped[str] = mapped_column(String(64), default="agent-client-protocol")
    status: Mapped[str] = mapped_column(String(32), default="created", index=True)
    runtime_id: Mapped[str | None] = mapped_column(String(128), index=True, nullable=True)
    acp_session_id: Mapped[str | None] = mapped_column(String(128), index=True, nullable=True)
    decision_status: Mapped[str | None] = mapped_column(String(32), index=True, nullable=True)
    decision_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    input_payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    output_payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    artifact_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    events: Mapped[list["AgentRunEvent"]] = relationship(back_populates="agent_run")


class AgentRunEvent(TimestampMixin, Base):
    __tablename__ = "agent_run_events"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    agent_run_id: Mapped[str] = mapped_column(ForeignKey("agent_runs.agent_run_id"), index=True)
    event_type: Mapped[str] = mapped_column(String(128), index=True)
    payload_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)

    agent_run: Mapped[AgentRun] = relationship(back_populates="events")


class ToolRun(TimestampMixin, Base):
    __tablename__ = "tool_runs"

    tool_run_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    audit_run_id: Mapped[str] = mapped_column(String(128), index=True)
    project_id: Mapped[str] = mapped_column(String(128), index=True)
    tool_name: Mapped[str] = mapped_column(String(128), index=True)
    status: Mapped[str] = mapped_column(String(32), default="created", index=True)
    input_payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    output_payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    artifact_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)


class AgentRuntime(TimestampMixin, Base):
    __tablename__ = "agent_runtimes"

    runtime_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    audit_run_id: Mapped[str] = mapped_column(String(128), index=True)
    project_id: Mapped[str] = mapped_column(String(128), index=True)
    status: Mapped[str] = mapped_column(String(32), index=True)
    runtime_kind: Mapped[str] = mapped_column(String(64), index=True)
    runner_container_id: Mapped[str | None] = mapped_column(String(128), index=True, nullable=True)
    runner_container_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    network_name: Mapped[str | None] = mapped_column(String(255), index=True, nullable=True)
    mcp_containers: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    container_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    endpoint_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    ttl_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True, nullable=True)
    cleanup_status: Mapped[str] = mapped_column(String(32), index=True)
    cleanup_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class AgentTranscriptEvent(TimestampMixin, Base):
    __tablename__ = "agent_transcript_events"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    agent_run_id: Mapped[str] = mapped_column(String(128), index=True)
    audit_run_id: Mapped[str] = mapped_column(String(128), index=True)
    runtime_id: Mapped[str | None] = mapped_column(String(128), index=True, nullable=True)
    seq: Mapped[int] = mapped_column(Integer, index=True)
    event_type: Mapped[str] = mapped_column(String(128), index=True)
    session_id: Mapped[str | None] = mapped_column(String(128), index=True, nullable=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    content_text: Mapped[str | None] = mapped_column(Text, nullable=True)


class Finding(TimestampMixin, Base):
    __tablename__ = "findings"

    finding_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    audit_run_id: Mapped[str] = mapped_column(String(128), index=True)
    project_id: Mapped[str] = mapped_column(String(128), index=True)
    title: Mapped[str] = mapped_column(String(255))
    severity: Mapped[str] = mapped_column(String(32), default="unknown", index=True)
    status: Mapped[str] = mapped_column(String(32), default="candidate", index=True)
    file_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    line_start: Mapped[int | None] = mapped_column(Integer, nullable=True)
    line_end: Mapped[int | None] = mapped_column(Integer, nullable=True)
    rule_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    source: Mapped[str] = mapped_column(String(64), default="agent", index=True)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    raw_result: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class Evidence(TimestampMixin, Base):
    __tablename__ = "evidence"

    evidence_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    finding_id: Mapped[str | None] = mapped_column(String(128), index=True, nullable=True)
    audit_run_id: Mapped[str] = mapped_column(String(128), index=True)
    kind: Mapped[str] = mapped_column(String(64), index=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    artifact_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    payload_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class FindingTriageDecision(TimestampMixin, Base):
    __tablename__ = "finding_triage_decisions"

    decision_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    audit_run_id: Mapped[str] = mapped_column(String(128), index=True)
    project_id: Mapped[str] = mapped_column(String(128), index=True)
    finding_id: Mapped[str | None] = mapped_column(String(128), index=True, nullable=True)
    card_id: Mapped[str | None] = mapped_column(String(128), index=True, nullable=True)
    agent_run_id: Mapped[str | None] = mapped_column(String(128), index=True, nullable=True)
    decision_status: Mapped[str] = mapped_column(String(32), index=True)
    decision_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    deep_dive_allowed: Mapped[bool] = mapped_column(Boolean, index=True)
    poc_allowed: Mapped[bool] = mapped_column(Boolean, index=True)
    confidence: Mapped[str | None] = mapped_column(String(32), nullable=True)
    signals: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class Report(TimestampMixin, Base):
    __tablename__ = "reports"

    report_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    audit_run_id: Mapped[str] = mapped_column(String(128), index=True)
    title: Mapped[str] = mapped_column(String(255))
    format: Mapped[str] = mapped_column(String(32), default="markdown")
    artifact_id: Mapped[str | None] = mapped_column(String(512), nullable=True)
    summary_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class Artifact(TimestampMixin, Base):
    __tablename__ = "artifacts"

    artifact_id: Mapped[str] = mapped_column(String(512), primary_key=True)
    artifact_uri: Mapped[str] = mapped_column(Text)
    storage_backend: Mapped[str] = mapped_column(String(32), default="local", index=True)
    path: Mapped[str] = mapped_column(Text)
    content_type: Mapped[str | None] = mapped_column(String(255), nullable=True)
    sha256: Mapped[str | None] = mapped_column(String(128), index=True, nullable=True)
    size: Mapped[int] = mapped_column(Integer, default=0)
    audit_run_id: Mapped[str | None] = mapped_column(String(128), index=True, nullable=True)
    project_id: Mapped[str | None] = mapped_column(String(128), index=True, nullable=True)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class DeliverableArtifact(TimestampMixin, Base):
    __tablename__ = "deliverable_artifacts"

    artifact_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    audit_run_id: Mapped[str] = mapped_column(String(128), index=True)
    project_id: Mapped[str] = mapped_column(String(128), index=True)
    finding_id: Mapped[str | None] = mapped_column(String(128), index=True, nullable=True)
    kind: Mapped[str] = mapped_column(String(64), index=True)
    path: Mapped[str] = mapped_column(Text)
    title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    content_type: Mapped[str | None] = mapped_column(String(255), nullable=True)
    size: Mapped[int] = mapped_column(Integer)
    sha256: Mapped[str | None] = mapped_column(String(128), index=True, nullable=True)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class RuntimeContainer(TimestampMixin, Base):
    __tablename__ = "runtime_containers"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    audit_run_id: Mapped[str] = mapped_column(String(128), index=True)
    project_id: Mapped[str | None] = mapped_column(String(128), index=True, nullable=True)
    agent_run_id: Mapped[str | None] = mapped_column(String(128), index=True, nullable=True)
    container_id: Mapped[str] = mapped_column(String(128), unique=True)
    container_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    image: Mapped[str] = mapped_column(Text)
    role: Mapped[str] = mapped_column(String(32), index=True)
    status: Mapped[str] = mapped_column(String(32), default="created", index=True)
    exit_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    log_artifact_id: Mapped[str | None] = mapped_column(String(512), nullable=True)
    labels_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class WorkerHeartbeat(TimestampMixin, Base):
    __tablename__ = "worker_heartbeats"

    worker_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    service_name: Mapped[str] = mapped_column(String(128), index=True)
    hostname: Mapped[str] = mapped_column(String(255), index=True)
    status: Mapped[str] = mapped_column(String(32), default="starting", index=True)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True, nullable=False)
    current_audit_run_id: Mapped[str | None] = mapped_column(String(128), index=True, nullable=True)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class ApiKey(TimestampMixin, Base):
    __tablename__ = "api_keys"

    key_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), index=True)
    key_hash: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    scopes: Mapped[list[str]] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(32), default="active", index=True)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    deactivated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class KnowledgeDocument(TimestampMixin, Base):
    __tablename__ = "knowledge_documents"

    document_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    title: Mapped[str] = mapped_column(String(255), index=True)
    source_name: Mapped[str] = mapped_column(Text)
    content_type: Mapped[str | None] = mapped_column(String(255), nullable=True)
    scope: Mapped[str] = mapped_column(String(32), default="global", index=True)
    project_id: Mapped[str | None] = mapped_column(String(128), index=True, nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="indexed", index=True)
    chunk_count: Mapped[int] = mapped_column(Integer, default=0)
    artifact_id: Mapped[str | None] = mapped_column(String(512), nullable=True)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class WhiteboardCard(TimestampMixin, Base):
    __tablename__ = "whiteboard_cards"

    card_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    audit_run_id: Mapped[str] = mapped_column(String(128), index=True)
    title: Mapped[str] = mapped_column(String(255))
    card_type: Mapped[str] = mapped_column(String(64), default="observation", index=True)
    status: Mapped[str] = mapped_column(String(64), default="open", index=True)
    content: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class WhiteboardEdge(TimestampMixin, Base):
    __tablename__ = "whiteboard_edges"

    edge_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    audit_run_id: Mapped[str] = mapped_column(String(128), index=True)
    source_card_id: Mapped[str] = mapped_column(String(128), index=True)
    target_card_id: Mapped[str] = mapped_column(String(128), index=True)
    edge_type: Mapped[str] = mapped_column(String(64), default="supports", index=True)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
