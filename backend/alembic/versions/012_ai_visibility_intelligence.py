"""AI Visibility Intelligence tables

Revision ID: 012
Revises: 011
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB, ARRAY

revision = "012"
down_revision = "011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ai_workspace_keywords
    op.create_table(
        "ai_workspace_keywords",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("workspace_id", UUID(as_uuid=True), sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("keyword", sa.String(255), nullable=False),
        sa.Column("source", sa.String(50), nullable=False, server_default="user"),
        sa.Column("is_approved", sa.Boolean, server_default=sa.text("false")),
        sa.Column("extracted_from", sa.String(100), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("workspace_id", "keyword", name="uq_ai_ws_keyword"),
    )

    # ai_prompt_sources
    op.create_table(
        "ai_prompt_sources",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("workspace_id", UUID(as_uuid=True), sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("prompt_text", sa.Text, nullable=False),
        sa.Column("source_type", sa.String(50), nullable=False),
        sa.Column("source_detail", JSONB, nullable=True),
        sa.Column("status", sa.String(50), server_default="suggested", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("workspace_id", "prompt_text", name="uq_ai_prompt_source_ws_text"),
    )

    # ai_prompt_clusters (for AI visibility, separate from old prompt_clusters)
    op.create_table(
        "ai_prompt_clusters",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("workspace_id", UUID(as_uuid=True), sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("cluster_topic", sa.String(255), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # ai_tracked_prompts
    op.create_table(
        "ai_tracked_prompts",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("workspace_id", UUID(as_uuid=True), sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("prompt_text", sa.Text, nullable=False),
        sa.Column("normalized_text", sa.String(512), nullable=False),
        sa.Column("source_type", sa.String(50), nullable=False),
        sa.Column("cluster_id", UUID(as_uuid=True), sa.ForeignKey("ai_prompt_clusters.id", ondelete="SET NULL"), nullable=True),
        sa.Column("is_active", sa.Boolean, server_default=sa.text("true")),
        sa.Column("last_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("workspace_id", "prompt_text", name="uq_ai_tracked_prompt_ws_text"),
    )

    # ai_prompt_runs (GLOBAL, no workspace_id)
    op.create_table(
        "ai_prompt_runs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("prompt_text", sa.Text, nullable=False),
        sa.Column("normalized_text", sa.String(512), nullable=False),
        sa.Column("run_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(50), server_default="pending", nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("normalized_text", "run_date", name="uq_ai_prompt_run_text_date"),
    )

    # ai_engine_results
    op.create_table(
        "ai_engine_results",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("prompt_run_id", UUID(as_uuid=True), sa.ForeignKey("ai_prompt_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("engine", sa.String(50), nullable=False),
        sa.Column("raw_response", sa.Text, nullable=True),
        sa.Column("mentioned_brands", ARRAY(sa.String), server_default="{}"),
        sa.Column("ranking_data", JSONB, nullable=True),
        sa.Column("citations", ARRAY(sa.Text), server_default="{}"),
        sa.Column("status", sa.String(50), server_default="pending", nullable=False),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column("executed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("prompt_run_id", "engine", name="uq_ai_engine_result_run_engine"),
    )

    # ai_visibility_events
    op.create_table(
        "ai_visibility_events",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("workspace_id", UUID(as_uuid=True), sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("competitor_id", UUID(as_uuid=True), sa.ForeignKey("competitors.id", ondelete="CASCADE"), nullable=False),
        sa.Column("tracked_prompt_id", UUID(as_uuid=True), sa.ForeignKey("ai_tracked_prompts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("engine_result_id", UUID(as_uuid=True), sa.ForeignKey("ai_engine_results.id", ondelete="CASCADE"), nullable=False),
        sa.Column("engine", sa.String(50), nullable=False),
        sa.Column("mentioned", sa.Boolean, server_default=sa.text("false")),
        sa.Column("rank_position", sa.Integer, nullable=True),
        sa.Column("citation_url", sa.Text, nullable=True),
        sa.Column("event_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # ai_impact_insights
    op.create_table(
        "ai_impact_insights",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("workspace_id", UUID(as_uuid=True), sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("competitor_id", UUID(as_uuid=True), sa.ForeignKey("competitors.id", ondelete="CASCADE"), nullable=False),
        sa.Column("signal_event_id", sa.String(100), nullable=True),
        sa.Column("signal_type", sa.String(50), nullable=True),
        sa.Column("signal_title", sa.Text, nullable=True),
        sa.Column("prompt_text", sa.Text, nullable=True),
        sa.Column("tracked_prompt_id", UUID(as_uuid=True), sa.ForeignKey("ai_tracked_prompts.id", ondelete="SET NULL"), nullable=True),
        sa.Column("visibility_before", sa.Integer, server_default="0"),
        sa.Column("visibility_after", sa.Integer, server_default="0"),
        sa.Column("engines_affected", ARRAY(sa.String), server_default="{}"),
        sa.Column("citations", ARRAY(sa.Text), server_default="{}"),
        sa.Column("impact_score", sa.Float, nullable=True),
        sa.Column("priority_level", sa.String(10), server_default="P2"),
        sa.Column("explanation", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # Indexes for performance
    op.create_index("ix_ai_tracked_prompts_ws", "ai_tracked_prompts", ["workspace_id"])
    op.create_index("ix_ai_prompt_runs_date", "ai_prompt_runs", ["run_date"])
    op.create_index("ix_ai_prompt_runs_normalized", "ai_prompt_runs", ["normalized_text"])
    op.create_index("ix_ai_visibility_events_ws", "ai_visibility_events", ["workspace_id"])
    op.create_index("ix_ai_visibility_events_date", "ai_visibility_events", ["event_date"])
    op.create_index("ix_ai_impact_insights_ws", "ai_impact_insights", ["workspace_id"])


def downgrade() -> None:
    op.drop_index("ix_ai_impact_insights_ws")
    op.drop_index("ix_ai_visibility_events_date")
    op.drop_index("ix_ai_visibility_events_ws")
    op.drop_index("ix_ai_prompt_runs_normalized")
    op.drop_index("ix_ai_prompt_runs_date")
    op.drop_index("ix_ai_tracked_prompts_ws")
    op.drop_table("ai_impact_insights")
    op.drop_table("ai_visibility_events")
    op.drop_table("ai_engine_results")
    op.drop_table("ai_prompt_runs")
    op.drop_table("ai_tracked_prompts")
    op.drop_table("ai_prompt_clusters")
    op.drop_table("ai_prompt_sources")
    op.drop_table("ai_workspace_keywords")
