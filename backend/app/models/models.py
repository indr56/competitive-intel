import uuid

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import relationship

from app.core.database import Base

import enum


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
    change_events = relationship("ChangeEvent", back_populates="workspace")
    digests = relationship("Digest", back_populates="workspace", cascade="all, delete-orphan")


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
    change_events = relationship("ChangeEvent", back_populates="competitor")


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
    change_event = relationship("ChangeEvent", back_populates="diff", uselist=False)


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


class Digest(Base):
    __tablename__ = "digests"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id = Column(UUID(as_uuid=True), ForeignKey("workspaces.id"), nullable=False)
    period_start = Column(DateTime(timezone=True), nullable=False)
    period_end = Column(DateTime(timezone=True), nullable=False)
    change_event_ids = Column(ARRAY(UUID(as_uuid=True)), nullable=False, default=[])
    email_sent_at = Column(DateTime(timezone=True), nullable=True)
    web_view_token = Column(String(128), unique=True, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    workspace = relationship("Workspace", back_populates="digests")
