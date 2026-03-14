"""016_p14_intelligence_enhancements

PROMPT-14 additions:
- New InsightType enum values: ai_share_of_voice, ai_narrative, ai_optimization_playbook
- No new tables needed — insights stored in existing ai_impact_insights table
"""

from alembic import op

revision = "016"
down_revision = "015"
branch_labels = None
depends_on = None


def upgrade():
    # The insight_type column is VARCHAR(50), not a Postgres ENUM,
    # so no DDL change is needed — new values are stored directly.
    pass


def downgrade():
    pass
