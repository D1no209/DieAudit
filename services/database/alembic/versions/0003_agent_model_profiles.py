"""agent model profiles

Revision ID: 0003_agent_model_profiles
Revises: 0002_agent_runtime_deliverables
Create Date: 2026-07-01
"""

from alembic import op
import sqlalchemy as sa


revision = "0003_agent_model_profiles"
down_revision = "0002_agent_runtime_deliverables"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "agent_model_profiles",
        sa.Column("role", sa.String(length=128), nullable=False),
        sa.Column("runtime_id", sa.String(length=128), nullable=False),
        sa.Column("provider_type", sa.String(length=64), nullable=False),
        sa.Column("base_url", sa.Text(), nullable=True),
        sa.Column("model_name", sa.String(length=255), nullable=False),
        sa.Column("api_key", sa.Text(), nullable=True),
        sa.Column("temperature", sa.Float(), nullable=True),
        sa.Column("max_output_tokens", sa.Integer(), nullable=True),
        sa.Column("context_window", sa.Integer(), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("role"),
    )
    op.create_index("ix_agent_model_profiles_runtime_id", "agent_model_profiles", ["runtime_id"])
    op.create_index("ix_agent_model_profiles_provider_type", "agent_model_profiles", ["provider_type"])


def downgrade() -> None:
    op.drop_index("ix_agent_model_profiles_provider_type", table_name="agent_model_profiles")
    op.drop_index("ix_agent_model_profiles_runtime_id", table_name="agent_model_profiles")
    op.drop_table("agent_model_profiles")
