"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { AlertTriangle, ArrowRight, Filter } from "lucide-react";
import { useActiveWorkspace } from "@/lib/hooks";
import { changes as changesApi, competitors as compApi } from "@/lib/api";
import type { ChangeEvent, Competitor } from "@/lib/types";

const SEVERITY_OPTIONS = ["", "critical", "high", "medium", "low"];
const CATEGORY_OPTIONS = [
  "",
  "pricing_change",
  "plan_restructure",
  "positioning_hero",
  "cta_change",
  "feature_claim",
  "new_alternatives_content",
  "other",
];

const SEV_COLORS: Record<string, string> = {
  critical: "bg-red-50 text-red-700 border-red-200",
  high: "bg-orange-50 text-orange-700 border-orange-200",
  medium: "bg-yellow-50 text-yellow-700 border-yellow-200",
  low: "bg-green-50 text-green-700 border-green-200",
};

export default function ChangeFeedPage() {
  const { activeId } = useActiveWorkspace();
  const [events, setEvents] = useState<ChangeEvent[]>([]);
  const [compsMap, setCompsMap] = useState<Record<string, Competitor>>({});
  const [loading, setLoading] = useState(true);
  const [severity, setSeverity] = useState("");
  const [category, setCategory] = useState("");

  useEffect(() => {
    if (!activeId) return;
    setCompsMap({});
    compApi.list(activeId).then((list) => {
      const map: Record<string, Competitor> = {};
      list.forEach((c) => (map[c.id] = c));
      setCompsMap(map);
    });
  }, [activeId]);

  useEffect(() => {
    if (!activeId) return;
    setLoading(true);
    setEvents([]);
    changesApi
      .list({
        workspace_id: activeId,
        severity: severity || undefined,
        category: category || undefined,
        limit: 50,
      })
      .then(setEvents)
      .catch(console.error)
      .finally(() => setLoading(false));
  }, [activeId, severity, category]);

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-gray-900">Change Feed</h1>
        <div className="flex items-center gap-2">
          <Filter className="h-4 w-4 text-gray-400" />
          <select
            value={severity}
            onChange={(e) => setSeverity(e.target.value)}
            className="rounded-lg border px-2 py-1.5 text-xs bg-white focus:outline-none focus:ring-2 focus:ring-blue-500"
          >
            <option value="">All severities</option>
            {SEVERITY_OPTIONS.filter(Boolean).map((s) => (
              <option key={s} value={s}>
                {s.charAt(0).toUpperCase() + s.slice(1)}
              </option>
            ))}
          </select>
          <select
            value={category}
            onChange={(e) => setCategory(e.target.value)}
            className="rounded-lg border px-2 py-1.5 text-xs bg-white focus:outline-none focus:ring-2 focus:ring-blue-500"
          >
            <option value="">All categories</option>
            {CATEGORY_OPTIONS.filter(Boolean).map((c) => (
              <option key={c} value={c}>
                {c.replace(/_/g, " ")}
              </option>
            ))}
          </select>
        </div>
      </div>

      {loading ? (
        <div className="space-y-3">
          {[1, 2, 3, 4].map((i) => (
            <div key={i} className="h-28 animate-pulse rounded-xl bg-gray-100" />
          ))}
        </div>
      ) : events.length === 0 ? (
        <div className="rounded-xl border bg-white p-12 text-center text-gray-400">
          No changes detected yet. Start tracking competitor pages to see changes here.
        </div>
      ) : (
        <div className="space-y-3">
          {events.map((ce) => {
            const comp = compsMap[ce.competitor_id];
            return (
              <Link
                key={ce.id}
                href={`/dashboard/changes/${ce.id}`}
                className="block rounded-xl border bg-white p-5 hover:shadow-sm transition"
              >
                <div className="flex items-start justify-between mb-2">
                  <div className="flex items-center gap-2.5">
                    <AlertTriangle className="h-4 w-4 text-orange-500 flex-shrink-0" />
                    <span
                      className={`text-[10px] font-semibold px-2 py-0.5 rounded-full border ${
                        SEV_COLORS[ce.severity || "medium"]
                      }`}
                    >
                      {(ce.severity || "medium").toUpperCase()}
                    </span>
                    <div className="flex gap-1">
                      {ce.categories.map((cat) => (
                        <span
                          key={cat}
                          className="text-[10px] bg-gray-100 text-gray-600 px-1.5 py-0.5 rounded-full"
                        >
                          {cat.replace(/_/g, " ")}
                        </span>
                      ))}
                    </div>
                    {comp && (
                      <span className="text-xs text-blue-600 font-medium">
                        {comp.name}
                      </span>
                    )}
                  </div>
                  <div className="flex items-center gap-2">
                    <span className="text-xs text-gray-400">
                      {new Date(ce.created_at).toLocaleDateString()}
                    </span>
                    <ArrowRight className="h-3.5 w-3.5 text-gray-300" />
                  </div>
                </div>
                {ce.ai_summary && (
                  <p className="text-sm text-gray-800 mb-1.5">{ce.ai_summary}</p>
                )}
                {ce.ai_why_it_matters && (
                  <p className="text-xs text-gray-500">
                    <span className="font-medium text-gray-600">
                      Why it matters:
                    </span>{" "}
                    {ce.ai_why_it_matters}
                  </p>
                )}
              </Link>
            );
          })}
        </div>
      )}
    </div>
  );
}
