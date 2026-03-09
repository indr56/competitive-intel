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
  X,
  Shield,
  Eye,
  EyeOff,
  Crown,
  TrendingUp,
  ChevronRight,
} from "lucide-react";
import { useActiveWorkspace, useFetch } from "@/lib/hooks";
import { aiVisibility, competitors as competitorsApi } from "@/lib/api";
import type { AIInsightCompact, AIInsightDetail } from "@/lib/types";

const PRIORITY_STYLES: Record<string, { bg: string; text: string; border: string; label: string }> = {
  P0: { bg: "bg-red-50", text: "text-red-700", border: "border-red-200", label: "Critical" },
  P1: { bg: "bg-amber-50", text: "text-amber-700", border: "border-amber-200", label: "High" },
  P2: { bg: "bg-blue-50", text: "text-blue-700", border: "border-blue-200", label: "Medium" },
  P3: { bg: "bg-gray-50", text: "text-gray-500", border: "border-gray-200", label: "Low" },
};

const ENGINE_BADGE: Record<string, string> = {
  chatgpt: "bg-green-100 text-green-700",
  perplexity: "bg-blue-100 text-blue-700",
  claude: "bg-orange-100 text-orange-700",
  gemini: "bg-purple-100 text-purple-700",
};

const INSIGHT_TYPE_META: Record<string, { icon: typeof Lightbulb; color: string; label: string }> = {
  ai_impact: { icon: TrendingUp, color: "text-violet-600 bg-violet-50", label: "AI Impact" },
  ai_visibility_hijack: { icon: Eye, color: "text-emerald-600 bg-emerald-50", label: "Visibility Hijack" },
  ai_visibility_loss: { icon: EyeOff, color: "text-red-600 bg-red-50", label: "Visibility Loss" },
  ai_dominance: { icon: Crown, color: "text-amber-600 bg-amber-50", label: "AI Dominance" },
};

export default function AIImpactInsightsPage() {
  const { active, loading: wsLoading } = useActiveWorkspace();
  const wsId = active?.id ?? "";

  const [selComp, setSelComp] = useState("");
  const [selPriority, setSelPriority] = useState("");
  const [selType, setSelType] = useState("");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");
  const [detail, setDetail] = useState<AIInsightDetail | null>(null);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [drawerLoading, setDrawerLoading] = useState(false);

  const { data: comps } = useFetch(
    () => (wsId ? competitorsApi.list(wsId) : Promise.resolve([])),
    [wsId]
  );

  const {
    data: cards,
    loading,
    refetch,
  } = useFetch(
    () =>
      wsId
        ? aiVisibility.listInsightsCompact(
            wsId,
            selComp || undefined,
            selPriority || undefined,
            selType || undefined,
          )
        : Promise.resolve([]),
    [wsId, selComp, selPriority, selType]
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

  const openDetail = async (insightId: string) => {
    setDrawerOpen(true);
    setDrawerLoading(true);
    try {
      const d = await aiVisibility.getInsightDetail(wsId, insightId);
      setDetail(d);
    } catch {
      setDetail(null);
    }
    setDrawerLoading(false);
  };

  const items = cards ?? [];
  const p0Count = items.filter((i) => i.priority === "P0").length;
  const p1Count = items.filter((i) => i.priority === "P1").length;
  const hijackCount = items.filter((i) => i.insight_type === "ai_visibility_hijack").length;
  const dominanceCount = items.filter((i) => i.insight_type === "ai_dominance").length;

  return (
    <div className="space-y-6 relative">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-gray-900 flex items-center gap-2">
            <Lightbulb className="h-5 w-5 text-violet-600" />
            AI Impact Insights
          </h1>
          <p className="text-sm text-gray-500 mt-0.5">
            Intelligence from competitor signals and AI visibility changes
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
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <div className="rounded-xl border bg-white p-4">
          <p className="text-[11px] font-medium text-gray-400 uppercase">Total</p>
          <p className="text-2xl font-bold text-gray-900 mt-1">{items.length}</p>
        </div>
        <div className="rounded-xl border border-red-100 bg-red-50/30 p-4">
          <p className="text-[11px] font-medium text-red-400 uppercase">Critical (P0)</p>
          <p className="text-2xl font-bold text-red-700 mt-1">{p0Count}</p>
        </div>
        <div className="rounded-xl border border-emerald-100 bg-emerald-50/30 p-4">
          <p className="text-[11px] font-medium text-emerald-500 uppercase">Hijacks</p>
          <p className="text-2xl font-bold text-emerald-700 mt-1">{hijackCount}</p>
        </div>
        <div className="rounded-xl border border-amber-100 bg-amber-50/30 p-4">
          <p className="text-[11px] font-medium text-amber-500 uppercase">Dominance</p>
          <p className="text-2xl font-bold text-amber-700 mt-1">{dominanceCount}</p>
        </div>
      </div>

      {/* Filters */}
      <div className="flex flex-wrap items-center gap-3">
        <div className="flex items-center gap-1.5 text-xs text-gray-500">
          <Filter className="h-3.5 w-3.5" />
        </div>
        <select value={selComp} onChange={(e) => setSelComp(e.target.value)}
          className="rounded-md border px-2.5 py-1.5 text-xs text-gray-700 focus:outline-none focus:ring-2 focus:ring-violet-300">
          <option value="">All Competitors</option>
          {(comps ?? []).map((c) => (<option key={c.id} value={c.id}>{c.name}</option>))}
        </select>
        <select value={selPriority} onChange={(e) => setSelPriority(e.target.value)}
          className="rounded-md border px-2.5 py-1.5 text-xs text-gray-700 focus:outline-none focus:ring-2 focus:ring-violet-300">
          <option value="">All Priorities</option>
          <option value="P0">P0 — Critical</option>
          <option value="P1">P1 — High</option>
          <option value="P2">P2 — Medium</option>
          <option value="P3">P3 — Low</option>
        </select>
        <select value={selType} onChange={(e) => setSelType(e.target.value)}
          className="rounded-md border px-2.5 py-1.5 text-xs text-gray-700 focus:outline-none focus:ring-2 focus:ring-violet-300">
          <option value="">All Types</option>
          <option value="ai_impact">AI Impact</option>
          <option value="ai_visibility_hijack">Visibility Hijack</option>
          <option value="ai_visibility_loss">Visibility Loss</option>
          <option value="ai_dominance">AI Dominance</option>
        </select>
      </div>

      {/* Compact Insight Cards */}
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
          {items.map((card) => (
            <CompactInsightCard key={card.insight_id} card={card} onOpen={openDetail} />
          ))}
        </div>
      )}

      {/* Detail Drawer */}
      {drawerOpen && (
        <InsightDetailDrawer
          detail={detail}
          loading={drawerLoading}
          onClose={() => { setDrawerOpen(false); setDetail(null); }}
        />
      )}
    </div>
  );
}


/* ═══════════════════════════════════════════════════
   Compact Insight Card (Level 1)
   ═══════════════════════════════════════════════════ */

function CompactInsightCard({ card, onOpen }: { card: AIInsightCompact; onOpen: (id: string) => void }) {
  const pStyle = PRIORITY_STYLES[card.priority] ?? PRIORITY_STYLES.P3;
  const typeMeta = INSIGHT_TYPE_META[card.insight_type] ?? INSIGHT_TYPE_META.ai_impact;
  const TypeIcon = typeMeta.icon;
  const delta = card.visibility_delta;
  const DeltaIcon = delta > 0 ? ArrowUpRight : delta < 0 ? ArrowDownRight : Minus;
  const deltaColor = delta > 0 ? "text-green-600" : delta < 0 ? "text-red-600" : "text-gray-400";

  return (
    <button
      onClick={() => onOpen(card.insight_id)}
      className={`w-full text-left rounded-xl border ${pStyle.border} ${pStyle.bg} p-4 hover:shadow-md transition-shadow cursor-pointer`}
    >
      {/* Row 1: Type badge + Priority + Competitor + Signal */}
      <div className="flex items-center justify-between gap-2 mb-2">
        <div className="flex items-center gap-2 min-w-0">
          <span className={`inline-flex items-center gap-1 text-[10px] font-semibold px-2 py-0.5 rounded-full ${typeMeta.color}`}>
            <TypeIcon className="h-3 w-3" />
            {typeMeta.label}
          </span>
          <span className={`text-[10px] font-bold px-1.5 py-0.5 rounded-full border ${pStyle.text} ${pStyle.border}`}>
            {card.priority} — {pStyle.label}
          </span>
          <span className="text-xs font-semibold text-gray-800 truncate">
            {card.competitor_name}
          </span>
          {card.signal_type && card.signal_type !== card.insight_type && (
            <span className="text-[10px] bg-gray-100 text-gray-500 px-1.5 py-0.5 rounded hidden sm:inline">
              {card.signal_type.replace(/_/g, " ")}
            </span>
          )}
        </div>
        <div className="flex items-center gap-3 flex-shrink-0">
          {card.impact_score != null && (
            <div className="text-right">
              <p className="text-[9px] text-gray-400 uppercase leading-none">Impact</p>
              <p className="text-base font-bold text-gray-800">{card.impact_score.toFixed(0)}</p>
            </div>
          )}
          <ChevronRight className="h-4 w-4 text-gray-300" />
        </div>
      </div>

      {/* Row 2: Short title */}
      {card.short_title && (
        <p className="text-sm font-medium text-gray-700 mb-1.5 truncate">{card.short_title}</p>
      )}

      {/* Row 3: Visibility + Engines + Confidence */}
      <div className="flex items-center gap-4 text-xs">
        <span className="text-gray-400">Visibility:</span>
        <span className="font-medium text-gray-600">{card.visibility_before}</span>
        <span className="text-gray-400">→</span>
        <span className="font-medium text-gray-600">{card.visibility_after}</span>
        <DeltaIcon className={`h-3.5 w-3.5 ${deltaColor}`} />
        <span className={`font-medium ${deltaColor}`}>
          {delta > 0 ? "+" : ""}{delta}
        </span>
        <span className="text-gray-300">|</span>
        <span className="text-gray-400">Engines:</span>
        <span className="text-gray-600 font-medium">{card.engine_summary}</span>
        {card.correlation_confidence != null && (
          <>
            <span className="text-gray-300">|</span>
            <span className="text-gray-400">Confidence:</span>
            <span className="font-medium text-gray-600">{card.correlation_confidence}%</span>
          </>
        )}
      </div>

      {/* Row 4: Summary */}
      {card.summary_text && (
        <p className="text-[11px] text-gray-500 mt-2 line-clamp-2 leading-relaxed">{card.summary_text}</p>
      )}

      {/* Timestamp */}
      <p className="text-[10px] text-gray-400 mt-2">{new Date(card.timestamp).toLocaleString()}</p>
    </button>
  );
}


/* ═══════════════════════════════════════════════════
   Expanded Insight Detail Drawer (Level 2)
   ═══════════════════════════════════════════════════ */

function InsightDetailDrawer({
  detail,
  loading,
  onClose,
}: {
  detail: AIInsightDetail | null;
  loading: boolean;
  onClose: () => void;
}) {
  return (
    <>
      {/* Overlay */}
      <div className="fixed inset-0 bg-black/20 z-40" onClick={onClose} />

      {/* Drawer */}
      <div className="fixed right-0 top-0 h-full w-full max-w-xl bg-white shadow-2xl z-50 overflow-y-auto border-l">
        {/* Header */}
        <div className="sticky top-0 bg-white border-b px-6 py-4 flex items-center justify-between z-10">
          <h2 className="text-base font-bold text-gray-900">Insight Detail</h2>
          <button onClick={onClose} className="p-1 rounded-lg hover:bg-gray-100 transition">
            <X className="h-5 w-5 text-gray-500" />
          </button>
        </div>

        {loading ? (
          <div className="p-8 text-center text-gray-400 text-sm">Loading detail…</div>
        ) : !detail ? (
          <div className="p-8 text-center text-gray-400 text-sm">Insight not found.</div>
        ) : (
          <div className="p-6 space-y-6">
            <DetailContent detail={detail} />
          </div>
        )}
      </div>
    </>
  );
}

function DetailContent({ detail: d }: { detail: AIInsightDetail }) {
  const pStyle = PRIORITY_STYLES[d.priority] ?? PRIORITY_STYLES.P3;
  const typeMeta = INSIGHT_TYPE_META[d.insight_type] ?? INSIGHT_TYPE_META.ai_impact;
  const TypeIcon = typeMeta.icon;
  const delta = d.visibility_delta;
  const deltaColor = delta > 0 ? "text-green-600" : delta < 0 ? "text-red-600" : "text-gray-400";

  return (
    <>
      {/* A. Header */}
      <div>
        <div className="flex items-center gap-2 mb-2">
          <span className={`inline-flex items-center gap-1 text-[10px] font-semibold px-2 py-0.5 rounded-full ${typeMeta.color}`}>
            <TypeIcon className="h-3 w-3" />
            {typeMeta.label}
          </span>
          <span className={`text-[10px] font-bold px-1.5 py-0.5 rounded-full border ${pStyle.text} ${pStyle.border}`}>
            {d.priority} — {pStyle.label}
          </span>
        </div>
        <h3 className="text-lg font-bold text-gray-900">{d.competitor_name}</h3>
        <div className="flex items-center gap-4 mt-1 text-xs text-gray-500">
          {d.impact_score != null && <span>Impact: <strong className="text-gray-800">{d.impact_score.toFixed(0)}</strong></span>}
          {d.correlation_confidence != null && (
            <span className="flex items-center gap-1">
              <Shield className="h-3 w-3" />
              Confidence: <strong className="text-gray-800">{d.correlation_confidence}%</strong>
            </span>
          )}
          <span>{new Date(d.timestamp).toLocaleString()}</span>
        </div>
      </div>

      {/* B. Signal Context */}
      {d.signal_title && (
        <Section title="Signal Context">
          <div className="flex items-start gap-2">
            <AlertTriangle className="h-4 w-4 text-amber-500 mt-0.5 flex-shrink-0" />
            <div>
              <p className="text-sm font-medium text-gray-700">{d.signal_title}</p>
              {d.signal_type && (
                <p className="text-xs text-gray-400 mt-0.5">Type: {d.signal_type.replace(/_/g, " ")}</p>
              )}
              {d.signal_timestamp && (
                <p className="text-xs text-gray-400">Signal time: {new Date(d.signal_timestamp).toLocaleString()}</p>
              )}
            </div>
          </div>
        </Section>
      )}

      {/* C. Prompt Context */}
      {d.prompt_text && (
        <Section title="Prompt Context">
          <p className="text-sm text-gray-700 italic">&ldquo;{d.prompt_text}&rdquo;</p>
          {d.prompt_cluster_name && (
            <p className="text-xs text-gray-400 mt-1">Cluster: <strong>{d.prompt_cluster_name}</strong></p>
          )}
          {d.prompt_source && (
            <p className="text-xs text-gray-400">Source: {d.prompt_source}</p>
          )}
        </Section>
      )}

      {/* D. Visibility Change */}
      <Section title="Visibility Change">
        <div className="grid grid-cols-3 gap-3 text-center">
          <div className="rounded-lg bg-gray-50 p-3">
            <p className="text-[10px] text-gray-400 uppercase">Previous</p>
            <p className="text-xl font-bold text-gray-800">{d.visibility_before}</p>
          </div>
          <div className="rounded-lg bg-gray-50 p-3">
            <p className="text-[10px] text-gray-400 uppercase">Current</p>
            <p className="text-xl font-bold text-gray-800">{d.visibility_after}</p>
          </div>
          <div className={`rounded-lg p-3 ${delta > 0 ? "bg-green-50" : delta < 0 ? "bg-red-50" : "bg-gray-50"}`}>
            <p className="text-[10px] text-gray-400 uppercase">Delta</p>
            <p className={`text-xl font-bold ${deltaColor}`}>
              {delta > 0 ? "+" : ""}{delta}
            </p>
          </div>
        </div>
        {d.engines_detected.length > 0 && (
          <div className="flex items-center gap-1.5 mt-3">
            <span className="text-[10px] text-gray-400">Engines:</span>
            {d.engines_detected.map((eng) => (
              <span key={eng} className={`text-[10px] font-medium px-1.5 py-0.5 rounded ${ENGINE_BADGE[eng] ?? "bg-gray-100 text-gray-600"}`}>
                {eng}
              </span>
            ))}
          </div>
        )}
        {d.engine_breakdown && Object.keys(d.engine_breakdown).length > 0 && (
          <div className="mt-3 space-y-1">
            {Object.entries(d.engine_breakdown).map(([eng, data]) => (
              <div key={eng} className="flex items-center gap-2 text-xs text-gray-600">
                <span className={`font-medium px-1.5 py-0.5 rounded ${ENGINE_BADGE[eng] ?? "bg-gray-100"}`}>{eng}</span>
                {data.rank != null && <span>Rank #{data.rank}</span>}
                {data.citation_url && (
                  <a href={data.citation_url} target="_blank" rel="noopener noreferrer" className="text-violet-600 hover:underline flex items-center gap-0.5">
                    <ExternalLink className="h-3 w-3" />{data.citation_url.length > 40 ? data.citation_url.slice(0, 40) + "…" : data.citation_url}
                  </a>
                )}
              </div>
            ))}
          </div>
        )}
      </Section>

      {/* E. Citations */}
      {Object.keys(d.citations).length > 0 && (
        <Section title="Citations">
          {Object.entries(d.citations).map(([eng, urls]) => (
            <div key={eng} className="mb-2">
              <p className="text-[10px] text-gray-400 uppercase mb-1">{eng}</p>
              {urls.map((url, i) => (
                <a key={i} href={url} target="_blank" rel="noopener noreferrer"
                  className="text-xs text-violet-600 hover:underline flex items-center gap-0.5 mb-0.5">
                  <ExternalLink className="h-3 w-3" />
                  {url.length > 60 ? url.slice(0, 60) + "…" : url}
                </a>
              ))}
            </div>
          ))}
        </Section>
      )}

      {/* F. Reasoning */}
      {d.reasoning && (
        <Section title="Why This Matters">
          <p className="text-sm text-gray-700 leading-relaxed">{d.reasoning}</p>
        </Section>
      )}

      {/* G. Supporting Evidence */}
      {(d.previous_mentions.length > 0 || d.current_mentions.length > 0) && (
        <Section title="Supporting Evidence">
          <div className="grid grid-cols-2 gap-3">
            <div>
              <p className="text-[10px] text-gray-400 uppercase mb-1">Previous Results</p>
              {d.previous_mentions.length > 0 ? (
                <ul className="text-xs text-gray-600 space-y-0.5">
                  {d.previous_mentions.slice(0, 10).map((b, i) => <li key={i}>{b}</li>)}
                </ul>
              ) : (
                <p className="text-xs text-gray-400 italic">None</p>
              )}
            </div>
            <div>
              <p className="text-[10px] text-gray-400 uppercase mb-1">Current Results</p>
              {d.current_mentions.length > 0 ? (
                <ul className="text-xs text-gray-600 space-y-0.5">
                  {d.current_mentions.slice(0, 10).map((b, i) => <li key={i}>{b}</li>)}
                </ul>
              ) : (
                <p className="text-xs text-gray-400 italic">None</p>
              )}
            </div>
          </div>
        </Section>
      )}

      {/* H. Actions */}
      <Section title="Actions">
        <div className="flex flex-wrap gap-2">
          {d.actions.view_signal && (
            <ActionButton label="View Signal" href={d.actions.view_signal} />
          )}
          {d.actions.view_prompt_analytics && (
            <ActionButton label="View Prompt Analytics" href={d.actions.view_prompt_analytics} />
          )}
          {d.actions.view_competitor_timeline && (
            <ActionButton label="View Competitor Timeline" href={d.actions.view_competitor_timeline} />
          )}
        </div>
      </Section>
    </>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div>
      <h4 className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-2">{title}</h4>
      {children}
    </div>
  );
}

function ActionButton({ label, href }: { label: string; href: string }) {
  return (
    <a href={href}
      className="inline-flex items-center gap-1 text-xs font-medium text-violet-600 border border-violet-200 rounded-lg px-3 py-1.5 hover:bg-violet-50 transition">
      {label}
      <ChevronRight className="h-3 w-3" />
    </a>
  );
}
