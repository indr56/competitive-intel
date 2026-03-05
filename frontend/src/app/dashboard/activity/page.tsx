"use client";

import { useEffect, useState } from "react";
import { useActiveWorkspace } from "@/lib/hooks";
import { activityFeed } from "@/lib/api";
import type { ActivityFeedItem, SignalType } from "@/lib/types";
import {
  Filter,
  Newspaper,
  Users,
  DollarSign,
  Star,
  Megaphone,
  Globe,
  Tag,
  TrendingUp,
  ExternalLink,
} from "lucide-react";

const SIGNAL_META: Record<
  string,
  { label: string; icon: typeof Globe; color: string; bg: string }
> = {
  website_change: {
    label: "Website Change",
    icon: Globe,
    color: "text-blue-600",
    bg: "bg-blue-50",
  },
  pricing_change: {
    label: "Pricing Change",
    icon: DollarSign,
    color: "text-red-600",
    bg: "bg-red-50",
  },
  product_change: {
    label: "Product Change",
    icon: Tag,
    color: "text-purple-600",
    bg: "bg-purple-50",
  },
  blog_post: {
    label: "Blog Post",
    icon: Newspaper,
    color: "text-emerald-600",
    bg: "bg-emerald-50",
  },
  hiring: {
    label: "Hiring",
    icon: Users,
    color: "text-amber-600",
    bg: "bg-amber-50",
  },
  funding: {
    label: "Funding",
    icon: TrendingUp,
    color: "text-pink-600",
    bg: "bg-pink-50",
  },
  review: {
    label: "Review",
    icon: Star,
    color: "text-yellow-600",
    bg: "bg-yellow-50",
  },
  marketing: {
    label: "Marketing",
    icon: Megaphone,
    color: "text-indigo-600",
    bg: "bg-indigo-50",
  },
};

const SEV_COLORS: Record<string, string> = {
  critical: "bg-red-100 text-red-700 border-red-200",
  high: "bg-orange-100 text-orange-700 border-orange-200",
  medium: "bg-yellow-100 text-yellow-700 border-yellow-200",
  low: "bg-green-100 text-green-700 border-green-200",
};

const SIGNAL_FILTERS: { value: string; label: string }[] = [
  { value: "", label: "All Signals" },
  { value: "blog_post", label: "Blog Posts" },
  { value: "hiring", label: "Hiring" },
  { value: "funding", label: "Funding" },
  { value: "review", label: "Reviews" },
  { value: "marketing", label: "Marketing" },
  { value: "website_change", label: "Website Changes" },
  { value: "pricing_change", label: "Pricing Changes" },
  { value: "product_change", label: "Product Changes" },
];

export default function ActivityFeedPage() {
  const { activeId } = useActiveWorkspace();
  const [items, setItems] = useState<ActivityFeedItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [signalFilter, setSignalFilter] = useState("");

  useEffect(() => {
    if (!activeId) return;
    setLoading(true);
    setError(null);
    activityFeed
      .list(activeId, {
        signal_type: signalFilter || undefined,
        limit: 50,
      })
      .then(setItems)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, [activeId, signalFilter]);

  // Count by signal type for summary badges
  const typeCounts: Record<string, number> = {};
  items.forEach((item) => {
    typeCounts[item.signal_type] = (typeCounts[item.signal_type] || 0) + 1;
  });

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Activity Feed</h1>
          <p className="text-sm text-gray-500 mt-0.5">
            All competitive intelligence signals across your competitors
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Filter className="h-4 w-4 text-gray-400" />
          <select
            value={signalFilter}
            onChange={(e) => setSignalFilter(e.target.value)}
            className="rounded-lg border px-3 py-1.5 text-xs bg-white focus:outline-none focus:ring-2 focus:ring-blue-500"
          >
            {SIGNAL_FILTERS.map((f) => (
              <option key={f.value} value={f.value}>
                {f.label}
              </option>
            ))}
          </select>
        </div>
      </div>

      {/* Signal type summary badges */}
      {!loading && items.length > 0 && (
        <div className="flex flex-wrap gap-2">
          {Object.entries(typeCounts).map(([type, count]) => {
            const meta = SIGNAL_META[type] || SIGNAL_META.website_change;
            const Icon = meta.icon;
            return (
              <button
                key={type}
                onClick={() =>
                  setSignalFilter(signalFilter === type ? "" : type)
                }
                className={`inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-xs font-medium border transition ${
                  signalFilter === type
                    ? "ring-2 ring-blue-400 border-blue-300"
                    : "border-gray-200 hover:border-gray-300"
                } ${meta.bg} ${meta.color}`}
              >
                <Icon className="h-3 w-3" />
                {meta.label}
                <span className="ml-0.5 rounded-full bg-white/60 px-1.5 py-0.5 text-[10px] font-bold">
                  {count}
                </span>
              </button>
            );
          })}
        </div>
      )}

      {/* Error */}
      {error && (
        <div className="rounded-lg bg-red-50 border border-red-200 px-4 py-2 text-sm text-red-700">
          {error}
        </div>
      )}

      {/* Loading skeleton */}
      {loading ? (
        <div className="space-y-3">
          {[1, 2, 3, 4, 5].map((i) => (
            <div
              key={i}
              className="h-24 animate-pulse rounded-xl bg-gray-100"
            />
          ))}
        </div>
      ) : items.length === 0 ? (
        <div className="rounded-xl border bg-white p-12 text-center">
          <Globe className="h-10 w-10 text-gray-300 mx-auto mb-3" />
          <p className="text-gray-500 text-sm">
            No signals detected yet. Signals will appear here as collectors scan
            your competitors&apos; blogs, careers pages, funding news, and
            review platforms.
          </p>
        </div>
      ) : (
        /* Feed cards */
        <div className="space-y-3">
          {items.map((item) => {
            const meta =
              SIGNAL_META[item.signal_type] || SIGNAL_META.website_change;
            const Icon = meta.icon;
            return (
              <div
                key={`${item.source}-${item.id}`}
                className="rounded-xl border bg-white p-5 hover:shadow-sm transition"
              >
                {/* Top row: signal icon, type badge, severity, competitor, date */}
                <div className="flex items-start justify-between mb-2">
                  <div className="flex items-center gap-2.5 flex-wrap">
                    <span
                      className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-semibold ${meta.bg} ${meta.color}`}
                    >
                      <Icon className="h-3 w-3" />
                      {meta.label}
                    </span>
                    {item.severity && (
                      <span
                        className={`text-[10px] font-semibold px-2 py-0.5 rounded-full border ${
                          SEV_COLORS[item.severity] || SEV_COLORS.medium
                        }`}
                      >
                        {item.severity.toUpperCase()}
                      </span>
                    )}
                    {item.competitor_name && (
                      <span className="text-xs text-blue-600 font-medium">
                        {item.competitor_name}
                      </span>
                    )}
                  </div>
                  <span className="text-xs text-gray-400 whitespace-nowrap">
                    {new Date(item.event_time).toLocaleDateString("en-US", {
                      month: "short",
                      day: "numeric",
                      hour: "2-digit",
                      minute: "2-digit",
                    })}
                  </span>
                </div>

                {/* Title */}
                <p className="text-sm font-medium text-gray-900 mb-1">
                  {item.title}
                </p>

                {/* Description */}
                {item.description && (
                  <p className="text-xs text-gray-500 line-clamp-2">
                    {item.description}
                  </p>
                )}

                {/* Source URL link */}
                {item.source_url && (
                  <a
                    href={item.source_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="inline-flex items-center gap-1 mt-2 text-xs text-blue-500 hover:text-blue-700 hover:underline"
                  >
                    <ExternalLink className="h-3 w-3" />
                    View source
                  </a>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
