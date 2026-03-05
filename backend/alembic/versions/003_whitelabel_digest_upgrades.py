"""Add white_label_configs table, digest body columns, user unsubscribe flag

Revision ID: 003
Revises: 002
Create Date: 2026-03-04
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision = "003"
down_revision = "002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # White-label config table
    op.create_table(
        "white_label_configs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("workspace_id", UUID(as_uuid=True), sa.ForeignKey("workspaces.id"), nullable=False, unique=True),
        sa.Column("logo_url", sa.Text(), nullable=True),
        sa.Column("brand_color", sa.String(7), server_default="#111827"),
        sa.Column("sender_name", sa.String(255), nullable=True),
        sa.Column("sender_email", sa.String(320), nullable=True),
        sa.Column("company_name", sa.String(255), nullable=True),
        sa.Column("footer_text", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # Digest table upgrades
    op.add_column("digests", sa.Column("ranking_data", JSONB, nullable=True))
    op.add_column("digests", sa.Column("html_body", sa.Text(), nullable=True))
    op.add_column("digests", sa.Column("markdown_body", sa.Text(), nullable=True))

    # User unsubscribe flag
    op.add_column("users", sa.Column("digest_unsubscribed", sa.Boolean(), server_default="false"))


def downgrade() -> None:
    op.drop_column("users", "digest_unsubscribed")
    op.drop_column("digests", "markdown_body")
    op.drop_column("digests", "html_body")
    op.drop_column("digests", "ranking_data")
    op.drop_table("white_label_configs")
