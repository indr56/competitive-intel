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
    POSITIONING_CHANGE = "positioning_change"
    INTEGRATION_ADDED = "integration_added"
    INTEGRATION_REMOVED = "integration_removed"
    LANDING_PAGE_CREATED = "landing_page_created"
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
    POSITIONING_CHANGE = "positioning_change"
    INTEGRATION_ADDED = "integration_added"
    INTEGRATION_REMOVED = "integration_removed"
    LANDING_PAGE_CREATED = "landing_page_created"


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
    signal_type = Column(String(50), nullable=True)
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


# ── Prompt Clustering ──


class PromptCluster(Base):
    __tablename__ = "prompt_clusters"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id = Column(UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False)
    cluster_topic = Column(String(255), nullable=False)
    normalized_topic = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    prompts = relationship("MonitoredPrompt", back_populates="cluster", cascade="all, delete-orphan")


class MonitoredPrompt(Base):
    __tablename__ = "monitored_prompts"
    __table_args__ = (
        UniqueConstraint("workspace_id", "raw_text", name="uq_monitored_prompt_ws_text"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id = Column(UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False)
    cluster_id = Column(UUID(as_uuid=True), ForeignKey("prompt_clusters.id", ondelete="SET NULL"), nullable=True)
    raw_text = Column(Text, nullable=False)
    normalized_text = Column(String(512), nullable=False)
    embedding = Column(JSONB, nullable=True)
    is_active = Column(Boolean, default=True)
    last_run_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    cluster = relationship("PromptCluster", back_populates="prompts")


# ── AI Visibility Intelligence ──


class PromptSourceType(str, enum.Enum):
    MANUAL = "manual"
    COMPETITOR = "competitor"
    KEYWORD = "keyword"
    TEMPLATE = "template"
    CATEGORY = "category"


class PromptStatusEnum(str, enum.Enum):
    SUGGESTED = "suggested"
    APPROVED = "approved"
    REJECTED = "rejected"
    PAUSED = "paused"


class AIEngineEnum(str, enum.Enum):
    CHATGPT = "chatgpt"
    PERPLEXITY = "perplexity"
    CLAUDE = "claude"
    GEMINI = "gemini"


class RunStatusEnum(str, enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class PriorityLevel(str, enum.Enum):
    P0 = "P0"
    P1 = "P1"
    P2 = "P2"
    P3 = "P3"


class InsightType(str, enum.Enum):
    AI_IMPACT = "ai_impact"
    AI_VISIBILITY_HIJACK = "ai_visibility_hijack"
    AI_VISIBILITY_LOSS = "ai_visibility_loss"
    AI_DOMINANCE = "ai_dominance"
    # PROMPT-11 additions
    AI_STRATEGY_ALERT = "ai_strategy_alert"
    AI_CITATION_INFLUENCE = "ai_citation_influence"
    AI_CATEGORY_OWNERSHIP = "ai_category_ownership"
    # PROMPT-14 additions
    AI_SHARE_OF_VOICE = "ai_share_of_voice"
    AI_NARRATIVE = "ai_narrative"
    AI_OPTIMIZATION_PLAYBOOK = "ai_optimization_playbook"


class AIWorkspaceKeyword(Base):
    __tablename__ = "ai_workspace_keywords"
    __table_args__ = (
        UniqueConstraint("workspace_id", "keyword", name="uq_ai_ws_keyword"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id = Column(UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False)
    keyword = Column(String(255), nullable=False)
    source = Column(String(50), nullable=False, default="user")  # "user" or "auto_extracted"
    is_approved = Column(Boolean, default=False)
    extracted_from = Column(String(100), nullable=True)  # e.g. "homepage", "features", "blog_title"
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class AIPromptSource(Base):
    """Suggested prompts before user approval."""
    __tablename__ = "ai_prompt_sources"
    __table_args__ = (
        UniqueConstraint("workspace_id", "prompt_text", name="uq_ai_prompt_source_ws_text"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id = Column(UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False)
    prompt_text = Column(Text, nullable=False)
    source_type = Column(String(50), nullable=False)  # manual/competitor/keyword/template/category
    source_detail = Column(JSONB, nullable=True)  # e.g. {"competitor": "Zapier", "template": "best {kw} tools"}
    status = Column(String(50), default=PromptStatusEnum.SUGGESTED.value, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class AITrackedPrompt(Base):
    """Approved prompts that participate in global execution."""
    __tablename__ = "ai_tracked_prompts"
    __table_args__ = (
        UniqueConstraint("workspace_id", "prompt_text", name="uq_ai_tracked_prompt_ws_text"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id = Column(UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False)
    prompt_text = Column(Text, nullable=False)
    normalized_text = Column(String(512), nullable=False)
    source_type = Column(String(50), nullable=False)
    cluster_id = Column(UUID(as_uuid=True), ForeignKey("ai_prompt_clusters.id", ondelete="SET NULL"), nullable=True)
    category_id = Column(UUID(as_uuid=True), ForeignKey("prompt_categories.id", ondelete="SET NULL"), nullable=True)  # PROMPT-11: optional
    is_active = Column(Boolean, default=True)
    last_run_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    cluster = relationship("AIPromptCluster", back_populates="tracked_prompts")
    category = relationship("PromptCategory", back_populates="tracked_prompts")
    visibility_events = relationship("AIVisibilityEvent", back_populates="tracked_prompt", cascade="all, delete-orphan")


class AIPromptCluster(Base):
    """Semantic clusters of tracked prompts for analytics."""
    __tablename__ = "ai_prompt_clusters"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id = Column(UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False)
    cluster_topic = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    tracked_prompts = relationship("AITrackedPrompt", back_populates="cluster")


class AIPromptRun(Base):
    """Global prompt execution record — NOT workspace-specific."""
    __tablename__ = "ai_prompt_runs"
    __table_args__ = (
        UniqueConstraint("normalized_text", "run_date", name="uq_ai_prompt_run_text_date"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    prompt_text = Column(Text, nullable=False)
    normalized_text = Column(String(512), nullable=False)
    run_date = Column(DateTime(timezone=True), nullable=False)  # date of scheduled run
    status = Column(String(50), default=RunStatusEnum.PENDING.value, nullable=False)
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    engine_results = relationship("AIEngineResult", back_populates="prompt_run", cascade="all, delete-orphan")


class AIEngineResult(Base):
    """Per-engine result for a global prompt run."""
    __tablename__ = "ai_engine_results"
    __table_args__ = (
        UniqueConstraint("prompt_run_id", "engine", name="uq_ai_engine_result_run_engine"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    prompt_run_id = Column(UUID(as_uuid=True), ForeignKey("ai_prompt_runs.id", ondelete="CASCADE"), nullable=False)
    engine = Column(String(50), nullable=False)  # chatgpt/perplexity/claude/gemini
    raw_response = Column(Text, nullable=True)
    mentioned_brands = Column(ARRAY(String), default=[])
    ranking_data = Column(JSONB, nullable=True)  # [{"brand": "X", "position": 1}, ...]
    citations = Column(ARRAY(Text), default=[])
    status = Column(String(50), default=RunStatusEnum.PENDING.value, nullable=False)
    error_message = Column(Text, nullable=True)
    executed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    prompt_run = relationship("AIPromptRun", back_populates="engine_results")
    visibility_events = relationship("AIVisibilityEvent", back_populates="engine_result", cascade="all, delete-orphan")


class AIVisibilityEvent(Base):
    """Workspace-filtered visibility detection from global results."""
    __tablename__ = "ai_visibility_events"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id = Column(UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False)
    competitor_id = Column(UUID(as_uuid=True), ForeignKey("competitors.id", ondelete="CASCADE"), nullable=False)
    tracked_prompt_id = Column(UUID(as_uuid=True), ForeignKey("ai_tracked_prompts.id", ondelete="CASCADE"), nullable=False)
    engine_result_id = Column(UUID(as_uuid=True), ForeignKey("ai_engine_results.id", ondelete="CASCADE"), nullable=False)
    engine = Column(String(50), nullable=False)
    mentioned = Column(Boolean, default=False)
    rank_position = Column(Integer, nullable=True)
    citation_url = Column(Text, nullable=True)
    event_date = Column(DateTime(timezone=True), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    tracked_prompt = relationship("AITrackedPrompt", back_populates="visibility_events")
    engine_result = relationship("AIEngineResult", back_populates="visibility_events")


class AIImpactInsight(Base):
    """Correlation between competitor signals and AI visibility changes."""
    __tablename__ = "ai_impact_insights"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id = Column(UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False)
    competitor_id = Column(UUID(as_uuid=True), ForeignKey("competitors.id", ondelete="CASCADE"), nullable=False)
    signal_event_id = Column(String(100), nullable=True)  # ID of change_event or competitor_event
    signal_type = Column(String(50), nullable=True)
    signal_title = Column(Text, nullable=True)
    prompt_text = Column(Text, nullable=True)
    tracked_prompt_id = Column(UUID(as_uuid=True), ForeignKey("ai_tracked_prompts.id", ondelete="SET NULL"), nullable=True)
    visibility_before = Column(Integer, default=0)
    visibility_after = Column(Integer, default=0)
    engines_affected = Column(ARRAY(String), default=[])
    citations = Column(ARRAY(Text), default=[])
    impact_score = Column(Float, nullable=True)
    priority_level = Column(String(10), default=PriorityLevel.P2.value)  # P0/P1/P2/P3
    explanation = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    # ── PROMPT-9 additions ──
    insight_type = Column(String(50), default=InsightType.AI_IMPACT.value, nullable=False)
    short_title = Column(String(512), nullable=True)
    correlation_confidence = Column(Float, nullable=True)  # 0-100
    reasoning = Column(Text, nullable=True)
    engine_breakdown = Column(JSONB, nullable=True)  # {engine: {rank, mentioned, citation_url}}
    previous_mentions = Column(ARRAY(String), default=[])
    current_mentions = Column(ARRAY(String), default=[])
    prompt_cluster_name = Column(String(255), nullable=True)
    signal_timestamp = Column(DateTime(timezone=True), nullable=True)
    visibility_delta = Column(Integer, nullable=True)
    # ── PROMPT-10 additions ──
    signal_headline = Column(String(200), nullable=True)          # concise 1-line signal for compact card
    confidence_factors = Column(JSONB, nullable=True)             # explainable breakdown: {score, factors_text, ...}
    prompt_relevance_score = Column(Float, nullable=True)         # 0.0-1.0 semantic signal↔prompt fit
    # ── PROMPT-11 additions ──
    strategy_actions = Column(JSONB, nullable=True)               # recommended actions for strategy alerts
    influential_sources = Column(JSONB, nullable=True)            # citation influence sources
    category_data = Column(JSONB, nullable=True)                  # category ownership data


# ── PROMPT-11: Prompt Categories ──


class PromptCategory(Base):
    """Optional grouping for tracked prompts to support category ownership."""
    __tablename__ = "prompt_categories"
    __table_args__ = (
        UniqueConstraint("workspace_id", "category_name", name="uq_prompt_category_ws_name"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id = Column(UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False)
    category_name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    tracked_prompts = relationship("AITrackedPrompt", back_populates="category")


class PromptEngineCitation(Base):
    """Citation URL extracted from an AI engine response."""
    __tablename__ = "prompt_engine_citations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id = Column(UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False)
    prompt_run_id = Column(UUID(as_uuid=True), ForeignKey("ai_prompt_runs.id", ondelete="CASCADE"), nullable=False)
    engine = Column(String(50), nullable=False)
    competitor_id = Column(UUID(as_uuid=True), ForeignKey("competitors.id", ondelete="CASCADE"), nullable=True)
    citation_url = Column(Text, nullable=False)
    citation_domain = Column(String(255), nullable=True)
    citation_context = Column(Text, nullable=True)
    rank = Column(Integer, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class CategoryVisibility(Base):
    """Computed visibility share for a competitor within a prompt category."""
    __tablename__ = "category_visibility"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id = Column(UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False)
    category_id = Column(UUID(as_uuid=True), ForeignKey("prompt_categories.id", ondelete="CASCADE"), nullable=False)
    competitor_id = Column(UUID(as_uuid=True), ForeignKey("competitors.id", ondelete="CASCADE"), nullable=False)
    visibility_share = Column(Float, nullable=False, default=0)
    engine_count = Column(Integer, nullable=False, default=0)
    prompt_count = Column(Integer, nullable=False, default=0)
    total_mentions = Column(Integer, nullable=False, default=0)
    time_window = Column(String(50), nullable=True)
    computed_at = Column(DateTime(timezone=True), server_default=func.now())


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
