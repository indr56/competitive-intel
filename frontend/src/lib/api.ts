import type {
  BillingOverview,
  ChangeEvent,
  CheckoutSessionResponse,
  Competitor,
  CompetitorCreate,
  CompetitorUpdate,
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

// ── Billing ──

export const billing = {
  plans: () => request<PlanInfo[]>("/api/billing/plans"),
  overview: (workspaceId: string) =>
    request<BillingOverview>(`/api/workspaces/${workspaceId}/billing`),
  checkout: (workspaceId: string, planType: string) =>
    request<CheckoutSessionResponse>(
      `/api/workspaces/${workspaceId}/billing/checkout`,
      {
        method: "POST",
        body: JSON.stringify({
          plan_type: planType,
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

// ── Health ──

export const health = {
  check: () => request<{ status: string; version: string }>("/health"),
};
