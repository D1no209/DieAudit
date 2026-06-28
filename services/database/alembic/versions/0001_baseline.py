"""baseline schema for split-service architecture

Revision ID: 0001_baseline
Revises:
Create Date: 2026-06-27
"""

from alembic import op
import sqlalchemy as sa


revision = "0001_baseline"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "projects",
        sa.Column("project_id", sa.String(length=128), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("source_type", sa.String(length=32), nullable=False),
        sa.Column("source_uri", sa.Text(), nullable=True),
        sa.Column("default_branch", sa.String(length=255), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("project_id"),
    )
    op.create_index("ix_projects_name", "projects", ["name"])
    op.create_index("ix_projects_status", "projects", ["status"])

    op.create_table(
        "project_snapshots",
        sa.Column("snapshot_id", sa.String(length=128), nullable=False),
        sa.Column("project_id", sa.String(length=128), nullable=False),
        sa.Column("source_type", sa.String(length=32), nullable=False),
        sa.Column("source_ref", sa.Text(), nullable=True),
        sa.Column("workspace_path", sa.Text(), nullable=False),
        sa.Column("artifact_path", sa.Text(), nullable=True),
        sa.Column("content_hash", sa.String(length=128), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.project_id"]),
        sa.PrimaryKeyConstraint("snapshot_id"),
    )
    op.create_index("ix_project_snapshots_project_id", "project_snapshots", ["project_id"])
    op.create_index("ix_project_snapshots_status", "project_snapshots", ["status"])

    op.create_table(
        "audit_runs",
        sa.Column("audit_run_id", sa.String(length=128), nullable=False),
        sa.Column("project_id", sa.String(length=128), nullable=False),
        sa.Column("snapshot_id", sa.String(length=128), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("pipeline_status", sa.String(length=32), nullable=False),
        sa.Column("current_stage", sa.String(length=128), nullable=True),
        sa.Column("worker_id", sa.String(length=128), nullable=True),
        sa.Column("cancel_requested", sa.Boolean(), nullable=False),
        sa.Column("workspace_path", sa.Text(), nullable=True),
        sa.Column("allow_external_network", sa.Boolean(), nullable=False),
        sa.Column("retain_runtime_on_failure", sa.Boolean(), nullable=False),
        sa.Column("config_json", sa.JSON(), nullable=False),
        sa.Column("input_payload", sa.JSON(), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.project_id"]),
        sa.PrimaryKeyConstraint("audit_run_id"),
    )
    for column in ("project_id", "snapshot_id", "status", "pipeline_status", "current_stage", "worker_id", "cancel_requested"):
        op.create_index(f"ix_audit_runs_{column}", "audit_runs", [column])

    op.create_table(
        "pipeline_runs",
        sa.Column("pipeline_run_id", sa.String(length=128), nullable=False),
        sa.Column("audit_run_id", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("summary_json", sa.JSON(), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["audit_run_id"], ["audit_runs.audit_run_id"]),
        sa.PrimaryKeyConstraint("pipeline_run_id"),
    )
    op.create_index("ix_pipeline_runs_audit_run_id", "pipeline_runs", ["audit_run_id"])
    op.create_index("ix_pipeline_runs_status", "pipeline_runs", ["status"])

    op.create_table(
        "pipeline_stage_runs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("pipeline_run_id", sa.String(length=128), nullable=False),
        sa.Column("audit_run_id", sa.String(length=128), nullable=False),
        sa.Column("stage", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("summary_json", sa.JSON(), nullable=False),
        sa.Column("artifact_ids", sa.JSON(), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["pipeline_run_id"], ["pipeline_runs.pipeline_run_id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("pipeline_run_id", "stage", name="uq_pipeline_stage_run"),
    )
    for column in ("pipeline_run_id", "audit_run_id", "stage", "status"):
        op.create_index(f"ix_pipeline_stage_runs_{column}", "pipeline_stage_runs", [column])

    _create_json_event_table()
    _create_runtime_tables()
    _create_result_tables()


def _create_json_event_table() -> None:
    op.create_table(
        "audit_events",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("audit_run_id", sa.String(length=128), nullable=False),
        sa.Column("subject", sa.String(length=255), nullable=False),
        sa.Column("event_type", sa.String(length=128), nullable=False),
        sa.Column("payload_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    for column in ("audit_run_id", "subject", "event_type"):
        op.create_index(f"ix_audit_events_{column}", "audit_events", [column])


def _create_runtime_tables() -> None:
    op.create_table(
        "worker_heartbeats",
        sa.Column("worker_id", sa.String(length=128), nullable=False),
        sa.Column("service_name", sa.String(length=128), nullable=False),
        sa.Column("hostname", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("current_audit_run_id", sa.String(length=128), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("worker_id"),
    )
    for column in ("service_name", "hostname", "status", "last_seen_at", "current_audit_run_id"):
        op.create_index(f"ix_worker_heartbeats_{column}", "worker_heartbeats", [column])

    op.create_table(
        "api_keys",
        sa.Column("key_id", sa.String(length=128), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("key_hash", sa.String(length=128), nullable=False),
        sa.Column("scopes", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deactivated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("key_id"),
        sa.UniqueConstraint("key_hash"),
    )
    op.create_index("ix_api_keys_key_hash", "api_keys", ["key_hash"])
    op.create_index("ix_api_keys_name", "api_keys", ["name"])
    op.create_index("ix_api_keys_status", "api_keys", ["status"])


def _create_result_tables() -> None:
    simple_tables = {
        "agent_runs": [
            sa.Column("agent_run_id", sa.String(length=128), nullable=False),
            sa.Column("audit_run_id", sa.String(length=128), nullable=False),
            sa.Column("project_id", sa.String(length=128), nullable=False),
            sa.Column("agent_name", sa.String(length=128), nullable=False),
            sa.Column("template_name", sa.String(length=128), nullable=False),
            sa.Column("protocol_kind", sa.String(length=64), nullable=False),
            sa.Column("status", sa.String(length=32), nullable=False),
            sa.Column("input_payload", sa.JSON(), nullable=False),
            sa.Column("output_payload", sa.JSON(), nullable=False),
            sa.Column("artifact_path", sa.Text(), nullable=True),
            sa.Column("error", sa.Text(), nullable=True),
        ],
        "tool_runs": [
            sa.Column("tool_run_id", sa.String(length=128), nullable=False),
            sa.Column("audit_run_id", sa.String(length=128), nullable=False),
            sa.Column("project_id", sa.String(length=128), nullable=False),
            sa.Column("tool_name", sa.String(length=128), nullable=False),
            sa.Column("status", sa.String(length=32), nullable=False),
            sa.Column("input_payload", sa.JSON(), nullable=False),
            sa.Column("output_payload", sa.JSON(), nullable=False),
            sa.Column("artifact_ids", sa.JSON(), nullable=False),
            sa.Column("error", sa.Text(), nullable=True),
        ],
        "findings": [
            sa.Column("finding_id", sa.String(length=128), nullable=False),
            sa.Column("audit_run_id", sa.String(length=128), nullable=False),
            sa.Column("project_id", sa.String(length=128), nullable=False),
            sa.Column("title", sa.String(length=255), nullable=False),
            sa.Column("severity", sa.String(length=32), nullable=False),
            sa.Column("status", sa.String(length=32), nullable=False),
            sa.Column("file_path", sa.Text(), nullable=True),
            sa.Column("line_start", sa.Integer(), nullable=True),
            sa.Column("line_end", sa.Integer(), nullable=True),
            sa.Column("rule_id", sa.String(length=255), nullable=True),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("source", sa.String(length=64), nullable=False),
            sa.Column("metadata_json", sa.JSON(), nullable=False),
            sa.Column("raw_result", sa.JSON(), nullable=False),
        ],
        "artifacts": [
            sa.Column("artifact_id", sa.String(length=512), nullable=False),
            sa.Column("artifact_uri", sa.Text(), nullable=False),
            sa.Column("storage_backend", sa.String(length=32), nullable=False),
            sa.Column("path", sa.Text(), nullable=False),
            sa.Column("content_type", sa.String(length=255), nullable=True),
            sa.Column("sha256", sa.String(length=128), nullable=True),
            sa.Column("size", sa.Integer(), nullable=False),
            sa.Column("audit_run_id", sa.String(length=128), nullable=True),
            sa.Column("project_id", sa.String(length=128), nullable=True),
            sa.Column("metadata_json", sa.JSON(), nullable=False),
        ],
    }
    for table_name, columns in simple_tables.items():
        primary = columns[0].name
        op.create_table(
            table_name,
            *columns,
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.PrimaryKeyConstraint(primary),
        )
    op.create_table(
        "agent_run_events",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("agent_run_id", sa.String(length=128), nullable=False),
        sa.Column("event_type", sa.String(length=128), nullable=False),
        sa.Column("payload_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["agent_run_id"], ["agent_runs.agent_run_id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "evidence",
        sa.Column("evidence_id", sa.String(length=128), nullable=False),
        sa.Column("finding_id", sa.String(length=128), nullable=True),
        sa.Column("audit_run_id", sa.String(length=128), nullable=False),
        sa.Column("kind", sa.String(length=64), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("artifact_ids", sa.JSON(), nullable=False),
        sa.Column("payload_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("evidence_id"),
    )
    op.create_table(
        "reports",
        sa.Column("report_id", sa.String(length=128), nullable=False),
        sa.Column("audit_run_id", sa.String(length=128), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("format", sa.String(length=32), nullable=False),
        sa.Column("artifact_id", sa.String(length=512), nullable=True),
        sa.Column("summary_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("report_id"),
    )
    op.create_table(
        "runtime_containers",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("audit_run_id", sa.String(length=128), nullable=False),
        sa.Column("project_id", sa.String(length=128), nullable=True),
        sa.Column("agent_run_id", sa.String(length=128), nullable=True),
        sa.Column("container_id", sa.String(length=128), nullable=False),
        sa.Column("container_name", sa.String(length=255), nullable=True),
        sa.Column("image", sa.Text(), nullable=False),
        sa.Column("role", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("exit_code", sa.Integer(), nullable=True),
        sa.Column("log_artifact_id", sa.String(length=512), nullable=True),
        sa.Column("labels_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("container_id"),
    )
    op.create_table(
        "knowledge_documents",
        sa.Column("document_id", sa.String(length=128), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("source_name", sa.Text(), nullable=False),
        sa.Column("content_type", sa.String(length=255), nullable=True),
        sa.Column("scope", sa.String(length=32), nullable=False),
        sa.Column("project_id", sa.String(length=128), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("chunk_count", sa.Integer(), nullable=False),
        sa.Column("artifact_id", sa.String(length=512), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("document_id"),
    )
    op.create_table(
        "whiteboard_cards",
        sa.Column("card_id", sa.String(length=128), nullable=False),
        sa.Column("audit_run_id", sa.String(length=128), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("card_type", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=64), nullable=False),
        sa.Column("content", sa.Text(), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("card_id"),
    )
    op.create_table(
        "whiteboard_edges",
        sa.Column("edge_id", sa.String(length=128), nullable=False),
        sa.Column("audit_run_id", sa.String(length=128), nullable=False),
        sa.Column("source_card_id", sa.String(length=128), nullable=False),
        sa.Column("target_card_id", sa.String(length=128), nullable=False),
        sa.Column("edge_type", sa.String(length=64), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("edge_id"),
    )


def downgrade() -> None:
    for table in (
        "whiteboard_edges",
        "whiteboard_cards",
        "knowledge_documents",
        "runtime_containers",
        "reports",
        "evidence",
        "agent_run_events",
        "artifacts",
        "findings",
        "tool_runs",
        "agent_runs",
        "api_keys",
        "worker_heartbeats",
        "audit_events",
        "pipeline_stage_runs",
        "pipeline_runs",
        "audit_runs",
        "project_snapshots",
        "projects",
    ):
        op.drop_table(table)
