"""agent runtime, transcript, triage, and deliverable package tables

Revision ID: 0002_agent_runtime_deliverables
Revises: 0001_baseline
Create Date: 2026-06-29
"""

from alembic import op
import sqlalchemy as sa


revision = "0002_agent_runtime_deliverables"
down_revision = "0001_baseline"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "agent_runtimes",
        sa.Column("runtime_id", sa.String(length=128), nullable=False),
        sa.Column("audit_run_id", sa.String(length=128), nullable=False),
        sa.Column("project_id", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("runtime_kind", sa.String(length=64), nullable=False),
        sa.Column("runner_container_id", sa.String(length=128), nullable=True),
        sa.Column("runner_container_name", sa.String(length=255), nullable=True),
        sa.Column("network_name", sa.String(length=255), nullable=True),
        sa.Column("mcp_containers", sa.JSON(), nullable=False),
        sa.Column("container_ids", sa.JSON(), nullable=False),
        sa.Column("endpoint_url", sa.Text(), nullable=True),
        sa.Column("ttl_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cleanup_status", sa.String(length=32), nullable=False),
        sa.Column("cleanup_reason", sa.Text(), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("runtime_id"),
    )
    for column in (
        "audit_run_id",
        "project_id",
        "status",
        "runtime_kind",
        "runner_container_id",
        "network_name",
        "ttl_expires_at",
        "cleanup_status",
    ):
        op.create_index(f"ix_agent_runtimes_{column}", "agent_runtimes", [column])

    for column in (
        sa.Column("runtime_id", sa.String(length=128), nullable=True),
        sa.Column("acp_session_id", sa.String(length=128), nullable=True),
        sa.Column("decision_status", sa.String(length=32), nullable=True),
        sa.Column("decision_reason", sa.Text(), nullable=True),
    ):
        op.add_column("agent_runs", column)
    for column in ("runtime_id", "acp_session_id", "decision_status"):
        op.create_index(f"ix_agent_runs_{column}", "agent_runs", [column])

    op.create_table(
        "agent_transcript_events",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("agent_run_id", sa.String(length=128), nullable=False),
        sa.Column("audit_run_id", sa.String(length=128), nullable=False),
        sa.Column("runtime_id", sa.String(length=128), nullable=True),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(length=128), nullable=False),
        sa.Column("session_id", sa.String(length=128), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("content_text", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    for column in ("agent_run_id", "audit_run_id", "runtime_id", "seq", "event_type", "session_id"):
        op.create_index(f"ix_agent_transcript_events_{column}", "agent_transcript_events", [column])

    op.create_table(
        "finding_triage_decisions",
        sa.Column("decision_id", sa.String(length=128), nullable=False),
        sa.Column("audit_run_id", sa.String(length=128), nullable=False),
        sa.Column("project_id", sa.String(length=128), nullable=False),
        sa.Column("finding_id", sa.String(length=128), nullable=True),
        sa.Column("card_id", sa.String(length=128), nullable=True),
        sa.Column("agent_run_id", sa.String(length=128), nullable=True),
        sa.Column("decision_status", sa.String(length=32), nullable=False),
        sa.Column("decision_reason", sa.Text(), nullable=True),
        sa.Column("deep_dive_allowed", sa.Boolean(), nullable=False),
        sa.Column("poc_allowed", sa.Boolean(), nullable=False),
        sa.Column("confidence", sa.String(length=32), nullable=True),
        sa.Column("signals", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("decision_id"),
    )
    for column in (
        "audit_run_id",
        "project_id",
        "finding_id",
        "card_id",
        "agent_run_id",
        "decision_status",
        "deep_dive_allowed",
        "poc_allowed",
    ):
        op.create_index(f"ix_finding_triage_decisions_{column}", "finding_triage_decisions", [column])

    op.create_table(
        "deliverable_artifacts",
        sa.Column("artifact_id", sa.String(length=128), nullable=False),
        sa.Column("audit_run_id", sa.String(length=128), nullable=False),
        sa.Column("project_id", sa.String(length=128), nullable=False),
        sa.Column("finding_id", sa.String(length=128), nullable=True),
        sa.Column("kind", sa.String(length=64), nullable=False),
        sa.Column("path", sa.Text(), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=True),
        sa.Column("content_type", sa.String(length=255), nullable=True),
        sa.Column("size", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.String(length=128), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("artifact_id"),
    )
    for column in ("audit_run_id", "project_id", "finding_id", "kind", "sha256"):
        op.create_index(f"ix_deliverable_artifacts_{column}", "deliverable_artifacts", [column])


def downgrade() -> None:
    for column in ("audit_run_id", "project_id", "finding_id", "kind", "sha256"):
        op.drop_index(f"ix_deliverable_artifacts_{column}", table_name="deliverable_artifacts")
    op.drop_table("deliverable_artifacts")

    for column in (
        "audit_run_id",
        "project_id",
        "finding_id",
        "card_id",
        "agent_run_id",
        "decision_status",
        "deep_dive_allowed",
        "poc_allowed",
    ):
        op.drop_index(f"ix_finding_triage_decisions_{column}", table_name="finding_triage_decisions")
    op.drop_table("finding_triage_decisions")

    for column in ("agent_run_id", "audit_run_id", "runtime_id", "seq", "event_type", "session_id"):
        op.drop_index(f"ix_agent_transcript_events_{column}", table_name="agent_transcript_events")
    op.drop_table("agent_transcript_events")

    for column in ("runtime_id", "acp_session_id", "decision_status"):
        op.drop_index(f"ix_agent_runs_{column}", table_name="agent_runs")
    for column in ("decision_reason", "decision_status", "acp_session_id", "runtime_id"):
        op.drop_column("agent_runs", column)

    for column in (
        "audit_run_id",
        "project_id",
        "status",
        "runtime_kind",
        "runner_container_id",
        "network_name",
        "ttl_expires_at",
        "cleanup_status",
    ):
        op.drop_index(f"ix_agent_runtimes_{column}", table_name="agent_runtimes")
    op.drop_table("agent_runtimes")
