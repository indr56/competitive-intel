import type {
  ActivityFeedItem,
  BillingOverview,
  ChangeEvent,
  CheckoutSessionResponse,
  Competitor,
  CompetitorCreate,
  CompetitorUpdate,
  CompetitorEvent,
  Diff,
  Digest,
  DigestGenerateResponse,
  DigestViewResponse,
  Insight,
  InsightGenerateRequest,
  InsightRegenerateRequest,
  PaymentVerifyResponse,
  PlanInfo,
  SignedUrlResponse,
  Snapshot,
  TrackedPage,
  TrackedPageCreate,
  TrackedPageUpdate,
  WhiteLabelConfig,
  WhiteLabelConfigUpsert,
  Workspace,
  WorkspaceCreate,
  SignalSource,
  TestSourceResult,
  ScanResult,
  MonitoredPrompt,
  PromptCluster,
  ClusteringResult,
  AIKeyword,
  AIPromptSource,
  AITrackedPrompt,
  AIVisibilityEvent,
  AIImpactInsight,
  VisibilityTrendsData,
  PromptLimits,
  RunPromptsResponse,
} from "./types";

export const API_URL =
  process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
    this.name = "ApiError";
  }
}

async function request<T>(
  path: string,
  options?: RequestInit & { retry?: number }
): Promise<T> {
  const maxRetries = options?.retry ?? 1;
  let lastError: Error | null = null;

  for (let attempt = 0; attempt < maxRetries; attempt++) {
    try {
      const res = await fetch(`${API_URL}${path}`, {
        headers: { "Content-Type": "application/json", ...options?.headers },
        ...options,
      });
      if (!res.ok) {
        const body = await res.text();
        throw new ApiError(res.status, `API ${res.status}: ${body}`);
      }
      if (res.status === 204) return undefined as T;
      return res.json();
    } catch (err) {
      lastError = err as Error;
      if (attempt < maxRetries - 1) {
        await new Promise((r) => setTimeout(r, 500 * (attempt + 1)));
      }
    }
  }
  throw lastError;
}

// ── Workspaces ──

export const workspaces = {
  list: () => request<Workspace[]>("/api/workspaces"),
  create: (data: WorkspaceCreate) =>
    request<Workspace>("/api/workspaces", {
      method: "POST",
      body: JSON.stringify(data),
    }),
  get: (id: string) => request<Workspace>(`/api/workspaces/${id}`),
  update: (id: string, data: WorkspaceCreate) =>
    request<Workspace>(`/api/workspaces/${id}`, {
      method: "PATCH",
      body: JSON.stringify(data),
    }),
};

// ── Competitors ──

export const competitors = {
  list: (workspaceId: string) =>
    request<Competitor[]>(`/api/workspaces/${workspaceId}/competitors`),
  create: (workspaceId: string, data: CompetitorCreate) =>
    request<Competitor>(`/api/workspaces/${workspaceId}/competitors`, {
      method: "POST",
      body: JSON.stringify(data),
    }),
  get: (id: string) => request<Competitor>(`/api/competitors/${id}`),
  update: (id: string, data: CompetitorUpdate) =>
    request<Competitor>(`/api/competitors/${id}`, {
      method: "PATCH",
      body: JSON.stringify(data),
    }),
  delete: (id: string) =>
    request<void>(`/api/competitors/${id}`, { method: "DELETE" }),
};

// ── Tracked Pages ──

export const trackedPages = {
  list: (competitorId: string) =>
    request<TrackedPage[]>(`/api/competitors/${competitorId}/pages`),
  create: (competitorId: string, data: TrackedPageCreate) =>
    request<TrackedPage>(`/api/competitors/${competitorId}/pages`, {
      method: "POST",
      body: JSON.stringify(data),
    }),
  get: (id: string) => request<TrackedPage>(`/api/pages/${id}`),
  update: (id: string, data: TrackedPageUpdate) =>
    request<TrackedPage>(`/api/pages/${id}`, {
      method: "PATCH",
      body: JSON.stringify(data),
    }),
  delete: (id: string) =>
    request<void>(`/api/pages/${id}`, { method: "DELETE" }),
  captureNow: (id: string, sync = false) =>
    request<Record<string, unknown>>(
      `/api/pages/${id}/capture-now?sync=${sync}`,
      { method: "POST" }
    ),
};

// ── Snapshots ──

export const snapshots = {
  list: (pageId: string, limit = 20) =>
    request<Snapshot[]>(`/api/pages/${pageId}/snapshots?limit=${limit}`),
  latest: (pageId: string) =>
    request<Snapshot>(`/api/pages/${pageId}/snapshots/latest`),
  get: (id: string) => request<Snapshot>(`/api/snapshots/${id}`),
};

// ── Changes ──

export const changes = {
  list: (params?: {
    workspace_id?: string;
    category?: string;
    severity?: string;
    limit?: number;
    offset?: number;
  }) => {
    const qs = new URLSearchParams();
    if (params?.workspace_id) qs.set("workspace_id", params.workspace_id);
    if (params?.category) qs.set("category", params.category);
    if (params?.severity) qs.set("severity", params.severity);
    if (params?.limit) qs.set("limit", String(params.limit));
    if (params?.offset) qs.set("offset", String(params.offset));
    return request<ChangeEvent[]>(`/api/changes?${qs.toString()}`);
  },
  get: (id: string) => request<ChangeEvent>(`/api/changes/${id}`),
  forPage: (pageId: string) =>
    request<ChangeEvent[]>(`/api/pages/${pageId}/changes`),
};

// ── Diffs ──

export const diffs = {
  forPage: (pageId: string) =>
    request<Diff[]>(`/api/pages/${pageId}/diffs`),
};

// ── Insights ──

export const insights = {
  listForEvent: (changeEventId: string, insightType?: string) => {
    const qs = insightType ? `?insight_type=${insightType}` : "";
    return request<Insight[]>(
      `/api/change-events/${changeEventId}/insights${qs}`
    );
  },
  get: (id: string) => request<Insight>(`/api/insights/${id}`),
  generate: (changeEventId: string, data?: InsightGenerateRequest) =>
    request<Insight[]>(
      `/api/change-events/${changeEventId}/insights/generate`,
      { method: "POST", body: JSON.stringify(data ?? {}) }
    ),
  regenerate: (insightId: string, data?: InsightRegenerateRequest) =>
    request<Insight>(`/api/insights/${insightId}/regenerate`, {
      method: "POST",
      body: JSON.stringify(data ?? {}),
    }),
};

// ── Digests ──

export const digests = {
  list: (workspaceId: string) =>
    request<Digest[]>(`/api/workspaces/${workspaceId}/digests`),
  get: (id: string) => request<Digest>(`/api/digests/${id}`),
  generate: (workspaceId: string, periodDays = 7) =>
    request<DigestGenerateResponse>(
      `/api/workspaces/${workspaceId}/digests/generate?period_days=${periodDays}`,
      { method: "POST" }
    ),
  resend: (id: string) =>
    request<Record<string, unknown>>(`/api/digests/${id}/resend`, {
      method: "POST",
    }),
  signedUrl: (id: string) =>
    request<SignedUrlResponse>(`/api/digests/${id}/signed-url`),
  webView: (token: string) =>
    request<DigestViewResponse>(`/api/digest-view/${token}`),
};

// ── White-Label Config ──

export const whiteLabel = {
  get: (workspaceId: string) =>
    request<WhiteLabelConfig>(
      `/api/workspaces/${workspaceId}/white-label`
    ),
  upsert: (workspaceId: string, data: WhiteLabelConfigUpsert) =>
    request<WhiteLabelConfig>(
      `/api/workspaces/${workspaceId}/white-label`,
      { method: "PUT", body: JSON.stringify(data) }
    ),
};

// ── Events (Multi-Signal) ──

export const events = {
  list: (workspaceId: string, params?: { signal_type?: string; competitor_id?: string; limit?: number }) => {
    const qs = new URLSearchParams();
    if (params?.signal_type) qs.set("signal_type", params.signal_type);
    if (params?.competitor_id) qs.set("competitor_id", params.competitor_id);
    if (params?.limit) qs.set("limit", String(params.limit));
    const q = qs.toString();
    return request<CompetitorEvent[]>(`/api/workspaces/${workspaceId}/events${q ? `?${q}` : ""}`);
  },
  forCompetitor: (competitorId: string, signalType?: string) => {
    const qs = signalType ? `?signal_type=${signalType}` : "";
    return request<CompetitorEvent[]>(`/api/competitors/${competitorId}/events${qs}`);
  },
  get: (eventId: string) => request<CompetitorEvent>(`/api/events/${eventId}`),
  analyze: (eventId: string) => request<CompetitorEvent>(`/api/events/${eventId}/analyze`, { method: "POST" }),
  signalTypes: () => request<string[]>("/api/events/signal-types"),
  create: (workspaceId: string, competitorId: string, data: {
    signal_type: string;
    title: string;
    description?: string;
    source_url?: string;
    severity?: string;
  }) =>
    request<CompetitorEvent>(
      `/api/workspaces/${workspaceId}/competitors/${competitorId}/events`,
      { method: "POST", body: JSON.stringify(data) }
    ),
};

export const activityFeed = {
  list: (workspaceId: string, params?: { signal_type?: string; limit?: number; offset?: number }) => {
    const qs = new URLSearchParams();
    if (params?.signal_type) qs.set("signal_type", params.signal_type);
    if (params?.limit) qs.set("limit", String(params.limit));
    if (params?.offset) qs.set("offset", String(params.offset));
    const q = qs.toString();
    return request<ActivityFeedItem[]>(`/api/workspaces/${workspaceId}/activity${q ? `?${q}` : ""}`);
  },
};

// ── Signal Sources ──

export const signalSources = {
  list: (competitorId: string, signalType?: string) => {
    const qs = signalType ? `?signal_type=${signalType}` : "";
    return request<SignalSource[]>(`/api/competitors/${competitorId}/sources${qs}`);
  },
  get: (sourceId: string) => request<SignalSource>(`/api/sources/${sourceId}`),
  create: (competitorId: string, data: {
    signal_type: string;
    source_url: string;
    source_label?: string;
    poll_interval_hours?: number;
  }) =>
    request<SignalSource>(
      `/api/competitors/${competitorId}/sources`,
      { method: "POST", body: JSON.stringify(data) }
    ),
  update: (sourceId: string, data: {
    source_url?: string;
    source_label?: string;
    is_active?: boolean;
    poll_interval_hours?: number;
  }) =>
    request<SignalSource>(
      `/api/sources/${sourceId}`,
      { method: "PATCH", body: JSON.stringify(data) }
    ),
  delete: (sourceId: string) =>
    request<void>(`/api/sources/${sourceId}`, { method: "DELETE" }),
  test: (sourceId: string) =>
    request<TestSourceResult>(`/api/sources/${sourceId}/test`, { method: "POST" }),
  testUrl: (signalType: string, sourceUrl: string) =>
    request<TestSourceResult>(
      `/api/sources/test-url?signal_type=${encodeURIComponent(signalType)}&source_url=${encodeURIComponent(sourceUrl)}`,
      { method: "POST" }
    ),
  scan: (competitorId: string, signalTypes?: string[]) => {
    const qs = signalTypes?.length
      ? `?${signalTypes.map(t => `signal_types=${t}`).join("&")}`
      : "";
    return request<ScanResult>(
      `/api/competitors/${competitorId}/scan${qs}`,
      { method: "POST" }
    );
  },
};

// ── Billing ──

export const billing = {
  plans: () => request<PlanInfo[]>("/api/billing/plans"),
  overview: (workspaceId: string) =>
    request<BillingOverview>(`/api/workspaces/${workspaceId}/billing`),
  checkout: (workspaceId: string, planType: string, currency: string = "USD", interval: string = "month") =>
    request<CheckoutSessionResponse>(
      `/api/workspaces/${workspaceId}/billing/checkout`,
      {
        method: "POST",
        body: JSON.stringify({
          plan_type: planType,
          currency,
          interval,
        }),
      }
    ),
  verify: (
    workspaceId: string,
    data: {
      razorpay_subscription_id: string;
      razorpay_payment_id: string;
      razorpay_signature: string;
    }
  ) =>
    request<PaymentVerifyResponse>(
      `/api/workspaces/${workspaceId}/billing/verify`,
      { method: "POST", body: JSON.stringify(data) }
    ),
  cancel: (workspaceId: string) =>
    request<Record<string, unknown>>(
      `/api/workspaces/${workspaceId}/billing/cancel`,
      { method: "POST" }
    ),
  sync: (workspaceId: string) =>
    request<Record<string, unknown>>(
      `/api/workspaces/${workspaceId}/billing/sync`,
      { method: "POST" }
    ),
};

// ── Prompt Clustering ──

export const promptClusters = {
  listPrompts: (workspaceId: string, clusterId?: string) => {
    const qs = clusterId ? `?cluster_id=${clusterId}` : "";
    return request<MonitoredPrompt[]>(`/api/workspaces/${workspaceId}/prompts${qs}`);
  },
  createPrompt: (workspaceId: string, rawText: string) =>
    request<MonitoredPrompt>(
      `/api/workspaces/${workspaceId}/prompts`,
      { method: "POST", body: JSON.stringify({ raw_text: rawText }) }
    ),
  deletePrompt: (promptId: string) =>
    request<void>(`/api/prompts/${promptId}`, { method: "DELETE" }),
  listClusters: (workspaceId: string) =>
    request<PromptCluster[]>(`/api/workspaces/${workspaceId}/prompt-clusters`),
  getCluster: (clusterId: string) =>
    request<PromptCluster>(`/api/prompt-clusters/${clusterId}`),
  runClustering: (workspaceId: string, threshold?: number) => {
    const qs = threshold != null ? `?threshold=${threshold}` : "";
    return request<ClusteringResult>(
      `/api/workspaces/${workspaceId}/prompt-clusters/run${qs}`,
      { method: "POST" }
    );
  },
  deleteCluster: (clusterId: string) =>
    request<void>(`/api/prompt-clusters/${clusterId}`, { method: "DELETE" }),
};

// ── AI Visibility Intelligence ──

export const aiVisibility = {
  // Keywords
  listKeywords: (wsId: string, source?: string) => {
    const qs = source ? `?source=${source}` : "";
    return request<AIKeyword[]>(`/api/workspaces/${wsId}/ai-visibility/keywords${qs}`);
  },
  addKeyword: (wsId: string, keyword: string, source = "user") =>
    request<AIKeyword>(`/api/workspaces/${wsId}/ai-visibility/keywords`, {
      method: "POST", body: JSON.stringify({ keyword, source }),
    }),
  approveKeywords: (wsId: string, ids: string[]) =>
    request<AIKeyword[]>(`/api/workspaces/${wsId}/ai-visibility/keywords/approve`, {
      method: "POST", body: JSON.stringify(ids),
    }),
  deleteKeyword: (wsId: string, kwId: string) =>
    request<void>(`/api/workspaces/${wsId}/ai-visibility/keywords/${kwId}`, { method: "DELETE" }),
  extractKeywords: (wsId: string) =>
    request<{ keywords_extracted: number; keywords_created: number }>(`/api/workspaces/${wsId}/ai-visibility/keywords/extract`, { method: "POST" }),

  // Suggestions
  listSuggestions: (wsId: string, sourceType?: string, status?: string) => {
    const qs = new URLSearchParams();
    if (sourceType) qs.set("source_type", sourceType);
    if (status) qs.set("status", status);
    const q = qs.toString();
    return request<AIPromptSource[]>(`/api/workspaces/${wsId}/ai-visibility/suggestions${q ? `?${q}` : ""}`);
  },
  addSuggestion: (wsId: string, promptText: string, sourceType = "manual") =>
    request<AIPromptSource>(`/api/workspaces/${wsId}/ai-visibility/suggestions`, {
      method: "POST", body: JSON.stringify({ prompt_text: promptText, source_type: sourceType }),
    }),
  generateSuggestions: (wsId: string, sourceTypes?: string[]) =>
    request<{ suggestions_created: number; by_source: Record<string, number> }>(`/api/workspaces/${wsId}/ai-visibility/suggestions/generate`, {
      method: "POST", body: JSON.stringify(sourceTypes ? { source_types: sourceTypes } : {}),
    }),
  approveSuggestions: (wsId: string, ids: string[]) =>
    request<AITrackedPrompt[]>(`/api/workspaces/${wsId}/ai-visibility/suggestions/approve`, {
      method: "POST", body: JSON.stringify({ prompt_source_ids: ids }),
    }),
  rejectSuggestions: (wsId: string, ids: string[]) =>
    request<{ rejected: number }>(`/api/workspaces/${wsId}/ai-visibility/suggestions/reject`, {
      method: "POST", body: JSON.stringify({ prompt_source_ids: ids }),
    }),

  // Tracked Prompts
  listPrompts: (wsId: string, activeOnly = false) =>
    request<AITrackedPrompt[]>(`/api/workspaces/${wsId}/ai-visibility/prompts${activeOnly ? "?active_only=true" : ""}`),
  pausePrompt: (wsId: string, promptId: string) =>
    request<{ id: string; is_active: boolean }>(`/api/workspaces/${wsId}/ai-visibility/prompts/${promptId}/pause`, { method: "POST" }),
  deletePrompt: (wsId: string, promptId: string) =>
    request<void>(`/api/workspaces/${wsId}/ai-visibility/prompts/${promptId}`, { method: "DELETE" }),
  getPromptLimits: (wsId: string) =>
    request<PromptLimits>(`/api/workspaces/${wsId}/ai-visibility/prompts/limits`),

  // Execution
  runAllPrompts: (wsId: string, force = true) =>
    request<RunPromptsResponse>(`/api/workspaces/${wsId}/ai-visibility/prompts/run?force=${force}`, { method: "POST" }),
  runSinglePrompt: (wsId: string, promptId: string, force = true) =>
    request<RunPromptsResponse>(`/api/workspaces/${wsId}/ai-visibility/prompts/${promptId}/run?force=${force}`, { method: "POST" }),

  // Visibility
  listEvents: (wsId: string, competitorId?: string, engine?: string) => {
    const qs = new URLSearchParams();
    if (competitorId) qs.set("competitor_id", competitorId);
    if (engine) qs.set("engine", engine);
    const q = qs.toString();
    return request<AIVisibilityEvent[]>(`/api/workspaces/${wsId}/ai-visibility/events${q ? `?${q}` : ""}`);
  },
  filterResults: (wsId: string) =>
    request<{ events_created: number }>(`/api/workspaces/${wsId}/ai-visibility/filter`, { method: "POST" }),

  // Trends
  getTrends: (wsId: string, competitorId?: string, days = 30, engine?: string) => {
    const qs = new URLSearchParams();
    if (competitorId) qs.set("competitor_id", competitorId);
    qs.set("days", String(days));
    if (engine) qs.set("engine", engine);
    return request<VisibilityTrendsData>(`/api/workspaces/${wsId}/ai-visibility/trends?${qs.toString()}`);
  },

  // Impact Insights
  listInsights: (wsId: string, competitorId?: string, priority?: string) => {
    const qs = new URLSearchParams();
    if (competitorId) qs.set("competitor_id", competitorId);
    if (priority) qs.set("priority", priority);
    const q = qs.toString();
    return request<AIImpactInsight[]>(`/api/workspaces/${wsId}/ai-visibility/insights${q ? `?${q}` : ""}`);
  },
  runCorrelation: (wsId: string, days = 7) =>
    request<{ insights_created: number }>(`/api/workspaces/${wsId}/ai-visibility/insights/correlate?days=${days}`, { method: "POST" }),
};

// ── Health ──

export const health = {
  check: () => request<{ status: string; version: string }>("/health"),
};
