const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, {
    headers: { "Content-Type": "application/json", ...options?.headers },
    ...options,
  });
  if (!res.ok) {
    const body = await res.text();
    throw new Error(`API ${res.status}: ${body}`);
  }
  if (res.status === 204) return undefined as T;
  return res.json();
}

// ── Workspaces ──

export const workspaces = {
  list: () => request<any[]>("/api/workspaces"),
  create: (data: { name: string; slug: string }) =>
    request<any>("/api/workspaces", { method: "POST", body: JSON.stringify(data) }),
  get: (id: string) => request<any>(`/api/workspaces/${id}`),
};

// ── Competitors ──

export const competitors = {
  list: (workspaceId: string) =>
    request<any[]>(`/api/workspaces/${workspaceId}/competitors`),
  create: (workspaceId: string, data: { name: string; domain: string; logo_url?: string }) =>
    request<any>(`/api/workspaces/${workspaceId}/competitors`, {
      method: "POST",
      body: JSON.stringify(data),
    }),
  get: (id: string) => request<any>(`/api/competitors/${id}`),
  update: (id: string, data: Record<string, any>) =>
    request<any>(`/api/competitors/${id}`, { method: "PATCH", body: JSON.stringify(data) }),
  delete: (id: string) =>
    request<void>(`/api/competitors/${id}`, { method: "DELETE" }),
};

// ── Tracked Pages ──

export const trackedPages = {
  list: (competitorId: string) =>
    request<any[]>(`/api/competitors/${competitorId}/pages`),
  create: (competitorId: string, data: { url: string; page_type: string; check_interval_hours?: number }) =>
    request<any>(`/api/competitors/${competitorId}/pages`, {
      method: "POST",
      body: JSON.stringify(data),
    }),
  get: (id: string) => request<any>(`/api/pages/${id}`),
  captureNow: (id: string) =>
    request<any>(`/api/pages/${id}/capture-now`, { method: "POST" }),
};

// ── Snapshots ──

export const snapshots = {
  list: (pageId: string, limit = 20) =>
    request<any[]>(`/api/pages/${pageId}/snapshots?limit=${limit}`),
  latest: (pageId: string) =>
    request<any>(`/api/pages/${pageId}/snapshots/latest`),
};

// ── Changes ──

export const changes = {
  list: (params?: { workspace_id?: string; category?: string; severity?: string; limit?: number }) => {
    const qs = new URLSearchParams();
    if (params?.workspace_id) qs.set("workspace_id", params.workspace_id);
    if (params?.category) qs.set("category", params.category);
    if (params?.severity) qs.set("severity", params.severity);
    if (params?.limit) qs.set("limit", String(params.limit));
    return request<any[]>(`/api/changes?${qs.toString()}`);
  },
  get: (id: string) => request<any>(`/api/changes/${id}`),
  forPage: (pageId: string) => request<any[]>(`/api/pages/${pageId}/changes`),
};

// ── Digests ──

export const digests = {
  list: (workspaceId: string) =>
    request<any[]>(`/api/workspaces/${workspaceId}/digests`),
  get: (id: string) => request<any>(`/api/digests/${id}`),
  resend: (id: string) =>
    request<any>(`/api/digests/${id}/resend`, { method: "POST" }),
  webView: (token: string) => request<any>(`/api/digest-view/${token}`),
};
