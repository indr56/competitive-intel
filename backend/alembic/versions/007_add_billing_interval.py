"""Add billing_interval column to workspace_billing

Revision ID: 007
Revises: 006
Create Date: 2026-03-05
"""

from alembic import op
import sqlalchemy as sa

revision = "007"
down_revision = "006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "workspace_billing",
        sa.Column("billing_interval", sa.String(10), nullable=False, server_default="month"),
    )


def downgrade() -> None:
    op.drop_column("workspace_billing", "billing_interval")
