"""Add signal_type to change_events, prompt_clusters and monitored_prompts tables.

Revision ID: 011
Revises: 010
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision = "011"
down_revision = "010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add signal_type column to change_events
    op.add_column("change_events", sa.Column("signal_type", sa.String(50), nullable=True))

    # Create prompt_clusters table
    op.create_table(
        "prompt_clusters",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("workspace_id", UUID(as_uuid=True), sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("cluster_topic", sa.String(255), nullable=False),
        sa.Column("normalized_topic", sa.String(255), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # Create monitored_prompts table
    op.create_table(
        "monitored_prompts",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("workspace_id", UUID(as_uuid=True), sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("cluster_id", UUID(as_uuid=True), sa.ForeignKey("prompt_clusters.id", ondelete="SET NULL"), nullable=True),
        sa.Column("raw_text", sa.Text, nullable=False),
        sa.Column("normalized_text", sa.String(512), nullable=False),
        sa.Column("embedding", JSONB, nullable=True),
        sa.Column("is_active", sa.Boolean, default=True),
        sa.Column("last_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("workspace_id", "raw_text", name="uq_monitored_prompt_ws_text"),
    )


def downgrade() -> None:
    op.drop_table("monitored_prompts")
    op.drop_table("prompt_clusters")
    op.drop_column("change_events", "signal_type")
