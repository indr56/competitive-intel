"""Add signal_sources table for configurable signal sources per competitor.

Revision ID: 009
Revises: 008
"""

revision = "009"
down_revision = "008"

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB


def upgrade() -> None:
    op.create_table(
        "signal_sources",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("workspace_id", UUID(as_uuid=True), sa.ForeignKey("workspaces.id"), nullable=False),
        sa.Column("competitor_id", UUID(as_uuid=True), sa.ForeignKey("competitors.id", ondelete="CASCADE"), nullable=False),
        sa.Column("signal_type", sa.String(50), nullable=False),
        sa.Column("source_url", sa.Text, nullable=False),
        sa.Column("source_label", sa.String(255), nullable=True),
        sa.Column("is_active", sa.Boolean, server_default=sa.text("true")),
        sa.Column("poll_interval_hours", sa.Integer, server_default=sa.text("12")),
        sa.Column("last_checked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_success_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text, nullable=True),
        sa.Column("source_kind", sa.String(50), server_default="manual"),
        sa.Column("metadata_json", JSONB, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("competitor_id", "signal_type", "source_url", name="uq_signal_source_comp_type_url"),
    )
    op.create_index("ix_signal_sources_competitor_id", "signal_sources", ["competitor_id"])
    op.create_index("ix_signal_sources_workspace_id", "signal_sources", ["workspace_id"])
    op.create_index("ix_signal_sources_signal_type", "signal_sources", ["signal_type"])


def downgrade() -> None:
    op.drop_index("ix_signal_sources_signal_type")
    op.drop_index("ix_signal_sources_workspace_id")
    op.drop_index("ix_signal_sources_competitor_id")
    op.drop_table("signal_sources")
