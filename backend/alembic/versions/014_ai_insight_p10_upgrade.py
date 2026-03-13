"""014_ai_insight_p10_upgrade

PROMPT-10 additions to ai_impact_insights:
- signal_headline   VARCHAR(200)  — concise one-line signal description for compact card
- confidence_factors JSONB        — explainable breakdown of confidence score
- prompt_relevance_score FLOAT    — semantic relevance between signal and prompt (0-1)
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "014"
down_revision = "013"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "ai_impact_insights",
        sa.Column("signal_headline", sa.String(200), nullable=True),
    )
    op.add_column(
        "ai_impact_insights",
        sa.Column("confidence_factors", postgresql.JSONB(), nullable=True),
    )
    op.add_column(
        "ai_impact_insights",
        sa.Column("prompt_relevance_score", sa.Float(), nullable=True),
    )


def downgrade():
    op.drop_column("ai_impact_insights", "prompt_relevance_score")
    op.drop_column("ai_impact_insights", "confidence_factors")
    op.drop_column("ai_impact_insights", "signal_headline")
