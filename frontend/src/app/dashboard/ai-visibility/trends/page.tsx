"use client";

import { useState } from "react";
import {
  TrendingUp,
  BarChart3,
  ExternalLink,
  RefreshCw,
  Filter,
} from "lucide-react";
import { useActiveWorkspace, useFetch } from "@/lib/hooks";
import { aiVisibility, competitors as competitorsApi } from "@/lib/api";
import type { Competitor } from "@/lib/types";

const ENGINES = ["chatgpt", "perplexity", "claude", "gemini"];
const ENGINE_COLORS: Record<string, string> = {
  chatgpt: "bg-green-500",
  perplexity: "bg-blue-500",
  claude: "bg-orange-500",
  gemini: "bg-purple-500",
};
const ENGINE_TEXT: Record<string, string> = {
  chatgpt: "text-green-700 bg-green-50",
  perplexity: "text-blue-700 bg-blue-50",
  claude: "text-orange-700 bg-orange-50",
  gemini: "text-purple-700 bg-purple-50",
};
const DAYS_OPTIONS = [7, 14, 30, 60, 90];

export default function VisibilityTrendsPage() {
  const { active, loading: wsLoading } = useActiveWorkspace();
  const wsId = active?.id ?? "";

  const [days, setDays] = useState(30);
  const [selComp, setSelComp] = useState<string>("");
  const [selEngine, setSelEngine] = useState<string>("");

  const { data: comps } = useFetch(
    () => (wsId ? competitorsApi.list(wsId) : Promise.resolve([])),
    [wsId]
  );

  const {
    data: trendsData,
    loading,
    refetch,
  } = useFetch(
    () =>
      wsId
        ? aiVisibility.getTrends(wsId, selComp || undefined, days, selEngine || undefined)
        : Promise.resolve(null),
    [wsId, selComp, days, selEngine]
  );

  if (wsLoading || !active) {
    return <div className="p-8 text-gray-500">Loading workspace…</div>;
  }

  const trends = trendsData?.trends ?? [];
  const breakdown = trendsData?.engines_breakdown ?? {};
  const compSummary = trendsData?.competitor_summary ?? [];
  const citations = trendsData?.citations ?? [];
  const totalMentions = Object.values(breakdown).reduce((a, b) => a + b, 0);

  // Group trends by date for simple chart visualization
  const dateMap = new Map<string, Record<string, { mentions: number; avg_rank: number | null }>>();
  for (const t of trends) {
    if (!dateMap.has(t.date)) dateMap.set(t.date, {});
    dateMap.get(t.date)![t.engine] = { mentions: t.mentions, avg_rank: t.avg_rank };
  }
  const sortedDates = Array.from(dateMap.keys()).sort();

  // Find max mentions for bar scaling
  let maxMentions = 1;
  Array.from(dateMap.values()).forEach((engines) => {
    const total = Object.values(engines).reduce((s, e) => s + e.mentions, 0);
    if (total > maxMentions) maxMentions = total;
  });

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-gray-900 flex items-center gap-2">
            <TrendingUp className="h-5 w-5 text-violet-600" />
            Visibility Trends
          </h1>
          <p className="text-sm text-gray-500 mt-0.5">
            Track how competitors appear across AI engines over time
          </p>
        </div>
        <button
          onClick={refetch}
          className="flex items-center gap-1.5 text-sm text-gray-600 hover:text-gray-900 bg-gray-100 hover:bg-gray-200 rounded-lg px-3 py-2 transition"
        >
          <RefreshCw className="h-3.5 w-3.5" />
          Refresh
        </button>
      </div>

      {/* Filters */}
      <div className="flex flex-wrap items-center gap-3">
        <div className="flex items-center gap-1.5 text-xs text-gray-500">
          <Filter className="h-3.5 w-3.5" />
          Filters:
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
          value={selEngine}
          onChange={(e) => setSelEngine(e.target.value)}
          className="rounded-md border px-2.5 py-1.5 text-xs text-gray-700 focus:outline-none focus:ring-2 focus:ring-violet-300"
        >
          <option value="">All Engines</option>
          {ENGINES.map((e) => (
            <option key={e} value={e}>
              {e.charAt(0).toUpperCase() + e.slice(1)}
            </option>
          ))}
        </select>
        <div className="flex rounded-md border overflow-hidden">
          {DAYS_OPTIONS.map((d) => (
            <button
              key={d}
              onClick={() => setDays(d)}
              className={`px-2.5 py-1.5 text-xs font-medium transition ${
                days === d
                  ? "bg-violet-600 text-white"
                  : "bg-white text-gray-600 hover:bg-gray-50"
              }`}
            >
              {d}d
            </button>
          ))}
        </div>
      </div>

      {loading ? (
        <div className="text-sm text-gray-400 py-8 text-center">Loading trends…</div>
      ) : (
        <>
          {/* Summary cards */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <div className="rounded-xl border bg-white p-4">
              <p className="text-[11px] font-medium text-gray-400 uppercase">Total Mentions</p>
              <p className="text-2xl font-bold text-gray-900 mt-1">{totalMentions}</p>
            </div>
            {ENGINES.map((eng) => (
              <div key={eng} className="rounded-xl border bg-white p-4">
                <p className="text-[11px] font-medium text-gray-400 uppercase">{eng}</p>
                <p className="text-2xl font-bold text-gray-900 mt-1">{breakdown[eng] ?? 0}</p>
              </div>
            ))}
          </div>

          {/* Stacked bar chart */}
          {sortedDates.length > 0 && (
            <div className="rounded-xl border bg-white p-5">
              <h3 className="text-sm font-semibold text-gray-800 mb-4 flex items-center gap-1.5">
                <BarChart3 className="h-4 w-4 text-violet-500" />
                Daily Mentions
              </h3>
              <div className="flex items-end gap-1 h-40">
                {sortedDates.map((date) => {
                  const engData = dateMap.get(date)!;
                  const total = Object.values(engData).reduce((s, e) => s + e.mentions, 0);
                  const heightPct = (total / maxMentions) * 100;
                  return (
                    <div key={date} className="flex-1 flex flex-col items-center group relative">
                      <div
                        className="w-full rounded-t-sm flex flex-col-reverse overflow-hidden"
                        style={{ height: `${Math.max(heightPct, 4)}%` }}
                      >
                        {ENGINES.map((eng) => {
                          const m = engData[eng]?.mentions ?? 0;
                          if (m === 0) return null;
                          const pct = (m / total) * 100;
                          return (
                            <div
                              key={eng}
                              className={`${ENGINE_COLORS[eng]} w-full`}
                              style={{ height: `${pct}%` }}
                            />
                          );
                        })}
                      </div>
                      <span className="text-[9px] text-gray-400 mt-1 hidden md:block">
                        {date.slice(5)}
                      </span>
                      {/* Tooltip */}
                      <div className="absolute bottom-full mb-2 hidden group-hover:block bg-gray-900 text-white text-[10px] rounded px-2 py-1 whitespace-nowrap z-10">
                        {date}: {total} mention{total !== 1 && "s"}
                      </div>
                    </div>
                  );
                })}
              </div>
              {/* Legend */}
              <div className="flex gap-4 mt-3 justify-center">
                {ENGINES.map((eng) => (
                  <div key={eng} className="flex items-center gap-1 text-[10px] text-gray-500">
                    <div className={`w-2.5 h-2.5 rounded-sm ${ENGINE_COLORS[eng]}`} />
                    {eng}
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Competitor ranking table */}
          {compSummary.length > 0 && (
            <div className="rounded-xl border bg-white p-5">
              <h3 className="text-sm font-semibold text-gray-800 mb-3">Competitor Visibility Ranking</h3>
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-[11px] text-gray-400 uppercase border-b">
                    <th className="pb-2 text-left font-medium">#</th>
                    <th className="pb-2 text-left font-medium">Competitor</th>
                    <th className="pb-2 text-right font-medium">Total Mentions</th>
                    <th className="pb-2 text-right font-medium">Avg Rank</th>
                  </tr>
                </thead>
                <tbody>
                  {compSummary.map((c, i) => (
                    <tr key={c.competitor_id} className="border-b last:border-0">
                      <td className="py-2 text-gray-400 font-medium">{i + 1}</td>
                      <td className="py-2 font-medium text-gray-800">{c.competitor_name}</td>
                      <td className="py-2 text-right text-gray-700">{c.total_mentions}</td>
                      <td className="py-2 text-right text-gray-500">{c.avg_rank ?? "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {/* Citations */}
          {citations.length > 0 && (
            <div className="rounded-xl border bg-white p-5">
              <h3 className="text-sm font-semibold text-gray-800 mb-3">Recent Citations</h3>
              <ul className="space-y-2">
                {citations.slice(0, 20).map((c, i) => (
                  <li key={i} className="flex items-center gap-3 text-xs">
                    <span className={`px-1.5 py-0.5 rounded text-[10px] font-medium ${ENGINE_TEXT[c.engine] ?? "bg-gray-100 text-gray-600"}`}>
                      {c.engine}
                    </span>
                    {c.rank_position && (
                      <span className="text-gray-400">#{c.rank_position}</span>
                    )}
                    <a
                      href={c.citation_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-violet-600 hover:underline truncate flex items-center gap-1"
                    >
                      {c.citation_url}
                      <ExternalLink className="h-3 w-3 flex-shrink-0" />
                    </a>
                    <span className="text-gray-400 ml-auto flex-shrink-0">{c.event_date}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* Empty state */}
          {totalMentions === 0 && sortedDates.length === 0 && (
            <div className="rounded-xl border bg-white p-8 text-center">
              <TrendingUp className="h-10 w-10 text-gray-300 mx-auto mb-3" />
              <p className="text-sm text-gray-500">
                No visibility data yet. Run your tracked prompts to start collecting trend data.
              </p>
            </div>
          )}
        </>
      )}
    </div>
  );
}
