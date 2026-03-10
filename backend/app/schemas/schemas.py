from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.models.models import PageType, Severity, SignalType


# ── Mixins ──


class TimestampMixin(BaseModel):
    created_at: datetime


class ORMBase(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ── Account ──


class AccountCreate(BaseModel):
    name: str
    slug: str
    plan: str = "free"


class AccountRead(ORMBase, TimestampMixin):
    id: uuid.UUID
    name: str
    slug: str
    plan: str


# ── User ──


class UserCreate(BaseModel):
    email: str
    role: str = "member"


class UserRead(ORMBase, TimestampMixin):
    id: uuid.UUID
    account_id: uuid.UUID
    email: str
    role: str


# ── Workspace ──


class WorkspaceCreate(BaseModel):
    name: str
    slug: str


class WorkspaceRead(ORMBase, TimestampMixin):
    id: uuid.UUID
    account_id: uuid.UUID
    name: str
    slug: str


# ── Competitor ──


class CompetitorCreate(BaseModel):
    name: str
    domain: str
    logo_url: str | None = None


class CompetitorUpdate(BaseModel):
    name: str | None = None
    domain: str | None = None
    logo_url: str | None = None
    is_active: bool | None = None


class CompetitorRead(ORMBase, TimestampMixin):
    id: uuid.UUID
    workspace_id: uuid.UUID
    name: str
    domain: str
    logo_url: str | None
    is_active: bool


# ── Tracked Page ──


class TrackedPageCreate(BaseModel):
    url: str
    page_type: PageType
    check_interval_hours: int = 24


class TrackedPageUpdate(BaseModel):
    url: str | None = None
    page_type: PageType | None = None
    check_interval_hours: int | None = None
    is_active: bool | None = None


class TrackedPageRead(ORMBase, TimestampMixin):
    id: uuid.UUID
    competitor_id: uuid.UUID
    url: str
    page_type: PageType
    check_interval_hours: int
    is_active: bool
    last_checked_at: datetime | None


# ── Snapshot ──


class SnapshotRead(ORMBase):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: uuid.UUID
    tracked_page_id: uuid.UUID
    screenshot_url: str | None
    html_archive_url: str | None
    extracted_text: str
    text_hash: str
    metadata_: dict[str, Any] | None = Field(default=None, alias="metadata_")
    captured_at: datetime


# ── Diff ──


class DiffRead(ORMBase):
    id: uuid.UUID
    tracked_page_id: uuid.UUID
    snapshot_before_id: uuid.UUID
    snapshot_after_id: uuid.UUID
    raw_diff: dict[str, Any]
    is_meaningful: bool | None
    noise_filtered: dict[str, Any] | None
    created_at: datetime


# ── Change Event ──


class ChangeEventRead(ORMBase):
    id: uuid.UUID
    diff_id: uuid.UUID
    workspace_id: uuid.UUID
    competitor_id: uuid.UUID
    categories: list[str]
    severity: Severity | None
    signal_type: str | None = None
    ai_summary: str | None
    ai_why_it_matters: str | None
    ai_next_moves: str | None
    ai_battlecard_block: str | None
    ai_sales_talk_track: str | None
    created_at: datetime


# ── Digest ──


class DigestRead(ORMBase):
    id: uuid.UUID
    workspace_id: uuid.UUID
    period_start: datetime
    period_end: datetime
    change_event_ids: list[uuid.UUID]
    ranking_data: list[dict[str, Any]] | None = None
    html_body: str | None = None
    markdown_body: str | None = None
    email_sent_at: datetime | None
    web_view_token: str | None
    created_at: datetime


# ── White-Label Config ──


class WhiteLabelConfigRead(ORMBase):
    id: uuid.UUID
    workspace_id: uuid.UUID
    logo_url: str | None
    brand_color: str
    sender_name: str | None
    sender_email: str | None
    company_name: str | None
    footer_text: str | None
    created_at: datetime


class WhiteLabelConfigUpsert(BaseModel):
    logo_url: str | None = None
    brand_color: str = "#111827"
    sender_name: str | None = None
    sender_email: str | None = None
    company_name: str | None = None
    footer_text: str | None = None


# ── Misc ──


class CaptureNowRequest(BaseModel):
    pass


# ── Insight ──


class InsightRead(ORMBase):
    id: uuid.UUID
    change_event_id: uuid.UUID
    insight_type: str
    version: int
    prompt_template_id: str
    content: dict[str, Any]
    evidence_refs: list[str] | None
    is_grounded: bool
    validation_errors: list[str] | None
    model_used: str | None
    provider: str | None
    token_count_input: int | None
    token_count_output: int | None
    cost_usd: float | None
    latency_ms: int | None
    regeneration_reason: str | None
    regenerated_from_id: uuid.UUID | None
    created_at: datetime


class InsightRegenerateRequest(BaseModel):
    reason: str = "manual"
    custom_instructions: str | None = None


class InsightGenerateRequest(BaseModel):
    insight_types: list[str] | None = None


class PaginatedResponse(BaseModel):
    items: list[Any]
    total: int
    page: int
    page_size: int


# ── Competitor Events (Multi-Signal) ──


class CompetitorEventCreate(BaseModel):
    signal_type: str
    title: str
    description: str | None = None
    source_url: str | None = None
    event_time: datetime | None = None
    metadata_json: dict[str, Any] | None = None
    severity: str = "medium"


class CompetitorEventRead(ORMBase):
    id: uuid.UUID
    workspace_id: uuid.UUID
    competitor_id: uuid.UUID
    signal_type: str
    title: str
    description: str | None
    source_url: str | None
    event_time: datetime
    metadata_json: dict[str, Any] | None
    ai_summary: str | None
    ai_implications: str | None
    severity: str
    is_processed: bool
    created_at: datetime


class ActivityFeedItem(BaseModel):
    """Unified feed item that can represent either a ChangeEvent or CompetitorEvent."""
    id: str
    source: str  # "change_event" or "competitor_event"
    workspace_id: str
    competitor_id: str
    competitor_name: str | None = None
    signal_type: str
    title: str
    description: str | None = None
    severity: str | None = None
    source_url: str | None = None
    event_time: datetime
    created_at: datetime


# ── Signal Sources ──


class SignalSourceCreate(BaseModel):
    signal_type: str
    source_url: str
    source_label: str | None = None
    is_active: bool = True
    poll_interval_hours: int = 12
    source_kind: str = "manual"
    metadata_json: dict[str, Any] | None = None


class SignalSourceUpdate(BaseModel):
    source_url: str | None = None
    source_label: str | None = None
    is_active: bool | None = None
    poll_interval_hours: int | None = None
    metadata_json: dict[str, Any] | None = None


class SignalSourceRead(ORMBase):
    id: uuid.UUID
    workspace_id: uuid.UUID
    competitor_id: uuid.UUID
    signal_type: str
    source_url: str
    source_label: str | None
    is_active: bool
    poll_interval_hours: int
    last_checked_at: datetime | None
    last_success_at: datetime | None
    last_error: str | None
    source_kind: str
    metadata_json: dict[str, Any] | None
    created_at: datetime
    updated_at: datetime | None


class TestSourceResult(BaseModel):
    status: str  # "valid", "unreachable", "unexpected_content", "no_items_found"
    message: str
    items_found: int = 0
    details: dict[str, Any] | None = None


class ScanResultItem(BaseModel):
    signal_type: str
    source_url: str | None = None
    events_found: int = 0
    events_created: int = 0
    events_skipped_dedup: int = 0
    error: str | None = None


class ScanResult(BaseModel):
    competitor_id: str
    competitor_name: str
    sources_scanned: int = 0
    total_events_found: int = 0
    total_events_created: int = 0
    results: list[ScanResultItem] = []


# ── Billing ──


class PlanLimits(BaseModel):
    max_competitors: int
    max_tracked_pages: int
    min_check_interval_hours: int
    white_label: bool
    max_workspaces: int
    max_tracked_prompts: int = 10


class IntervalPricing(BaseModel):
    month: int
    year: int


class PlanPricing(BaseModel):
    USD: IntervalPricing
    INR: IntervalPricing


class PlanInfo(BaseModel):
    plan_type: str
    name: str
    price_monthly_cents: int
    pricing: PlanPricing
    annual_discount_pct: float
    limits: PlanLimits


class WorkspaceBillingRead(ORMBase):
    id: uuid.UUID
    workspace_id: uuid.UUID
    plan_type: str
    subscription_status: str
    currency: str
    billing_interval: str
    plan_price: int | None
    razorpay_customer_id: str | None
    razorpay_subscription_id: str | None
    trial_ends_at: datetime | None
    current_period_end: datetime | None
    cancel_at_period_end: bool
    grace_period_ends_at: datetime | None
    created_at: datetime
    updated_at: datetime


class BillingOverview(BaseModel):
    billing: WorkspaceBillingRead | None
    plan: PlanInfo
    usage: dict[str, Any]


class CheckoutSessionRequest(BaseModel):
    plan_type: str
    currency: str = "USD"
    interval: str = "month"
    success_url: str | None = None
    cancel_url: str | None = None


class CheckoutSessionResponse(BaseModel):
    subscription_id: str
    razorpay_key_id: str
    short_url: str | None = None
    workspace_id: str
    plan_type: str
    currency: str
    interval: str
    plan_price: int


class PaymentVerifyRequest(BaseModel):
    razorpay_subscription_id: str
    razorpay_payment_id: str
    razorpay_signature: str


class PaymentVerifyResponse(BaseModel):
    verified: bool
    subscription_status: str


# ── Prompt Clustering ──


class MonitoredPromptCreate(BaseModel):
    raw_text: str


class MonitoredPromptRead(ORMBase):
    id: uuid.UUID
    workspace_id: uuid.UUID
    cluster_id: uuid.UUID | None
    raw_text: str
    normalized_text: str
    is_active: bool
    last_run_at: datetime | None
    created_at: datetime


class PromptClusterRead(ORMBase):
    id: uuid.UUID
    workspace_id: uuid.UUID
    cluster_topic: str
    normalized_topic: str
    description: str | None
    created_at: datetime
    updated_at: datetime | None
    prompts: list[MonitoredPromptRead] = []


class ClusteringResultRead(BaseModel):
    clusters_created: int
    clusters_updated: int
    prompts_clustered: int
    prompts_unclustered: int


# ── AI Visibility Intelligence ──


class AIKeywordCreate(BaseModel):
    keyword: str
    source: str = "user"


class AIKeywordRead(ORMBase):
    id: uuid.UUID
    workspace_id: uuid.UUID
    keyword: str
    source: str
    is_approved: bool
    extracted_from: str | None
    created_at: datetime


class AIPromptSourceCreate(BaseModel):
    prompt_text: str
    source_type: str = "manual"
    source_detail: dict[str, Any] | None = None


class AIPromptSourceRead(ORMBase):
    id: uuid.UUID
    workspace_id: uuid.UUID
    prompt_text: str
    source_type: str
    source_detail: dict[str, Any] | None
    status: str
    created_at: datetime
    updated_at: datetime | None


class AIPromptApproveRequest(BaseModel):
    prompt_source_ids: list[uuid.UUID]


class AIPromptRejectRequest(BaseModel):
    prompt_source_ids: list[uuid.UUID]


class AITrackedPromptRead(ORMBase):
    id: uuid.UUID
    workspace_id: uuid.UUID
    prompt_text: str
    normalized_text: str
    source_type: str
    cluster_id: uuid.UUID | None
    is_active: bool
    last_run_at: datetime | None
    created_at: datetime


class AIPromptClusterRead(ORMBase):
    id: uuid.UUID
    workspace_id: uuid.UUID
    cluster_topic: str
    description: str | None
    created_at: datetime
    tracked_prompts: list[AITrackedPromptRead] = []


class AIPromptRunRead(ORMBase):
    id: uuid.UUID
    prompt_text: str
    normalized_text: str
    run_date: datetime
    status: str
    started_at: datetime | None
    completed_at: datetime | None
    created_at: datetime


class AIEngineResultRead(ORMBase):
    id: uuid.UUID
    prompt_run_id: uuid.UUID
    engine: str
    raw_response: str | None
    mentioned_brands: list[str]
    ranking_data: list[dict[str, Any]] | None
    citations: list[str]
    status: str
    error_message: str | None
    executed_at: datetime | None
    created_at: datetime


class AIVisibilityEventRead(ORMBase):
    id: uuid.UUID
    workspace_id: uuid.UUID
    competitor_id: uuid.UUID
    tracked_prompt_id: uuid.UUID
    engine_result_id: uuid.UUID
    engine: str
    mentioned: bool
    rank_position: int | None
    citation_url: str | None
    event_date: datetime
    created_at: datetime


class AIImpactInsightRead(ORMBase):
    id: uuid.UUID
    workspace_id: uuid.UUID
    competitor_id: uuid.UUID
    signal_event_id: str | None
    signal_type: str | None
    signal_title: str | None
    prompt_text: str | None
    tracked_prompt_id: uuid.UUID | None
    visibility_before: int
    visibility_after: int
    engines_affected: list[str]
    citations: list[str]
    impact_score: float | None
    priority_level: str
    explanation: str | None
    created_at: datetime
    # PROMPT-9 additions
    insight_type: str = "ai_impact"
    short_title: str | None = None
    correlation_confidence: float | None = None
    reasoning: str | None = None
    engine_breakdown: dict[str, Any] | None = None
    previous_mentions: list[str] = []
    current_mentions: list[str] = []
    prompt_cluster_name: str | None = None
    signal_timestamp: datetime | None = None
    visibility_delta: int | None = None


class AIInsightCompactRead(BaseModel):
    """Level 1 — Compact Insight Card for feed/dashboard."""
    insight_id: uuid.UUID
    insight_type: str
    priority: str
    competitor_name: str
    signal_type: str | None
    short_title: str | None
    signal_headline: str | None  # PROMPT-10: concise 1-line signal description
    visibility_before: int
    visibility_after: int
    visibility_delta: int
    engine_summary: str
    impact_score: float | None
    correlation_confidence: float | None
    summary_text: str | None
    timestamp: datetime


class AIInsightDetailRead(BaseModel):
    """Level 2 — Expanded Insight Detail (full intelligence context)."""
    # A. Header
    insight_id: uuid.UUID
    insight_type: str
    competitor_name: str
    competitor_id: uuid.UUID
    priority: str
    impact_score: float | None
    correlation_confidence: float | None
    signal_type: str | None
    timestamp: datetime

    # B. Signal Context
    signal_title: str | None
    signal_timestamp: datetime | None
    signal_event_id: str | None

    # C. Prompt Context
    prompt_text: str | None
    prompt_cluster_name: str | None
    prompt_source: str | None
    prompt_run_timestamp: datetime | None

    # D. Visibility Change
    visibility_before: int
    visibility_after: int
    visibility_delta: int
    engines_detected: list[str]
    engine_breakdown: dict[str, Any] | None

    # E. Citations
    citations: dict[str, list[str]]  # engine_name -> [urls]

    # F. Reasoning
    reasoning: str | None
    explanation: str | None

    # G. Supporting Evidence
    previous_mentions: list[str]
    current_mentions: list[str]

    # H. Actions (links)
    actions: dict[str, str]

    # I. PROMPT-10 additions
    signal_headline: str | None = None          # concise signal one-liner
    confidence_factors: dict[str, Any] | None = None  # explainable breakdown
    prompt_relevance_score: float | None = None  # 0.0-1.0


class VisibilityTrendPoint(BaseModel):
    date: str
    engine: str
    mentions: int
    avg_rank: float | None


class VisibilityTrendsResponse(BaseModel):
    competitor_id: str
    competitor_name: str
    trends: list[VisibilityTrendPoint]
    total_mentions: int
    engines_breakdown: dict[str, int]


class GenerateSuggestionsRequest(BaseModel):
    source_types: list[str] | None = None  # filter which sources to generate from


class GenerateSuggestionsResponse(BaseModel):
    suggestions_created: int
    by_source: dict[str, int]


class RunPromptsRequest(BaseModel):
    prompt_ids: list[uuid.UUID] | None = None  # if None, run all active


class RunPromptsResponse(BaseModel):
    prompts_queued: int
    cached_reused: int
    message: str
