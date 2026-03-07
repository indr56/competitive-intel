"use client";

import { useEffect, useState } from "react";
import { useActiveWorkspace } from "@/lib/hooks";
import { activityFeed, events as eventsApi, competitors as compApi } from "@/lib/api";
import type { ActivityFeedItem, Competitor } from "@/lib/types";
import Link from "next/link";
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
  Plus,
  X,
  ChevronRight,
  MessageSquare,
  Plug,
  PlugZap,
  FileText,
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
  positioning_change: {
    label: "Positioning",
    icon: MessageSquare,
    color: "text-cyan-600",
    bg: "bg-cyan-50",
  },
  integration_added: {
    label: "Integration Added",
    icon: Plug,
    color: "text-teal-600",
    bg: "bg-teal-50",
  },
  integration_removed: {
    label: "Integration Removed",
    icon: PlugZap,
    color: "text-rose-600",
    bg: "bg-rose-50",
  },
  landing_page_created: {
    label: "Landing Page",
    icon: FileText,
    color: "text-violet-600",
    bg: "bg-violet-50",
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
  { value: "positioning_change", label: "Positioning Changes" },
  { value: "integration_added", label: "Integrations Added" },
  { value: "integration_removed", label: "Integrations Removed" },
  { value: "landing_page_created", label: "Landing Pages" },
];

export default function ActivityFeedPage() {
  const { activeId } = useActiveWorkspace();
  const [items, setItems] = useState<ActivityFeedItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [signalFilter, setSignalFilter] = useState("");
  const [refreshKey, setRefreshKey] = useState(0);

  // Competitors for the form
  const [competitors, setCompetitors] = useState<Competitor[]>([]);
  useEffect(() => {
    if (!activeId) return;
    compApi.list(activeId).then(setCompetitors).catch(() => {});
  }, [activeId]);

  // Form state
  const [showForm, setShowForm] = useState(false);
  const [formComp, setFormComp] = useState("");
  const [formSignal, setFormSignal] = useState("blog_post");
  const [formSeverity, setFormSeverity] = useState("medium");
  const [formTitle, setFormTitle] = useState("");
  const [formDesc, setFormDesc] = useState("");
  const [formUrl, setFormUrl] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [formSuccess, setFormSuccess] = useState<string | null>(null);

  const resetForm = () => {
    setFormTitle("");
    setFormDesc("");
    setFormUrl("");
    setFormError(null);
    setFormSuccess(null);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!activeId || !formComp) return;
    setFormError(null);
    setFormSuccess(null);
    setSubmitting(true);
    try {
      await eventsApi.create(activeId, formComp, {
        signal_type: formSignal,
        title: formTitle,
        description: formDesc || undefined,
        source_url: formUrl || undefined,
        severity: formSeverity,
      });
      setFormSuccess("Signal reported! It now appears in the feed.");
      setFormTitle("");
      setFormDesc("");
      setFormUrl("");
      setRefreshKey((k) => k + 1); // trigger feed reload
    } catch (err: any) {
      setFormError(err.message || "Failed to create signal");
    } finally {
      setSubmitting(false);
    }
  };

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
  }, [activeId, signalFilter, refreshKey]);

  // Count by signal type for summary badges
  const typeCounts: Record<string, number> = {};
  items.forEach((item) => {
    typeCounts[item.signal_type] = (typeCounts[item.signal_type] || 0) + 1;
  });

  // Set default competitor when competitors load
  useEffect(() => {
    if (competitors.length > 0 && !formComp) {
      setFormComp(competitors[0].id);
    }
  }, [competitors, formComp]);

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
        <div className="flex items-center gap-3">
          <button
            onClick={() => { setShowForm(!showForm); resetForm(); }}
            className="inline-flex items-center gap-1.5 rounded-lg bg-blue-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-blue-700 transition"
          >
            {showForm ? <X className="h-3.5 w-3.5" /> : <Plus className="h-3.5 w-3.5" />}
            {showForm ? "Cancel" : "Report Signal"}
          </button>
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
      </div>

      {/* Report Signal Form */}
      {showForm && (
        <form
          onSubmit={handleSubmit}
          className="rounded-xl border-2 border-blue-200 bg-blue-50/50 p-5 space-y-4"
        >
          <h2 className="text-sm font-semibold text-gray-900">Report a Competitive Signal</h2>

          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
            {/* Competitor */}
            <div>
              <label className="block text-xs font-medium text-gray-700 mb-1">
                Competitor *
              </label>
              <select
                value={formComp}
                onChange={(e) => setFormComp(e.target.value)}
                required
                className="w-full rounded-lg border px-3 py-2 text-sm bg-white focus:outline-none focus:ring-2 focus:ring-blue-500"
              >
                <option value="">Select competitor…</option>
                {competitors.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.name} ({c.domain})
                  </option>
                ))}
              </select>
            </div>

            {/* Signal Type */}
            <div>
              <label className="block text-xs font-medium text-gray-700 mb-1">
                Signal Type *
              </label>
              <select
                value={formSignal}
                onChange={(e) => setFormSignal(e.target.value)}
                className="w-full rounded-lg border px-3 py-2 text-sm bg-white focus:outline-none focus:ring-2 focus:ring-blue-500"
              >
                {SIGNAL_FILTERS.filter((f) => f.value).map((f) => (
                  <option key={f.value} value={f.value}>
                    {f.label}
                  </option>
                ))}
              </select>
            </div>

            {/* Severity */}
            <div>
              <label className="block text-xs font-medium text-gray-700 mb-1">
                Severity *
              </label>
              <select
                value={formSeverity}
                onChange={(e) => setFormSeverity(e.target.value)}
                className="w-full rounded-lg border px-3 py-2 text-sm bg-white focus:outline-none focus:ring-2 focus:ring-blue-500"
              >
                <option value="critical">Critical</option>
                <option value="high">High</option>
                <option value="medium">Medium</option>
                <option value="low">Low</option>
              </select>
            </div>
          </div>

          {/* Title */}
          <div>
            <label className="block text-xs font-medium text-gray-700 mb-1">
              Title *
            </label>
            <input
              type="text"
              value={formTitle}
              onChange={(e) => setFormTitle(e.target.value)}
              required
              placeholder='e.g. "Cursor raises $200M Series C"'
              className="w-full rounded-lg border px-3 py-2 text-sm bg-white focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
          </div>

          {/* Description */}
          <div>
            <label className="block text-xs font-medium text-gray-700 mb-1">
              Description
            </label>
            <textarea
              value={formDesc}
              onChange={(e) => setFormDesc(e.target.value)}
              rows={2}
              placeholder="What happened? Why does it matter?"
              className="w-full rounded-lg border px-3 py-2 text-sm bg-white focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
          </div>

          {/* Source URL */}
          <div>
            <label className="block text-xs font-medium text-gray-700 mb-1">
              Source URL
            </label>
            <input
              type="url"
              value={formUrl}
              onChange={(e) => setFormUrl(e.target.value)}
              placeholder="https://…"
              className="w-full rounded-lg border px-3 py-2 text-sm bg-white focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
          </div>

          {/* Errors / Success */}
          {formError && (
            <div className="rounded-lg bg-red-50 border border-red-200 px-3 py-2 text-xs text-red-700">
              {formError}
            </div>
          )}
          {formSuccess && (
            <div className="rounded-lg bg-green-50 border border-green-200 px-3 py-2 text-xs text-green-700">
              {formSuccess}
            </div>
          )}

          {/* Submit */}
          <button
            type="submit"
            disabled={submitting || !formComp || !formTitle}
            className="inline-flex items-center gap-1.5 rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition"
          >
            {submitting ? "Submitting…" : "Submit Signal"}
          </button>
        </form>
      )}

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
            const detailHref =
              item.source === "change_event"
                ? `/dashboard/changes/${item.id}`
                : `/dashboard/activity/event/${item.id}`;
            return (
              <Link
                key={`${item.source}-${item.id}`}
                href={detailHref}
                className="block rounded-xl border bg-white p-5 hover:shadow-md hover:border-blue-200 transition group"
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
                  <div className="flex items-center gap-2">
                    <span className="text-xs text-gray-400 whitespace-nowrap">
                      {new Date(item.event_time).toLocaleDateString("en-US", {
                        month: "short",
                        day: "numeric",
                        hour: "2-digit",
                        minute: "2-digit",
                      })}
                    </span>
                    <ChevronRight className="h-4 w-4 text-gray-300 group-hover:text-blue-500 transition" />
                  </div>
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
                  <span
                    className="inline-flex items-center gap-1 mt-2 text-xs text-blue-500"
                  >
                    <ExternalLink className="h-3 w-3" />
                    View source
                  </span>
                )}
              </Link>
            );
          })}
        </div>
      )}
    </div>
  );
}
