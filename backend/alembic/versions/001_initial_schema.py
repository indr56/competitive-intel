"""Initial schema

Revision ID: 001
Revises:
Create Date: 2026-02-15

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Enums
    page_type_enum = postgresql.ENUM(
        "pricing", "home_hero", "landing", "features_docs", "integrations", "alternatives",
        name="page_type_enum", create_type=False,
    )
    severity_enum = postgresql.ENUM(
        "low", "medium", "high", "critical",
        name="severity_enum", create_type=False,
    )
    page_type_enum.create(op.get_bind(), checkfirst=True)
    severity_enum.create(op.get_bind(), checkfirst=True)

    # accounts
    op.create_table(
        "accounts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("slug", sa.String(255), unique=True, nullable=False),
        sa.Column("plan", sa.String(50), server_default="free"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # users
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("account_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("accounts.id"), nullable=False),
        sa.Column("email", sa.String(320), unique=True, nullable=False),
        sa.Column("role", sa.String(50), server_default="member"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # workspaces
    op.create_table(
        "workspaces",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("account_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("accounts.id"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("slug", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # competitors
    op.create_table(
        "competitors",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("workspaces.id"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("domain", sa.String(512), nullable=False),
        sa.Column("logo_url", sa.Text, nullable=True),
        sa.Column("is_active", sa.Boolean, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # tracked_pages
    op.create_table(
        "tracked_pages",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("competitor_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("competitors.id", ondelete="CASCADE"), nullable=False),
        sa.Column("url", sa.Text, nullable=False),
        sa.Column("page_type", page_type_enum, nullable=False),
        sa.Column("check_interval_hours", sa.Integer, server_default="24"),
        sa.Column("is_active", sa.Boolean, server_default=sa.text("true")),
        sa.Column("last_checked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # snapshots
    op.create_table(
        "snapshots",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("tracked_page_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tracked_pages.id", ondelete="CASCADE"), nullable=False),
        sa.Column("screenshot_url", sa.Text, nullable=True),
        sa.Column("html_archive_url", sa.Text, nullable=True),
        sa.Column("extracted_text", sa.Text, nullable=False),
        sa.Column("text_hash", sa.String(64), nullable=False),
        sa.Column("metadata", postgresql.JSONB, server_default="{}"),
        sa.Column("captured_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("idx_snapshots_page_time", "snapshots", ["tracked_page_id", sa.text("captured_at DESC")])

    # diffs
    op.create_table(
        "diffs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("tracked_page_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tracked_pages.id"), nullable=False),
        sa.Column("snapshot_before_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("snapshots.id"), nullable=False),
        sa.Column("snapshot_after_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("snapshots.id"), nullable=False),
        sa.Column("raw_diff", postgresql.JSONB, nullable=False),
        sa.Column("is_meaningful", sa.Boolean, nullable=True),
        sa.Column("noise_filtered", postgresql.JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # change_events
    op.create_table(
        "change_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("diff_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("diffs.id"), nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("workspaces.id"), nullable=False),
        sa.Column("competitor_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("competitors.id"), nullable=False),
        sa.Column("categories", postgresql.ARRAY(sa.String), nullable=False),
        sa.Column("severity", severity_enum, nullable=True),
        sa.Column("ai_summary", sa.Text, nullable=True),
        sa.Column("ai_why_it_matters", sa.Text, nullable=True),
        sa.Column("ai_next_moves", sa.Text, nullable=True),
        sa.Column("ai_battlecard_block", sa.Text, nullable=True),
        sa.Column("ai_sales_talk_track", sa.Text, nullable=True),
        sa.Column("raw_llm_response", postgresql.JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("idx_change_events_org", "change_events", ["workspace_id", sa.text("created_at DESC")])

    # digests
    op.create_table(
        "digests",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("workspaces.id"), nullable=False),
        sa.Column("period_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("period_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("change_event_ids", postgresql.ARRAY(postgresql.UUID(as_uuid=True)), nullable=False, server_default="{}"),
        sa.Column("email_sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("web_view_token", sa.String(128), unique=True, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("digests")
    op.drop_index("idx_change_events_org", table_name="change_events")
    op.drop_table("change_events")
    op.drop_table("diffs")
    op.drop_index("idx_snapshots_page_time", table_name="snapshots")
    op.drop_table("snapshots")
    op.drop_table("tracked_pages")
    op.drop_table("competitors")
    op.drop_table("workspaces")
    op.drop_table("users")
    op.drop_table("accounts")
    op.execute("DROP TYPE IF EXISTS page_type_enum")
    op.execute("DROP TYPE IF EXISTS severity_enum")
