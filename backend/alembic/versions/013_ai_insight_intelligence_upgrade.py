"""AI Impact Insight Intelligence upgrade — new columns for compact/detail views,
insight types, confidence scoring, reasoning, engine breakdown.

Revision ID: 013
Revises: 012
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, ARRAY

revision = "013"
down_revision = "012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add new columns to ai_impact_insights
    op.add_column("ai_impact_insights", sa.Column(
        "insight_type", sa.String(50), server_default="ai_impact", nullable=False,
    ))
    op.add_column("ai_impact_insights", sa.Column(
        "short_title", sa.String(512), nullable=True,
    ))
    op.add_column("ai_impact_insights", sa.Column(
        "correlation_confidence", sa.Float, nullable=True,
    ))
    op.add_column("ai_impact_insights", sa.Column(
        "reasoning", sa.Text, nullable=True,
    ))
    op.add_column("ai_impact_insights", sa.Column(
        "engine_breakdown", JSONB, nullable=True,
    ))
    op.add_column("ai_impact_insights", sa.Column(
        "previous_mentions", ARRAY(sa.String), server_default="{}", nullable=True,
    ))
    op.add_column("ai_impact_insights", sa.Column(
        "current_mentions", ARRAY(sa.String), server_default="{}", nullable=True,
    ))
    op.add_column("ai_impact_insights", sa.Column(
        "prompt_cluster_name", sa.String(255), nullable=True,
    ))
    op.add_column("ai_impact_insights", sa.Column(
        "signal_timestamp", sa.DateTime(timezone=True), nullable=True,
    ))
    op.add_column("ai_impact_insights", sa.Column(
        "visibility_delta", sa.Integer, nullable=True,
    ))


def downgrade() -> None:
    op.drop_column("ai_impact_insights", "visibility_delta")
    op.drop_column("ai_impact_insights", "signal_timestamp")
    op.drop_column("ai_impact_insights", "prompt_cluster_name")
    op.drop_column("ai_impact_insights", "current_mentions")
    op.drop_column("ai_impact_insights", "previous_mentions")
    op.drop_column("ai_impact_insights", "engine_breakdown")
    op.drop_column("ai_impact_insights", "reasoning")
    op.drop_column("ai_impact_insights", "correlation_confidence")
    op.drop_column("ai_impact_insights", "short_title")
    op.drop_column("ai_impact_insights", "insight_type")
