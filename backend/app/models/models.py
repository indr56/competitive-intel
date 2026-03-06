import uuid

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import relationship

from app.core.database import Base

import enum


class PlanType(str, enum.Enum):
    STARTER = "starter"
    PRO = "pro"
    AGENCY = "agency"


class SubscriptionStatus(str, enum.Enum):
    TRIALING = "trialing"
    ACTIVE = "active"
    PAST_DUE = "past_due"
    CANCELED = "canceled"
    INCOMPLETE = "incomplete"


class PageType(str, enum.Enum):
    PRICING = "pricing"
    HOME_HERO = "home_hero"
    LANDING = "landing"
    FEATURES_DOCS = "features_docs"
    INTEGRATIONS = "integrations"
    ALTERNATIVES = "alternatives"


class ChangeCategory(str, enum.Enum):
    PRICING_CHANGE = "pricing_change"
    PLAN_RESTRUCTURE = "plan_restructure"
    POSITIONING_HERO = "positioning_hero"
    CTA_CHANGE = "cta_change"
    FEATURE_CLAIM = "feature_claim"
    NEW_ALTERNATIVES_CONTENT = "new_alternatives_content"
    OTHER = "other"


class Severity(str, enum.Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class SignalType(str, enum.Enum):
    WEBSITE_CHANGE = "website_change"
    PRICING_CHANGE = "pricing_change"
    PRODUCT_CHANGE = "product_change"
    BLOG_POST = "blog_post"
    HIRING = "hiring"
    FUNDING = "funding"
    REVIEW = "review"
    MARKETING = "marketing"


class SourceKind(str, enum.Enum):
    MANUAL = "manual"
    AUTO_DISCOVERED = "auto_discovered"


# ── Multi-tenant core ──


class Account(Base):
    __tablename__ = "accounts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False)
    slug = Column(String(255), unique=True, nullable=False)
    plan = Column(String(50), default="free")
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    users = relationship("User", back_populates="account", cascade="all, delete-orphan")
    workspaces = relationship("Workspace", back_populates="account", cascade="all, delete-orphan")


class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    account_id = Column(UUID(as_uuid=True), ForeignKey("accounts.id"), nullable=False)
    email = Column(String(320), unique=True, nullable=False)
    role = Column(String(50), default="member")  # admin | member | viewer
    digest_unsubscribed = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    account = relationship("Account", back_populates="users")


class Workspace(Base):
    __tablename__ = "workspaces"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    account_id = Column(UUID(as_uuid=True), ForeignKey("accounts.id"), nullable=False)
    name = Column(String(255), nullable=False)
    slug = Column(String(255), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    account = relationship("Account", back_populates="workspaces")
    competitors = relationship("Competitor", back_populates="workspace", cascade="all, delete-orphan")
    change_events = relationship("ChangeEvent", back_populates="workspace", cascade="all, delete-orphan")
    competitor_events = relationship("CompetitorEvent", back_populates="workspace", cascade="all, delete-orphan")
    signal_sources = relationship("SignalSource", back_populates="workspace", cascade="all, delete-orphan")
    digests = relationship("Digest", back_populates="workspace", cascade="all, delete-orphan")
    white_label_config = relationship("WhiteLabelConfig", back_populates="workspace", uselist=False, cascade="all, delete-orphan")
    billing = relationship("WorkspaceBilling", back_populates="workspace", uselist=False, cascade="all, delete-orphan")


# ── Competitive intel ──


class Competitor(Base):
    __tablename__ = "competitors"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id = Column(UUID(as_uuid=True), ForeignKey("workspaces.id"), nullable=False)
    name = Column(String(255), nullable=False)
    domain = Column(String(512), nullable=False)
    logo_url = Column(Text, nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    workspace = relationship("Workspace", back_populates="competitors")
    tracked_pages = relationship("TrackedPage", back_populates="competitor", cascade="all, delete-orphan")
    change_events = relationship("ChangeEvent", back_populates="competitor", cascade="all, delete-orphan")
    competitor_events = relationship("CompetitorEvent", back_populates="competitor", cascade="all, delete-orphan")
    signal_sources = relationship("SignalSource", back_populates="competitor", cascade="all, delete-orphan")


class TrackedPage(Base):
    __tablename__ = "tracked_pages"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    competitor_id = Column(UUID(as_uuid=True), ForeignKey("competitors.id", ondelete="CASCADE"), nullable=False)
    url = Column(Text, nullable=False)
    page_type = Column(Enum(PageType, name="page_type_enum", create_constraint=True, values_callable=lambda x: [e.value for e in x]), nullable=False)
    check_interval_hours = Column(Integer, default=24)
    is_active = Column(Boolean, default=True)
    last_checked_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    competitor = relationship("Competitor", back_populates="tracked_pages")
    snapshots = relationship("Snapshot", back_populates="tracked_page", cascade="all, delete-orphan")
    diffs = relationship("Diff", back_populates="tracked_page", cascade="all, delete-orphan")


class Snapshot(Base):
    __tablename__ = "snapshots"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tracked_page_id = Column(UUID(as_uuid=True), ForeignKey("tracked_pages.id", ondelete="CASCADE"), nullable=False)
    screenshot_url = Column(Text, nullable=True)
    html_archive_url = Column(Text, nullable=True)
    extracted_text = Column(Text, nullable=False)
    text_hash = Column(String(64), nullable=False)  # SHA-256
    metadata_ = Column("metadata", JSONB, default={})
    captured_at = Column(DateTime(timezone=True), server_default=func.now())

    tracked_page = relationship("TrackedPage", back_populates="snapshots")


class Diff(Base):
    __tablename__ = "diffs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tracked_page_id = Column(UUID(as_uuid=True), ForeignKey("tracked_pages.id"), nullable=False)
    snapshot_before_id = Column(UUID(as_uuid=True), ForeignKey("snapshots.id"), nullable=False)
    snapshot_after_id = Column(UUID(as_uuid=True), ForeignKey("snapshots.id"), nullable=False)
    raw_diff = Column(JSONB, nullable=False)
    is_meaningful = Column(Boolean, nullable=True)
    noise_filtered = Column(JSONB, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    tracked_page = relationship("TrackedPage", back_populates="diffs")
    snapshot_before = relationship("Snapshot", foreign_keys=[snapshot_before_id])
    snapshot_after = relationship("Snapshot", foreign_keys=[snapshot_after_id])
    change_event = relationship("ChangeEvent", back_populates="diff", uselist=False, cascade="all, delete-orphan")


class ChangeEvent(Base):
    __tablename__ = "change_events"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    diff_id = Column(UUID(as_uuid=True), ForeignKey("diffs.id"), nullable=False)
    workspace_id = Column(UUID(as_uuid=True), ForeignKey("workspaces.id"), nullable=False)
    competitor_id = Column(UUID(as_uuid=True), ForeignKey("competitors.id"), nullable=False)
    categories = Column(ARRAY(String), nullable=False)
    severity = Column(Enum(Severity, name="severity_enum", create_constraint=True, values_callable=lambda x: [e.value for e in x]), nullable=True)
    ai_summary = Column(Text, nullable=True)
    ai_why_it_matters = Column(Text, nullable=True)
    ai_next_moves = Column(Text, nullable=True)
    ai_battlecard_block = Column(Text, nullable=True)
    ai_sales_talk_track = Column(Text, nullable=True)
    raw_llm_response = Column(JSONB, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    diff = relationship("Diff", back_populates="change_event")
    workspace = relationship("Workspace", back_populates="change_events")
    competitor = relationship("Competitor", back_populates="change_events")
    insights = relationship("Insight", back_populates="change_event", cascade="all, delete-orphan")


class Digest(Base):
    __tablename__ = "digests"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id = Column(UUID(as_uuid=True), ForeignKey("workspaces.id"), nullable=False)
    period_start = Column(DateTime(timezone=True), nullable=False)
    period_end = Column(DateTime(timezone=True), nullable=False)
    change_event_ids = Column(ARRAY(UUID(as_uuid=True)), nullable=False, default=[])
    ranking_data = Column(JSONB, nullable=True)
    html_body = Column(Text, nullable=True)
    markdown_body = Column(Text, nullable=True)
    email_sent_at = Column(DateTime(timezone=True), nullable=True)
    web_view_token = Column(String(128), unique=True, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    workspace = relationship("Workspace", back_populates="digests")


# ── White-Label Config ──


class WhiteLabelConfig(Base):
    __tablename__ = "white_label_configs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id = Column(
        UUID(as_uuid=True), ForeignKey("workspaces.id"), nullable=False, unique=True,
    )
    logo_url = Column(Text, nullable=True)
    brand_color = Column(String(7), default="#111827")
    sender_name = Column(String(255), nullable=True)
    sender_email = Column(String(320), nullable=True)
    company_name = Column(String(255), nullable=True)
    footer_text = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    workspace = relationship("Workspace", back_populates="white_label_config")


# ── AI Insights ──


class InsightType(str, enum.Enum):
    CHANGE_ANALYSIS = "change_analysis"
    BATTLECARD = "battlecard"
    EXECUTIVE_BRIEF = "executive_brief"
    SALES_ENABLEMENT = "sales_enablement"


class Insight(Base):
    __tablename__ = "insights"
    __table_args__ = (
        UniqueConstraint(
            "change_event_id", "insight_type", "version",
            name="uq_insight_event_type_version",
        ),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    change_event_id = Column(
        UUID(as_uuid=True), ForeignKey("change_events.id"), nullable=False,
    )
    insight_type = Column(String(50), nullable=False)
    version = Column(Integer, default=1, nullable=False)
    prompt_template_id = Column(String(100), nullable=False)

    # Structured content
    content = Column(JSONB, nullable=False)
    evidence_refs = Column(JSONB, nullable=True)
    is_grounded = Column(Boolean, default=True)
    validation_errors = Column(JSONB, nullable=True)

    # LLM metadata
    model_used = Column(String(100), nullable=True)
    provider = Column(String(50), nullable=True)
    token_count_input = Column(Integer, nullable=True)
    token_count_output = Column(Integer, nullable=True)
    cost_usd = Column(Float, nullable=True)
    latency_ms = Column(Integer, nullable=True)

    # Regeneration
    regeneration_reason = Column(String(100), nullable=True)
    regenerated_from_id = Column(
        UUID(as_uuid=True), ForeignKey("insights.id"), nullable=True,
    )
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    change_event = relationship("ChangeEvent", back_populates="insights")
    regenerated_from = relationship("Insight", remote_side="Insight.id")


# ── Competitor Events (Multi-Signal) ──


class CompetitorEvent(Base):
    __tablename__ = "competitor_events"
    __table_args__ = (
        UniqueConstraint("competitor_id", "signal_type", "source_url", "title",
                         name="uq_competitor_event_dedup"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id = Column(UUID(as_uuid=True), ForeignKey("workspaces.id"), nullable=False)
    competitor_id = Column(UUID(as_uuid=True), ForeignKey("competitors.id", ondelete="CASCADE"), nullable=False)
    signal_type = Column(
        String(50), nullable=False,
    )
    title = Column(String(512), nullable=False)
    description = Column(Text, nullable=True)
    source_url = Column(Text, nullable=True)
    event_time = Column(DateTime(timezone=True), server_default=func.now())
    metadata_json = Column(JSONB, default={})
    ai_summary = Column(Text, nullable=True)
    ai_implications = Column(Text, nullable=True)
    severity = Column(String(20), default="medium")
    is_processed = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    workspace = relationship("Workspace", back_populates="competitor_events")
    competitor = relationship("Competitor", back_populates="competitor_events")


# ── Signal Sources ──


class SignalSource(Base):
    __tablename__ = "signal_sources"
    __table_args__ = (
        UniqueConstraint("competitor_id", "signal_type", "source_url",
                         name="uq_signal_source_comp_type_url"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id = Column(UUID(as_uuid=True), ForeignKey("workspaces.id"), nullable=False)
    competitor_id = Column(UUID(as_uuid=True), ForeignKey("competitors.id", ondelete="CASCADE"), nullable=False)
    signal_type = Column(String(50), nullable=False)
    source_url = Column(Text, nullable=False)
    source_label = Column(String(255), nullable=True)
    is_active = Column(Boolean, default=True)
    poll_interval_hours = Column(Integer, default=12)
    last_checked_at = Column(DateTime(timezone=True), nullable=True)
    last_success_at = Column(DateTime(timezone=True), nullable=True)
    last_error = Column(Text, nullable=True)
    source_kind = Column(String(50), default=SourceKind.MANUAL.value)
    metadata_json = Column(JSONB, default={})
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    workspace = relationship("Workspace", back_populates="signal_sources")
    competitor = relationship("Competitor", back_populates="signal_sources")


# ── Billing ──


class WorkspaceBilling(Base):
    __tablename__ = "workspace_billing"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id = Column(
        UUID(as_uuid=True), ForeignKey("workspaces.id"), nullable=False, unique=True,
    )
    plan_type = Column(String(50), default=PlanType.STARTER.value, nullable=False)
    subscription_status = Column(
        String(50), default=SubscriptionStatus.TRIALING.value, nullable=False,
    )
    currency = Column(String(10), default="USD", nullable=False, server_default="USD")
    billing_interval = Column(String(10), default="month", nullable=False, server_default="month")
    plan_price = Column(Integer, nullable=True)
    razorpay_customer_id = Column(String(255), nullable=True, unique=True)
    razorpay_subscription_id = Column(String(255), nullable=True, unique=True)
    trial_ends_at = Column(DateTime(timezone=True), nullable=True)
    current_period_end = Column(DateTime(timezone=True), nullable=True)
    cancel_at_period_end = Column(Boolean, default=False)
    grace_period_ends_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    workspace = relationship("Workspace", back_populates="billing")


class WebhookEvent(Base):
    __tablename__ = "webhook_events"
    __table_args__ = (
        UniqueConstraint("razorpay_event_id", name="uq_razorpay_event_id"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    razorpay_event_id = Column(String(255), nullable=False)
    event_type = Column(String(100), nullable=False)
    payload = Column(JSONB, nullable=False)
    processed = Column(Boolean, default=False)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
