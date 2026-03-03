"""Add insights table

Revision ID: 002
Revises: 001
Create Date: 2026-03-04
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision = "002"
down_revision = "001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "insights",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("change_event_id", UUID(as_uuid=True), sa.ForeignKey("change_events.id"), nullable=False),
        sa.Column("insight_type", sa.String(50), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("prompt_template_id", sa.String(100), nullable=False),
        sa.Column("content", JSONB, nullable=False),
        sa.Column("evidence_refs", JSONB, nullable=True),
        sa.Column("is_grounded", sa.Boolean(), server_default="true"),
        sa.Column("validation_errors", JSONB, nullable=True),
        sa.Column("model_used", sa.String(100), nullable=True),
        sa.Column("provider", sa.String(50), nullable=True),
        sa.Column("token_count_input", sa.Integer(), nullable=True),
        sa.Column("token_count_output", sa.Integer(), nullable=True),
        sa.Column("cost_usd", sa.Float(), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("regeneration_reason", sa.String(100), nullable=True),
        sa.Column("regenerated_from_id", UUID(as_uuid=True), sa.ForeignKey("insights.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("change_event_id", "insight_type", "version", name="uq_insight_event_type_version"),
    )
    op.create_index("ix_insights_change_event_id", "insights", ["change_event_id"])
    op.create_index("ix_insights_type_version", "insights", ["insight_type", "version"])


def downgrade() -> None:
    op.drop_index("ix_insights_type_version")
    op.drop_index("ix_insights_change_event_id")
    op.drop_table("insights")
