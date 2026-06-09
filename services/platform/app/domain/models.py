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
    status: Mapped[str] = mapped_column(String(32), default="created")
    validator_rounds: Mapped[int] = mapped_column(Integer, default=1)
    max_parallel_validators: Mapped[int] = mapped_column(Integer, default=2)
    allow_external_network: Mapped[bool] = mapped_column(default=False)
    retain_runtime_on_failure: Mapped[bool] = mapped_column(default=False)
    config: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


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


class AgentTemplateRecord(TimestampMixin, Base):
    __tablename__ = "agent_templates"

    name: Mapped[str] = mapped_column(String(128), primary_key=True)
    body: Mapped[dict[str, Any]] = mapped_column(JSON)


class McpTemplateRecord(TimestampMixin, Base):
    __tablename__ = "mcp_templates"

    name: Mapped[str] = mapped_column(String(128), primary_key=True)
    body: Mapped[dict[str, Any]] = mapped_column(JSON)
