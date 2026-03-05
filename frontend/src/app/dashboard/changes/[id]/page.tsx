"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import {
  ArrowLeft,
  Brain,
  Copy,
  Check,
  RefreshCw,
  Sparkles,
  FileText,
} from "lucide-react";
import {
  changes as changesApi,
  insights as insightsApi,
  competitors as compApi,
} from "@/lib/api";
import type { ChangeEvent, Insight, Competitor } from "@/lib/types";

const SEV_COLORS: Record<string, string> = {
  critical: "bg-red-50 text-red-700",
  high: "bg-orange-50 text-orange-700",
  medium: "bg-yellow-50 text-yellow-700",
  low: "bg-green-50 text-green-700",
};

export default function ChangeDetailPage() {
  const params = useParams();
  const id = params.id as string;
  const [change, setChange] = useState<ChangeEvent | null>(null);
  const [comp, setComp] = useState<Competitor | null>(null);
  const [insightsList, setInsights] = useState<Insight[]>([]);
  const [loading, setLoading] = useState(true);
  const [generating, setGenerating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState<string | null>(null);

  useEffect(() => {
    setLoading(true);
    changesApi
      .get(id)
      .then(async (ce) => {
        setChange(ce);
        const [ins, competitor] = await Promise.all([
          insightsApi.listForEvent(ce.id).catch(() => []),
          compApi.get(ce.competitor_id).catch(() => null),
        ]);
        setInsights(ins);
        setComp(competitor);
      })
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, [id]);

  const handleGenerate = async (types?: string[]) => {
    if (!change) return;
    setGenerating(true);
    try {
      const newInsights = await insightsApi.generate(change.id, {
        insight_types: types,
      });
      setInsights((prev) => [...newInsights, ...prev]);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setGenerating(false);
    }
  };

  const handleCopy = (text: string, label: string) => {
    navigator.clipboard.writeText(text);
    setCopied(label);
    setTimeout(() => setCopied(null), 2000);
  };

  if (loading) {
    return (
      <div className="space-y-4">
        <div className="h-8 w-64 animate-pulse rounded bg-gray-100" />
        <div className="h-96 animate-pulse rounded-xl bg-gray-100" />
      </div>
    );
  }

  if (!change) {
    return (
      <div className="text-center text-red-500 py-16">
        {error || "Change event not found."}
      </div>
    );
  }

  const sev = change.severity ?? "medium";

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center gap-3">
        <Link
          href="/dashboard/changes"
          className="rounded-lg border p-1.5 text-gray-400 hover:text-gray-600 hover:bg-gray-50 transition"
        >
          <ArrowLeft className="h-4 w-4" />
        </Link>
        <div>
          <h1 className="text-xl font-bold text-gray-900">Change Detail</h1>
          <div className="flex items-center gap-2 mt-1">
            <span
              className={`text-[10px] font-semibold px-2 py-0.5 rounded-full ${SEV_COLORS[sev]}`}
            >
              {sev.toUpperCase()}
            </span>
            {change.categories.map((cat) => (
              <span
                key={cat}
                className="text-[10px] bg-gray-100 text-gray-600 px-1.5 py-0.5 rounded-full"
              >
                {cat.replace(/_/g, " ")}
              </span>
            ))}
            {comp && (
              <span className="text-xs text-blue-600 font-medium">
                {comp.name}
              </span>
            )}
            <span className="text-xs text-gray-400">
              {new Date(change.created_at).toLocaleString()}
            </span>
          </div>
        </div>
      </div>

      {error && (
        <div className="rounded-lg bg-red-50 border border-red-200 px-4 py-2 text-sm text-red-700">
          {error}
        </div>
      )}

      {/* AI Summary Panel */}
      <div className="rounded-xl border bg-white overflow-hidden">
        <div className="bg-gradient-to-r from-purple-50 to-blue-50 px-5 py-3 border-b flex items-center gap-2">
          <Brain className="h-4 w-4 text-purple-600" />
          <span className="text-sm font-semibold text-gray-800">
            AI Classification Summary
          </span>
        </div>
        <div className="p-5 space-y-4">
          {change.ai_summary && (
            <Section
              title="Summary"
              text={change.ai_summary}
              onCopy={() => handleCopy(change.ai_summary!, "summary")}
              copied={copied === "summary"}
            />
          )}
          {change.ai_why_it_matters && (
            <Section
              title="Why It Matters"
              text={change.ai_why_it_matters}
              onCopy={() =>
                handleCopy(change.ai_why_it_matters!, "why")
              }
              copied={copied === "why"}
            />
          )}
          {change.ai_next_moves && (
            <Section
              title="Next Moves"
              text={change.ai_next_moves}
              onCopy={() => handleCopy(change.ai_next_moves!, "moves")}
              copied={copied === "moves"}
            />
          )}
          {change.ai_battlecard_block && (
            <Section
              title="Battlecard Block"
              text={change.ai_battlecard_block}
              onCopy={() =>
                handleCopy(change.ai_battlecard_block!, "battlecard")
              }
              copied={copied === "battlecard"}
            />
          )}
          {change.ai_sales_talk_track && (
            <Section
              title="Sales Talk Track"
              text={change.ai_sales_talk_track}
              onCopy={() =>
                handleCopy(change.ai_sales_talk_track!, "talk")
              }
              copied={copied === "talk"}
            />
          )}
        </div>
      </div>

      {/* Structured Insights */}
      <div className="rounded-xl border bg-white overflow-hidden">
        <div className="bg-gradient-to-r from-green-50 to-emerald-50 px-5 py-3 border-b flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Sparkles className="h-4 w-4 text-emerald-600" />
            <span className="text-sm font-semibold text-gray-800">
              AI Insights ({insightsList.length})
            </span>
          </div>
          <div className="flex gap-1.5">
            <button
              onClick={() => handleGenerate(["change_analysis"])}
              disabled={generating}
              className="inline-flex items-center gap-1 rounded-lg border bg-white px-2.5 py-1 text-xs text-gray-600 hover:bg-gray-50 disabled:opacity-50 transition"
            >
              <RefreshCw
                className={`h-3 w-3 ${generating ? "animate-spin" : ""}`}
              />
              Analysis
            </button>
            <button
              onClick={() => handleGenerate(["battlecard"])}
              disabled={generating}
              className="inline-flex items-center gap-1 rounded-lg border bg-white px-2.5 py-1 text-xs text-gray-600 hover:bg-gray-50 disabled:opacity-50 transition"
            >
              <FileText className="h-3 w-3" />
              Battlecard
            </button>
          </div>
        </div>

        {insightsList.length === 0 ? (
          <div className="p-8 text-center text-sm text-gray-400">
            No insights generated yet. Click a button above to generate.
          </div>
        ) : (
          <div className="divide-y">
            {insightsList.map((ins) => (
              <InsightCard
                key={ins.id}
                insight={ins}
                onCopy={handleCopy}
                copied={copied}
              />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function Section({
  title,
  text,
  onCopy,
  copied,
}: {
  title: string;
  text: string;
  onCopy: () => void;
  copied: boolean;
}) {
  return (
    <div>
      <div className="flex items-center justify-between mb-1">
        <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wide">
          {title}
        </h3>
        <button
          onClick={onCopy}
          className="text-gray-400 hover:text-gray-600 transition p-0.5"
        >
          {copied ? (
            <Check className="h-3.5 w-3.5 text-green-500" />
          ) : (
            <Copy className="h-3.5 w-3.5" />
          )}
        </button>
      </div>
      <p className="text-sm text-gray-700 leading-relaxed">{text}</p>
    </div>
  );
}

function InsightCard({
  insight,
  onCopy,
  copied,
}: {
  insight: Insight;
  onCopy: (text: string, label: string) => void;
  copied: string | null;
}) {
  const [expanded, setExpanded] = useState(false);
  const content = insight.content as Record<string, unknown>;
  const summary =
    (content.summary as string) ||
    (content.competitor_positioning as string) ||
    (content.headline as string) ||
    (content.talk_track as string) ||
    "";

  return (
    <div className="p-4">
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2">
          <span className="text-xs font-semibold bg-purple-50 text-purple-700 px-2 py-0.5 rounded-full">
            {insight.insight_type.replace(/_/g, " ")}
          </span>
          <span className="text-[10px] text-gray-400">
            v{insight.version}
          </span>
          {insight.is_grounded && (
            <span className="text-[10px] bg-green-50 text-green-600 px-1.5 py-0.5 rounded-full">
              grounded
            </span>
          )}
          {insight.cost_usd != null && (
            <span className="text-[10px] text-gray-400">
              ${insight.cost_usd.toFixed(4)}
            </span>
          )}
        </div>
        <div className="flex items-center gap-1">
          <button
            onClick={() =>
              onCopy(JSON.stringify(content, null, 2), insight.id)
            }
            className="p-1 text-gray-400 hover:text-gray-600 transition"
          >
            {copied === insight.id ? (
              <Check className="h-3.5 w-3.5 text-green-500" />
            ) : (
              <Copy className="h-3.5 w-3.5" />
            )}
          </button>
        </div>
      </div>
      {summary && (
        <p className="text-sm text-gray-700 mb-2 line-clamp-3">{summary}</p>
      )}
      <button
        onClick={() => setExpanded(!expanded)}
        className="text-xs text-blue-600 hover:underline"
      >
        {expanded ? "Collapse" : "View full JSON"}
      </button>
      {expanded && (
        <pre className="mt-2 rounded-lg bg-gray-50 p-3 text-xs text-gray-600 overflow-x-auto max-h-80">
          {JSON.stringify(content, null, 2)}
        </pre>
      )}
    </div>
  );
}
