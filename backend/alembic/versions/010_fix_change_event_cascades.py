"""Fix cascade deletes on change_events foreign keys.

Add ON DELETE CASCADE to change_events.competitor_id and change_events.diff_id
so that deleting a Competitor or Diff properly cascades to its ChangeEvents
at the database level.
"""

from alembic import op

revision = "010"
down_revision = "009"
branch_labels = None
depends_on = None


def upgrade():
    # Drop existing FK constraints and re-create with ON DELETE CASCADE
    op.drop_constraint("change_events_competitor_id_fkey", "change_events", type_="foreignkey")
    op.create_foreign_key(
        "change_events_competitor_id_fkey",
        "change_events",
        "competitors",
        ["competitor_id"],
        ["id"],
        ondelete="CASCADE",
    )

    op.drop_constraint("change_events_diff_id_fkey", "change_events", type_="foreignkey")
    op.create_foreign_key(
        "change_events_diff_id_fkey",
        "change_events",
        "diffs",
        ["diff_id"],
        ["id"],
        ondelete="CASCADE",
    )


def downgrade():
    op.drop_constraint("change_events_competitor_id_fkey", "change_events", type_="foreignkey")
    op.create_foreign_key(
        "change_events_competitor_id_fkey",
        "change_events",
        "competitors",
        ["competitor_id"],
        ["id"],
    )

    op.drop_constraint("change_events_diff_id_fkey", "change_events", type_="foreignkey")
    op.create_foreign_key(
        "change_events_diff_id_fkey",
        "change_events",
        "diffs",
        ["diff_id"],
        ["id"],
    )
