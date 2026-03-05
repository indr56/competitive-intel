"""Rename stripe columns to razorpay

Revision ID: 005
Revises: 004
Create Date: 2026-03-05
"""

from alembic import op

revision = "005"
down_revision = "004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # workspace_billing: rename stripe_* → razorpay_*
    op.alter_column("workspace_billing", "stripe_customer_id", new_column_name="razorpay_customer_id")
    op.alter_column("workspace_billing", "stripe_subscription_id", new_column_name="razorpay_subscription_id")

    # webhook_events: rename stripe_event_id → razorpay_event_id
    op.drop_constraint("uq_stripe_event_id", "webhook_events", type_="unique")
    op.alter_column("webhook_events", "stripe_event_id", new_column_name="razorpay_event_id")
    op.create_unique_constraint("uq_razorpay_event_id", "webhook_events", ["razorpay_event_id"])


def downgrade() -> None:
    # webhook_events: rename back
    op.drop_constraint("uq_razorpay_event_id", "webhook_events", type_="unique")
    op.alter_column("webhook_events", "razorpay_event_id", new_column_name="stripe_event_id")
    op.create_unique_constraint("uq_stripe_event_id", "webhook_events", ["stripe_event_id"])

    # workspace_billing: rename back
    op.alter_column("workspace_billing", "razorpay_customer_id", new_column_name="stripe_customer_id")
    op.alter_column("workspace_billing", "razorpay_subscription_id", new_column_name="stripe_subscription_id")
