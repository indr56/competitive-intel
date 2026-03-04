import { describe, it, expect, vi, beforeEach } from "vitest";

const API_URL = "http://localhost:8000";

describe("API Client Integration", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        json: async () => ({}),
        text: async () => "",
        headers: new Headers(),
      })
    );
  });

  it("health endpoint connects to backend", async () => {
    const mockFetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ status: "ok", version: "0.1.0" }),
      headers: new Headers(),
    });
    vi.stubGlobal("fetch", mockFetch);

    const { health } = await import("@/lib/api");
    const result = await health.check();
    expect(result.status).toBe("ok");
    expect(mockFetch).toHaveBeenCalledWith(
      `${API_URL}/health`,
      expect.objectContaining({
        headers: expect.objectContaining({
          "Content-Type": "application/json",
        }),
      })
    );
  });

  it("workspaces.list calls correct endpoint", async () => {
    const mockData = [
      { id: "ws-1", name: "Test WS", slug: "test-ws", account_id: "acc-1", created_at: "2026-01-01" },
    ];
    const mockFetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => mockData,
      headers: new Headers(),
    });
    vi.stubGlobal("fetch", mockFetch);

    const { workspaces } = await import("@/lib/api");
    const result = await workspaces.list();
    expect(result).toEqual(mockData);
    expect(mockFetch).toHaveBeenCalledWith(
      `${API_URL}/api/workspaces`,
      expect.anything()
    );
  });

  it("changes.list passes filter params correctly", async () => {
    const mockFetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => [],
      headers: new Headers(),
    });
    vi.stubGlobal("fetch", mockFetch);

    const { changes } = await import("@/lib/api");
    await changes.list({
      workspace_id: "ws-1",
      severity: "high",
      category: "pricing_change",
      limit: 10,
    });

    const calledUrl = mockFetch.mock.calls[0][0] as string;
    expect(calledUrl).toContain("workspace_id=ws-1");
    expect(calledUrl).toContain("severity=high");
    expect(calledUrl).toContain("category=pricing_change");
    expect(calledUrl).toContain("limit=10");
  });

  it("changes.get calls correct endpoint", async () => {
    const mockChange = {
      id: "ce-1",
      diff_id: "d-1",
      workspace_id: "ws-1",
      competitor_id: "comp-1",
      categories: ["pricing_change"],
      severity: "high",
      ai_summary: "Price went up 20%",
      created_at: "2026-03-01",
    };
    const mockFetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => mockChange,
      headers: new Headers(),
    });
    vi.stubGlobal("fetch", mockFetch);

    const { changes } = await import("@/lib/api");
    const result = await changes.get("ce-1");
    expect(result.id).toBe("ce-1");
    expect(result.ai_summary).toBe("Price went up 20%");
    expect(mockFetch).toHaveBeenCalledWith(
      `${API_URL}/api/changes/ce-1`,
      expect.anything()
    );
  });

  it("insights.listForEvent calls correct endpoint", async () => {
    const mockInsights = [
      {
        id: "ins-1",
        change_event_id: "ce-1",
        insight_type: "change_analysis",
        version: 1,
        content: { summary: "Test" },
        is_grounded: true,
      },
    ];
    const mockFetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => mockInsights,
      headers: new Headers(),
    });
    vi.stubGlobal("fetch", mockFetch);

    const { insights } = await import("@/lib/api");
    const result = await insights.listForEvent("ce-1");
    expect(result).toHaveLength(1);
    expect(result[0].insight_type).toBe("change_analysis");
    expect(mockFetch).toHaveBeenCalledWith(
      `${API_URL}/api/change-events/ce-1/insights`,
      expect.anything()
    );
  });

  it("insights.listForEvent with type filter", async () => {
    const mockFetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => [],
      headers: new Headers(),
    });
    vi.stubGlobal("fetch", mockFetch);

    const { insights } = await import("@/lib/api");
    await insights.listForEvent("ce-1", "battlecard");
    const calledUrl = mockFetch.mock.calls[0][0] as string;
    expect(calledUrl).toContain("insight_type=battlecard");
  });

  it("digests.list calls correct endpoint", async () => {
    const mockFetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => [],
      headers: new Headers(),
    });
    vi.stubGlobal("fetch", mockFetch);

    const { digests } = await import("@/lib/api");
    await digests.list("ws-1");
    expect(mockFetch).toHaveBeenCalledWith(
      `${API_URL}/api/workspaces/ws-1/digests`,
      expect.anything()
    );
  });

  it("digests.generate calls POST with period_days", async () => {
    const mockFetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ status: "generated", digest_id: "d-1" }),
      headers: new Headers(),
    });
    vi.stubGlobal("fetch", mockFetch);

    const { digests } = await import("@/lib/api");
    const result = await digests.generate("ws-1", 14);
    expect(result.status).toBe("generated");
    const calledUrl = mockFetch.mock.calls[0][0] as string;
    expect(calledUrl).toContain("period_days=14");
    expect(mockFetch.mock.calls[0][1]?.method).toBe("POST");
  });

  it("API error throws with status code", async () => {
    const mockFetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 404,
      text: async () => '{"detail":"Not found"}',
      headers: new Headers(),
    });
    vi.stubGlobal("fetch", mockFetch);

    const { workspaces } = await import("@/lib/api");
    await expect(workspaces.get("nonexistent")).rejects.toThrow("API 404");
  });

  it("competitors.create sends POST with body", async () => {
    const mockComp = {
      id: "c-1",
      workspace_id: "ws-1",
      name: "Rival",
      domain: "rival.com",
      is_active: true,
    };
    const mockFetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 201,
      json: async () => mockComp,
      headers: new Headers(),
    });
    vi.stubGlobal("fetch", mockFetch);

    const { competitors } = await import("@/lib/api");
    const result = await competitors.create("ws-1", {
      name: "Rival",
      domain: "rival.com",
    });
    expect(result.name).toBe("Rival");
    expect(mockFetch.mock.calls[0][1]?.method).toBe("POST");
    const body = JSON.parse(mockFetch.mock.calls[0][1]?.body as string);
    expect(body.name).toBe("Rival");
    expect(body.domain).toBe("rival.com");
  });

  it("whiteLabel.upsert sends PUT", async () => {
    const mockFetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ id: "wl-1", brand_color: "#FF0000" }),
      headers: new Headers(),
    });
    vi.stubGlobal("fetch", mockFetch);

    const { whiteLabel } = await import("@/lib/api");
    await whiteLabel.upsert("ws-1", { brand_color: "#FF0000" });
    expect(mockFetch.mock.calls[0][1]?.method).toBe("PUT");
    expect(mockFetch).toHaveBeenCalledWith(
      `${API_URL}/api/workspaces/ws-1/white-label`,
      expect.anything()
    );
  });
});
