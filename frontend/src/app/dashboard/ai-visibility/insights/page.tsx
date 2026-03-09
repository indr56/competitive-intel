"use client";

import { useState } from "react";
import {
  Lightbulb,
  AlertTriangle,
  ArrowUpRight,
  ArrowDownRight,
  Minus,
  RefreshCw,
  Filter,
  ExternalLink,
  Zap,
} from "lucide-react";
import { useActiveWorkspace, useFetch } from "@/lib/hooks";
import { aiVisibility, competitors as competitorsApi } from "@/lib/api";

const PRIORITY_STYLES: Record<string, { bg: string; text: string; label: string }> = {
  P0: { bg: "bg-red-50 border-red-200", text: "text-red-700", label: "Critical" },
  P1: { bg: "bg-amber-50 border-amber-200", text: "text-amber-700", label: "High" },
  P2: { bg: "bg-blue-50 border-blue-200", text: "text-blue-700", label: "Medium" },
};

const ENGINE_BADGE: Record<string, string> = {
  chatgpt: "bg-green-100 text-green-700",
  perplexity: "bg-blue-100 text-blue-700",
  claude: "bg-orange-100 text-orange-700",
  gemini: "bg-purple-100 text-purple-700",
};

export default function AIImpactInsightsPage() {
  const { active, loading: wsLoading } = useActiveWorkspace();
  const wsId = active?.id ?? "";

  const [selComp, setSelComp] = useState("");
  const [selPriority, setSelPriority] = useState("");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");

  const { data: comps } = useFetch(
    () => (wsId ? competitorsApi.list(wsId) : Promise.resolve([])),
    [wsId]
  );

  const {
    data: insights,
    loading,
    refetch,
  } = useFetch(
    () =>
      wsId
        ? aiVisibility.listInsights(wsId, selComp || undefined, selPriority || undefined)
        : Promise.resolve([]),
    [wsId, selComp, selPriority]
  );

  if (wsLoading || !active) {
    return <div className="p-8 text-gray-500">Loading workspace…</div>;
  }

  const flash = (m: string) => {
    setMsg(m);
    setTimeout(() => setMsg(""), 4000);
  };

  const handleCorrelate = async () => {
    setBusy(true);
    try {
      const res = await aiVisibility.runCorrelation(wsId);
      flash(`Correlation complete: ${res.insights_created} new insights`);
      refetch();
    } catch (e: any) {
      flash(e.message);
    }
    setBusy(false);
  };

  const items = insights ?? [];
  const p0Count = items.filter((i) => i.priority_level === "P0").length;
  const p1Count = items.filter((i) => i.priority_level === "P1").length;

  const getCompName = (compId: string) =>
    (comps ?? []).find((c) => c.id === compId)?.name ?? "Unknown";

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-gray-900 flex items-center gap-2">
            <Lightbulb className="h-5 w-5 text-violet-600" />
            AI Impact Insights
          </h1>
          <p className="text-sm text-gray-500 mt-0.5">
            Correlations between competitor signals and AI visibility changes
          </p>
        </div>
        <button
          onClick={handleCorrelate}
          disabled={busy}
          className="flex items-center gap-1.5 rounded-lg bg-violet-600 px-4 py-2 text-sm font-medium text-white hover:bg-violet-700 transition disabled:opacity-50"
        >
          {busy ? <RefreshCw className="h-4 w-4 animate-spin" /> : <Zap className="h-4 w-4" />}
          Run Correlation
        </button>
      </div>

      {msg && (
        <div className="rounded-lg bg-violet-50 border border-violet-200 px-4 py-2 text-sm text-violet-700">
          {msg}
        </div>
      )}

      {/* Summary cards */}
      <div className="grid grid-cols-3 gap-4">
        <div className="rounded-xl border bg-white p-4">
          <p className="text-[11px] font-medium text-gray-400 uppercase">Total Insights</p>
          <p className="text-2xl font-bold text-gray-900 mt-1">{items.length}</p>
        </div>
        <div className="rounded-xl border border-red-100 bg-red-50/30 p-4">
          <p className="text-[11px] font-medium text-red-400 uppercase">Critical (P0)</p>
          <p className="text-2xl font-bold text-red-700 mt-1">{p0Count}</p>
        </div>
        <div className="rounded-xl border border-amber-100 bg-amber-50/30 p-4">
          <p className="text-[11px] font-medium text-amber-400 uppercase">High (P1)</p>
          <p className="text-2xl font-bold text-amber-700 mt-1">{p1Count}</p>
        </div>
      </div>

      {/* Filters */}
      <div className="flex flex-wrap items-center gap-3">
        <div className="flex items-center gap-1.5 text-xs text-gray-500">
          <Filter className="h-3.5 w-3.5" />
        </div>
        <select
          value={selComp}
          onChange={(e) => setSelComp(e.target.value)}
          className="rounded-md border px-2.5 py-1.5 text-xs text-gray-700 focus:outline-none focus:ring-2 focus:ring-violet-300"
        >
          <option value="">All Competitors</option>
          {(comps ?? []).map((c) => (
            <option key={c.id} value={c.id}>
              {c.name}
            </option>
          ))}
        </select>
        <select
          value={selPriority}
          onChange={(e) => setSelPriority(e.target.value)}
          className="rounded-md border px-2.5 py-1.5 text-xs text-gray-700 focus:outline-none focus:ring-2 focus:ring-violet-300"
        >
          <option value="">All Priorities</option>
          <option value="P0">P0 — Critical</option>
          <option value="P1">P1 — High</option>
          <option value="P2">P2 — Medium</option>
        </select>
      </div>

      {/* Insights list */}
      {loading ? (
        <div className="text-sm text-gray-400 py-8 text-center">Loading insights…</div>
      ) : items.length === 0 ? (
        <div className="rounded-xl border bg-white p-8 text-center">
          <Lightbulb className="h-10 w-10 text-gray-300 mx-auto mb-3" />
          <p className="text-sm text-gray-500">
            No insights yet. Make sure you have tracked prompts running and competitor signals being collected, then click <strong>Run Correlation</strong>.
          </p>
        </div>
      ) : (
        <div className="space-y-3">
          {items.map((insight) => {
            const pStyle = PRIORITY_STYLES[insight.priority_level] ?? PRIORITY_STYLES.P2;
            const delta = insight.visibility_after - insight.visibility_before;
            const DeltaIcon =
              delta > 0 ? ArrowUpRight : delta < 0 ? ArrowDownRight : Minus;
            const deltaColor =
              delta > 0 ? "text-green-600" : delta < 0 ? "text-red-600" : "text-gray-400";

            return (
              <div
                key={insight.id}
                className={`rounded-xl border ${pStyle.bg} p-5`}
              >
                {/* Top row: priority + competitor + signal */}
                <div className="flex items-start justify-between gap-3 mb-3">
                  <div className="flex items-center gap-2">
                    <span
                      className={`text-[10px] font-bold px-2 py-0.5 rounded-full border ${pStyle.text} ${pStyle.bg}`}
                    >
                      {insight.priority_level} — {pStyle.label}
                    </span>
                    <span className="text-xs font-semibold text-gray-700">
                      {getCompName(insight.competitor_id)}
                    </span>
                    {insight.signal_type && (
                      <span className="text-[10px] bg-gray-100 text-gray-500 px-1.5 py-0.5 rounded">
                        {insight.signal_type}
                      </span>
                    )}
                  </div>
                  {insight.impact_score != null && (
                    <div className="text-right flex-shrink-0">
                      <p className="text-[10px] text-gray-400 uppercase">Impact</p>
                      <p className="text-lg font-bold text-gray-800">
                        {insight.impact_score.toFixed(0)}
                      </p>
                    </div>
                  )}
                </div>

                {/* Signal title */}
                {insight.signal_title && (
                  <p className="text-sm font-medium text-gray-700 mb-2">
                    <AlertTriangle className="h-3.5 w-3.5 inline mr-1 text-amber-500" />
                    {insight.signal_title}
                  </p>
                )}

                {/* Visibility change */}
                <div className="flex items-center gap-4 mb-2">
                  <div className="flex items-center gap-1.5 text-xs">
                    <span className="text-gray-400">Visibility:</span>
                    <span className="font-medium text-gray-600">{insight.visibility_before}</span>
                    <span className="text-gray-400">→</span>
                    <span className="font-medium text-gray-600">{insight.visibility_after}</span>
                    <DeltaIcon className={`h-3.5 w-3.5 ${deltaColor}`} />
                    <span className={`font-medium ${deltaColor}`}>
                      {delta > 0 ? "+" : ""}
                      {delta}
                    </span>
                  </div>
                </div>

                {/* Engines affected */}
                {insight.engines_affected.length > 0 && (
                  <div className="flex items-center gap-1.5 mb-2">
                    <span className="text-[10px] text-gray-400">Engines:</span>
                    {insight.engines_affected.map((eng) => (
                      <span
                        key={eng}
                        className={`text-[10px] font-medium px-1.5 py-0.5 rounded ${
                          ENGINE_BADGE[eng] ?? "bg-gray-100 text-gray-600"
                        }`}
                      >
                        {eng}
                      </span>
                    ))}
                  </div>
                )}

                {/* Prompt */}
                {insight.prompt_text && (
                  <p className="text-[11px] text-gray-500 mb-2 italic">
                    Prompt: &ldquo;{insight.prompt_text}&rdquo;
                  </p>
                )}

                {/* Explanation */}
                {insight.explanation && (
                  <p className="text-xs text-gray-600 leading-relaxed">{insight.explanation}</p>
                )}

                {/* Citations */}
                {insight.citations.length > 0 && (
                  <div className="mt-2 flex flex-wrap gap-2">
                    {insight.citations.slice(0, 3).map((url, i) => (
                      <a
                        key={i}
                        href={url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-[10px] text-violet-600 hover:underline flex items-center gap-0.5"
                      >
                        <ExternalLink className="h-3 w-3" />
                        {url.length > 50 ? url.slice(0, 50) + "…" : url}
                      </a>
                    ))}
                  </div>
                )}

                {/* Timestamp */}
                <p className="text-[10px] text-gray-400 mt-2">
                  {new Date(insight.created_at).toLocaleString()}
                </p>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
