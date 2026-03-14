"""015_p11_intelligence_enhancements

PROMPT-11 additions:
- prompt_categories table (optional grouping for prompts)
- prompt_engine_citations table (extracted citation URLs per engine result)
- category_visibility table (computed ownership shares per category)
- category_id nullable FK on ai_tracked_prompts (backward compatible)
- New InsightType enum values: ai_strategy_alert, ai_citation_influence, ai_category_ownership
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "015"
down_revision = "014"
branch_labels = None
depends_on = None


def upgrade():
    # 1. prompt_categories
    op.create_table(
        "prompt_categories",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("category_name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("workspace_id", "category_name", name="uq_prompt_category_ws_name"),
    )

    # 2. prompt_engine_citations
    op.create_table(
        "prompt_engine_citations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("prompt_run_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("ai_prompt_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("engine", sa.String(50), nullable=False),
        sa.Column("competitor_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("competitors.id", ondelete="CASCADE"), nullable=True),
        sa.Column("citation_url", sa.Text(), nullable=False),
        sa.Column("citation_domain", sa.String(255), nullable=True),
        sa.Column("citation_context", sa.Text(), nullable=True),
        sa.Column("rank", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # 3. category_visibility
    op.create_table(
        "category_visibility",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("category_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("prompt_categories.id", ondelete="CASCADE"), nullable=False),
        sa.Column("competitor_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("competitors.id", ondelete="CASCADE"), nullable=False),
        sa.Column("visibility_share", sa.Float(), nullable=False, server_default="0"),
        sa.Column("engine_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("prompt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_mentions", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("time_window", sa.String(50), nullable=True),
        sa.Column("computed_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # 4. Add nullable category_id to ai_tracked_prompts (backward compatible)
    op.add_column(
        "ai_tracked_prompts",
        sa.Column(
            "category_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("prompt_categories.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )

    # 5. Add strategy_actions JSONB to ai_impact_insights for strategy alerts
    op.add_column(
        "ai_impact_insights",
        sa.Column("strategy_actions", postgresql.JSONB(), nullable=True),
    )
    # 6. Add influential_sources JSONB for citation influence insights
    op.add_column(
        "ai_impact_insights",
        sa.Column("influential_sources", postgresql.JSONB(), nullable=True),
    )
    # 7. Add category_data JSONB for category ownership insights
    op.add_column(
        "ai_impact_insights",
        sa.Column("category_data", postgresql.JSONB(), nullable=True),
    )


def downgrade():
    op.drop_column("ai_impact_insights", "category_data")
    op.drop_column("ai_impact_insights", "influential_sources")
    op.drop_column("ai_impact_insights", "strategy_actions")
    op.drop_column("ai_tracked_prompts", "category_id")
    op.drop_table("category_visibility")
    op.drop_table("prompt_engine_citations")
    op.drop_table("prompt_categories")
