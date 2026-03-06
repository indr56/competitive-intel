// Types derived directly from backend Pydantic schemas

export interface Workspace {
  id: string;
  account_id: string;
  name: string;
  slug: string;
  created_at: string;
}

export interface WorkspaceCreate {
  name: string;
  slug: string;
}

export interface Competitor {
  id: string;
  workspace_id: string;
  name: string;
  domain: string;
  logo_url: string | null;
  is_active: boolean;
  created_at: string;
}

export interface CompetitorCreate {
  name: string;
  domain: string;
  logo_url?: string | null;
}

export interface CompetitorUpdate {
  name?: string;
  domain?: string;
  logo_url?: string | null;
  is_active?: boolean;
}

export type PageType =
  | "pricing"
  | "home_hero"
  | "landing"
  | "features_docs"
  | "integrations"
  | "alternatives";

export interface TrackedPage {
  id: string;
  competitor_id: string;
  url: string;
  page_type: PageType;
  check_interval_hours: number;
  is_active: boolean;
  last_checked_at: string | null;
  created_at: string;
}

export interface TrackedPageCreate {
  url: string;
  page_type: PageType;
  check_interval_hours?: number;
}

export interface TrackedPageUpdate {
  url?: string;
  page_type?: PageType;
  check_interval_hours?: number;
  is_active?: boolean;
}

export interface Snapshot {
  id: string;
  tracked_page_id: string;
  screenshot_url: string | null;
  html_archive_url: string | null;
  extracted_text: string;
  text_hash: string;
  metadata_: Record<string, unknown> | null;
  captured_at: string;
}

export type Severity = "low" | "medium" | "high" | "critical";

export interface ChangeEvent {
  id: string;
  diff_id: string;
  workspace_id: string;
  competitor_id: string;
  categories: string[];
  severity: Severity | null;
  ai_summary: string | null;
  ai_why_it_matters: string | null;
  ai_next_moves: string | null;
  ai_battlecard_block: string | null;
  ai_sales_talk_track: string | null;
  created_at: string;
}

export interface Diff {
  id: string;
  tracked_page_id: string;
  snapshot_before_id: string;
  snapshot_after_id: string;
  raw_diff: Record<string, unknown>;
  is_meaningful: boolean | null;
  noise_filtered: Record<string, unknown> | null;
  created_at: string;
}

export interface Digest {
  id: string;
  workspace_id: string;
  period_start: string;
  period_end: string;
  change_event_ids: string[];
  ranking_data: RankingEntry[] | null;
  html_body: string | null;
  markdown_body: string | null;
  email_sent_at: string | null;
  web_view_token: string | null;
  created_at: string;
}

export interface RankingEntry {
  change_event_id?: string;
  event_id?: string;
  rank_score: number;
  impact_score?: number;
  noise_score?: number;
  severity: string;
  signal_type?: string;
}

export interface Insight {
  id: string;
  change_event_id: string;
  insight_type: string;
  version: number;
  prompt_template_id: string;
  content: Record<string, unknown>;
  evidence_refs: string[] | null;
  is_grounded: boolean;
  validation_errors: string[] | null;
  model_used: string | null;
  provider: string | null;
  token_count_input: number | null;
  token_count_output: number | null;
  cost_usd: number | null;
  latency_ms: number | null;
  regeneration_reason: string | null;
  regenerated_from_id: string | null;
  created_at: string;
}

export interface InsightGenerateRequest {
  insight_types?: string[];
}

export interface InsightRegenerateRequest {
  reason?: string;
  custom_instructions?: string | null;
}

export interface WhiteLabelConfig {
  id: string;
  workspace_id: string;
  logo_url: string | null;
  brand_color: string;
  sender_name: string | null;
  sender_email: string | null;
  company_name: string | null;
  footer_text: string | null;
  created_at: string;
}

export interface WhiteLabelConfigUpsert {
  logo_url?: string | null;
  brand_color?: string;
  sender_name?: string | null;
  sender_email?: string | null;
  company_name?: string | null;
  footer_text?: string | null;
}

export interface DigestViewResponse {
  workspace_id: string;
  period_start: string;
  period_end: string;
  changes: DigestChangeItem[];
  ranking_data?: RankingEntry[] | null;
}

export interface DigestChangeItem {
  competitor_name: string;
  categories: string[];
  severity: string;
  summary: string | null;
  why_it_matters: string | null;
  next_moves: string | null;
  battlecard_block: string | null;
  sales_talk_track: string | null;
}

export interface DigestGenerateResponse {
  status: string;
  digest_id?: string;
  change_count?: number;
  web_view_token?: string;
  signed_url?: string;
  workspace_id?: string;
}

export interface SignedUrlResponse {
  signed_url: string;
  digest_id: string;
}

// ── Competitor Events (Multi-Signal) ──

export interface CompetitorEvent {
  id: string;
  workspace_id: string;
  competitor_id: string;
  signal_type: string;
  title: string;
  description: string | null;
  source_url: string | null;
  event_time: string;
  metadata_json: Record<string, unknown> | null;
  ai_summary: string | null;
  ai_implications: string | null;
  severity: string;
  is_processed: boolean;
  created_at: string;
}

export interface ActivityFeedItem {
  id: string;
  source: "change_event" | "competitor_event";
  workspace_id: string;
  competitor_id: string;
  competitor_name: string | null;
  signal_type: string;
  title: string;
  description: string | null;
  severity: string | null;
  source_url: string | null;
  event_time: string;
  created_at: string;
}

export type SignalType =
  | "website_change"
  | "pricing_change"
  | "product_change"
  | "blog_post"
  | "hiring"
  | "funding"
  | "review"
  | "marketing";

// ── Signal Sources ──

export interface SignalSource {
  id: string;
  workspace_id: string;
  competitor_id: string;
  signal_type: string;
  source_url: string;
  source_label: string | null;
  is_active: boolean;
  poll_interval_hours: number;
  last_checked_at: string | null;
  last_success_at: string | null;
  last_error: string | null;
  source_kind: string;
  metadata_json: Record<string, unknown> | null;
  created_at: string;
  updated_at: string | null;
}

export interface TestSourceResult {
  status: "valid" | "unreachable" | "unexpected_content" | "no_items_found";
  message: string;
  items_found: number;
  details: Record<string, unknown> | null;
}

export interface ScanResultItem {
  signal_type: string;
  source_url: string | null;
  events_found: number;
  events_created: number;
  events_skipped_dedup: number;
  error: string | null;
}

export interface ScanResult {
  competitor_id: string;
  competitor_name: string;
  sources_scanned: number;
  total_events_found: number;
  total_events_created: number;
  results: ScanResultItem[];
}

// ── Billing ──

export interface PlanLimits {
  max_competitors: number;
  max_tracked_pages: number;
  min_check_interval_hours: number;
  white_label: boolean;
  max_workspaces: number;
}

export interface IntervalPricing {
  month: number;
  year: number;
}

export interface PlanPricing {
  USD: IntervalPricing;
  INR: IntervalPricing;
}

export interface PlanInfo {
  plan_type: string;
  name: string;
  price_monthly_cents: number;
  pricing: PlanPricing;
  annual_discount_pct: number;
  limits: PlanLimits;
}

export interface WorkspaceBilling {
  id: string;
  workspace_id: string;
  plan_type: string;
  subscription_status: string;
  currency: string;
  billing_interval: string;
  plan_price: number | null;
  razorpay_customer_id: string | null;
  razorpay_subscription_id: string | null;
  trial_ends_at: string | null;
  current_period_end: string | null;
  cancel_at_period_end: boolean;
  grace_period_ends_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface BillingOverview {
  billing: WorkspaceBilling | null;
  plan: PlanInfo;
  usage: {
    competitors: number;
    competitors_limit: number;
    tracked_pages: number;
    tracked_pages_limit: number;
  };
}

export interface CheckoutSessionResponse {
  subscription_id: string;
  razorpay_key_id: string;
  short_url: string | null;
  workspace_id: string;
  plan_type: string;
  currency: string;
  interval: string;
  plan_price: number;
}

export interface PaymentVerifyRequest {
  razorpay_subscription_id: string;
  razorpay_payment_id: string;
  razorpay_signature: string;
}

export interface PaymentVerifyResponse {
  verified: boolean;
  subscription_status: string;
}
