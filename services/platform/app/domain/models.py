from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class AuditRun(TimestampMixin, Base):
    __tablename__ = "audit_runs"

    audit_run_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    project_id: Mapped[str] = mapped_column(String(128), index=True)
    snapshot_id: Mapped[str | None] = mapped_column(String(128), index=True, nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="created")
    validator_rounds: Mapped[int] = mapped_column(Integer, default=1)
    max_parallel_validators: Mapped[int] = mapped_column(Integer, default=2)
    allow_external_network: Mapped[bool] = mapped_column(default=False)
    retain_runtime_on_failure: Mapped[bool] = mapped_column(default=False)
    config: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class AuditRunEvent(TimestampMixin, Base):
    __tablename__ = "audit_run_events"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    audit_run_id: Mapped[str] = mapped_column(String(128), index=True)
    event_type: Mapped[str] = mapped_column(String(128), index=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class PlatformAuditEvent(TimestampMixin, Base):
    __tablename__ = "platform_audit_events"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    service: Mapped[str] = mapped_column(String(64), index=True)
    method: Mapped[str] = mapped_column(String(16), index=True)
    path: Mapped[str] = mapped_column(Text)
    status_code: Mapped[int] = mapped_column(Integer, index=True)
    client_host: Mapped[str | None] = mapped_column(String(128), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(Text, nullable=True)
    auth_enabled: Mapped[bool] = mapped_column(default=False)
    auth_result: Mapped[str] = mapped_column(String(32), index=True, default="not_required")
    request_id: Mapped[str | None] = mapped_column(String(128), index=True, nullable=True)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class ApiKeyRecord(TimestampMixin, Base):
    __tablename__ = "api_keys"

    key_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), index=True)
    key_hash: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    scopes: Mapped[list[str]] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(32), index=True, default="active")
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    deactivated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class Project(TimestampMixin, Base):
    __tablename__ = "projects"

    project_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), index=True)
    source_type: Mapped[str] = mapped_column(String(32))
    source_uri: Mapped[str | None] = mapped_column(Text, nullable=True)
    default_branch: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="created")
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class ProjectSnapshot(TimestampMixin, Base):
    __tablename__ = "project_snapshots"

    snapshot_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    project_id: Mapped[str] = mapped_column(String(128), index=True)
    source_type: Mapped[str] = mapped_column(String(32))
    source_ref: Mapped[str | None] = mapped_column(Text, nullable=True)
    workspace_path: Mapped[str] = mapped_column(Text)
    artifact_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    content_hash: Mapped[str | None] = mapped_column(String(128), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="ready")
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class ContainerRun(TimestampMixin, Base):
    __tablename__ = "container_runs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    audit_run_id: Mapped[str] = mapped_column(String(128), index=True)
    project_id: Mapped[str] = mapped_column(String(128), index=True)
    agent_run_id: Mapped[str | None] = mapped_column(String(128), index=True, nullable=True)
    container_id: Mapped[str] = mapped_column(String(128), unique=True)
    container_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    image: Mapped[str] = mapped_column(Text)
    role: Mapped[str] = mapped_column(String(32), index=True)
    status: Mapped[str] = mapped_column(String(32), default="created")
    exit_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    log_artifact: Mapped[str | None] = mapped_column(Text, nullable=True)
    labels: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class RuntimeNetwork(TimestampMixin, Base):
    __tablename__ = "runtime_networks"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    audit_run_id: Mapped[str] = mapped_column(String(128), index=True)
    name: Mapped[str] = mapped_column(String(255), unique=True)
    status: Mapped[str] = mapped_column(String(32), default="created")


class AgentRun(TimestampMixin, Base):
    __tablename__ = "agent_runs"

    agent_run_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    audit_run_id: Mapped[str] = mapped_column(String(128), index=True)
    project_id: Mapped[str] = mapped_column(String(128), index=True)
    agent_name: Mapped[str] = mapped_column(String(128), index=True)
    template_name: Mapped[str] = mapped_column(String(128))
    protocol_kind: Mapped[str] = mapped_column(String(64), default="legacy-http")
    status: Mapped[str] = mapped_column(String(32), default="created")
    input_summary: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    output_summary: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    artifact_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    events: Mapped[list["AgentRunEvent"]] = relationship(back_populates="agent_run")


class AgentRunEvent(TimestampMixin, Base):
    __tablename__ = "agent_run_events"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    agent_run_id: Mapped[str] = mapped_column(ForeignKey("agent_runs.agent_run_id"), index=True)
    event_type: Mapped[str] = mapped_column(String(128), index=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)

    agent_run: Mapped[AgentRun] = relationship(back_populates="events")


class RuntimePackage(TimestampMixin, Base):
    __tablename__ = "runtime_packages"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    agent_run_id: Mapped[str] = mapped_column(String(128), index=True)
    path: Mapped[str] = mapped_column(Text)
    content_hash: Mapped[str] = mapped_column(String(128))
    manifest: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class Finding(TimestampMixin, Base):
    __tablename__ = "findings"

    finding_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    audit_run_id: Mapped[str] = mapped_column(String(128), index=True)
    project_id: Mapped[str] = mapped_column(String(128), index=True)
    title: Mapped[str] = mapped_column(String(255))
    severity: Mapped[str] = mapped_column(String(32), default="unknown")
    status: Mapped[str] = mapped_column(String(32), default="candidate")
    file_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    line_start: Mapped[int | None] = mapped_column(Integer, nullable=True)
    line_end: Mapped[int | None] = mapped_column(Integer, nullable=True)
    rule_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    source: Mapped[str] = mapped_column(String(64), default="agent")
    raw: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class Evidence(TimestampMixin, Base):
    __tablename__ = "evidence"

    evidence_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    finding_id: Mapped[str] = mapped_column(String(128), index=True)
    audit_run_id: Mapped[str] = mapped_column(String(128), index=True)
    kind: Mapped[str] = mapped_column(String(64))
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    artifact_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class KnowledgeDocument(TimestampMixin, Base):
    __tablename__ = "knowledge_documents"

    document_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    title: Mapped[str] = mapped_column(String(255), index=True)
    source_name: Mapped[str] = mapped_column(Text)
    content_type: Mapped[str | None] = mapped_column(String(255), nullable=True)
    scope: Mapped[str] = mapped_column(String(32), index=True, default="global")
    project_id: Mapped[str | None] = mapped_column(String(128), index=True, nullable=True)
    status: Mapped[str] = mapped_column(String(32), index=True, default="indexed")
    chunk_count: Mapped[int] = mapped_column(Integer, default=0)
    artifact_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class KnowledgeChunk(TimestampMixin, Base):
    __tablename__ = "knowledge_chunks"

    chunk_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    document_id: Mapped[str] = mapped_column(String(128), index=True)
    scope: Mapped[str] = mapped_column(String(32), index=True, default="global")
    project_id: Mapped[str | None] = mapped_column(String(128), index=True, nullable=True)
    chunk_index: Mapped[int] = mapped_column(Integer, default=0)
    text: Mapped[str] = mapped_column(Text)
    token_count: Mapped[int] = mapped_column(Integer, default=0)
    vector_id: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class ValidationAttempt(TimestampMixin, Base):
    __tablename__ = "validation_attempts"

    attempt_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    finding_id: Mapped[str] = mapped_column(String(128), index=True)
    audit_run_id: Mapped[str] = mapped_column(String(128), index=True)
    agent_run_id: Mapped[str | None] = mapped_column(String(128), index=True, nullable=True)
    round_index: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String(32), default="created")
    result: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class ReportArtifact(TimestampMixin, Base):
    __tablename__ = "report_artifacts"

    report_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    audit_run_id: Mapped[str] = mapped_column(String(128), index=True)
    project_id: Mapped[str] = mapped_column(String(128), index=True)
    kind: Mapped[str] = mapped_column(String(64))
    path: Mapped[str] = mapped_column(Text)
    summary: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class AgentTemplateRecord(TimestampMixin, Base):
    __tablename__ = "agent_templates"

    name: Mapped[str] = mapped_column(String(128), primary_key=True)
    body: Mapped[dict[str, Any]] = mapped_column(JSON)


class McpTemplateRecord(TimestampMixin, Base):
    __tablename__ = "mcp_templates"

    name: Mapped[str] = mapped_column(String(128), primary_key=True)
    body: Mapped[dict[str, Any]] = mapped_column(JSON)
