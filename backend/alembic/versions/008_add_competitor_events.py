"""Add competitor_events table for multi-signal intelligence.

Revision ID: 008
Revises: 007
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision = "008"
down_revision = "007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "competitor_events",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("workspace_id", UUID(as_uuid=True), sa.ForeignKey("workspaces.id"), nullable=False),
        sa.Column("competitor_id", UUID(as_uuid=True), sa.ForeignKey("competitors.id", ondelete="CASCADE"), nullable=False),
        sa.Column("signal_type", sa.String(50), nullable=False),
        sa.Column("title", sa.String(512), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("source_url", sa.Text, nullable=True),
        sa.Column("event_time", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("metadata_json", JSONB, server_default="{}"),
        sa.Column("ai_summary", sa.Text, nullable=True),
        sa.Column("ai_implications", sa.Text, nullable=True),
        sa.Column("severity", sa.String(20), server_default="medium"),
        sa.Column("is_processed", sa.Boolean, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_competitor_events_workspace_id", "competitor_events", ["workspace_id"])
    op.create_index("ix_competitor_events_competitor_id", "competitor_events", ["competitor_id"])
    op.create_index("ix_competitor_events_signal_type", "competitor_events", ["signal_type"])
    op.create_index("ix_competitor_events_event_time", "competitor_events", ["event_time"])
    op.create_unique_constraint(
        "uq_competitor_event_dedup",
        "competitor_events",
        ["competitor_id", "signal_type", "source_url", "title"],
    )


def downgrade() -> None:
    op.drop_table("competitor_events")
