"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import {
  ArrowLeft,
  Brain,
  Copy,
  Check,
  ExternalLink,
  Globe,
  Newspaper,
  Users,
  DollarSign,
  Star,
  Megaphone,
  Tag,
  TrendingUp,
  RefreshCw,
  Loader2,
  MessageSquare,
  Plug,
  PlugZap,
  FileText,
} from "lucide-react";
import { events as eventsApi, competitors as compApi } from "@/lib/api";
import type { CompetitorEvent, Competitor } from "@/lib/types";

const SEV_COLORS: Record<string, string> = {
  critical: "bg-red-50 text-red-700",
  high: "bg-orange-50 text-orange-700",
  medium: "bg-yellow-50 text-yellow-700",
  low: "bg-green-50 text-green-700",
};

const SIGNAL_META: Record<
  string,
  { label: string; icon: typeof Globe; color: string; bg: string }
> = {
  website_change: { label: "Website Change", icon: Globe, color: "text-blue-600", bg: "bg-blue-50" },
  pricing_change: { label: "Pricing Change", icon: DollarSign, color: "text-red-600", bg: "bg-red-50" },
  product_change: { label: "Product Change", icon: Tag, color: "text-purple-600", bg: "bg-purple-50" },
  blog_post: { label: "Blog Post", icon: Newspaper, color: "text-emerald-600", bg: "bg-emerald-50" },
  hiring: { label: "Hiring", icon: Users, color: "text-amber-600", bg: "bg-amber-50" },
  funding: { label: "Funding", icon: TrendingUp, color: "text-pink-600", bg: "bg-pink-50" },
  review: { label: "Review", icon: Star, color: "text-yellow-600", bg: "bg-yellow-50" },
  marketing: { label: "Marketing", icon: Megaphone, color: "text-indigo-600", bg: "bg-indigo-50" },
  positioning_change: { label: "Positioning", icon: MessageSquare, color: "text-cyan-600", bg: "bg-cyan-50" },
  integration_added: { label: "Integration Added", icon: Plug, color: "text-teal-600", bg: "bg-teal-50" },
  integration_removed: { label: "Integration Removed", icon: PlugZap, color: "text-rose-600", bg: "bg-rose-50" },
  landing_page_created: { label: "Landing Page", icon: FileText, color: "text-violet-600", bg: "bg-violet-50" },
};

export default function EventDetailPage() {
  const params = useParams();
  const id = params.id as string;
  const [event, setEvent] = useState<CompetitorEvent | null>(null);
  const [comp, setComp] = useState<Competitor | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState<string | null>(null);
  const [analyzing, setAnalyzing] = useState(false);

  useEffect(() => {
    setLoading(true);
    eventsApi
      .get(id)
      .then(async (ev) => {
        setEvent(ev);
        try {
          const c = await compApi.get(ev.competitor_id);
          setComp(c);
        } catch {}
      })
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, [id]);

  const handleAnalyze = async () => {
    if (!event) return;
    setAnalyzing(true);
    setError(null);
    try {
      const updated = await eventsApi.analyze(event.id);
      setEvent(updated);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setAnalyzing(false);
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

  if (!event) {
    return (
      <div className="text-center text-red-500 py-16">
        {error || "Event not found."}
      </div>
    );
  }

  const sev = event.severity ?? "medium";
  const meta = SIGNAL_META[event.signal_type] || SIGNAL_META.website_change;
  const Icon = meta.icon;
  const metadata = event.metadata_json || {};

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center gap-3">
        <Link
          href="/dashboard/activity"
          className="rounded-lg border p-1.5 text-gray-400 hover:text-gray-600 hover:bg-gray-50 transition"
        >
          <ArrowLeft className="h-4 w-4" />
        </Link>
        <div className="flex-1">
          <h1 className="text-xl font-bold text-gray-900">Signal Detail</h1>
          <div className="flex items-center gap-2 mt-1 flex-wrap">
            <span
              className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-semibold ${meta.bg} ${meta.color}`}
            >
              <Icon className="h-3 w-3" />
              {meta.label}
            </span>
            <span
              className={`text-[10px] font-semibold px-2 py-0.5 rounded-full ${SEV_COLORS[sev]}`}
            >
              {sev.toUpperCase()}
            </span>
            {comp && (
              <Link
                href={`/dashboard/competitors/${comp.id}`}
                className="text-xs text-blue-600 font-medium hover:underline"
              >
                {comp.name}
              </Link>
            )}
            <span className="text-xs text-gray-400">
              {new Date(event.event_time).toLocaleString()}
            </span>
          </div>
        </div>
      </div>

      {error && (
        <div className="rounded-lg bg-red-50 border border-red-200 px-4 py-2 text-sm text-red-700">
          {error}
        </div>
      )}

      {/* Event Overview Card */}
      <div className="rounded-xl border bg-white overflow-hidden">
        <div className="bg-gradient-to-r from-gray-50 to-slate-50 px-5 py-3 border-b">
          <h2 className="text-sm font-semibold text-gray-800">Event Overview</h2>
        </div>
        <div className="p-5 space-y-3">
          <div>
            <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-1">
              Title
            </h3>
            <p className="text-sm font-medium text-gray-900">{event.title}</p>
          </div>
          {event.description && (
            <div>
              <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-1">
                Description
              </h3>
              <p className="text-sm text-gray-700 leading-relaxed whitespace-pre-wrap">
                {event.description}
              </p>
            </div>
          )}
          {event.source_url && (
            <div>
              <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-1">
                Source
              </h3>
              <a
                href={event.source_url}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-1.5 text-sm text-blue-600 hover:text-blue-800 hover:underline"
              >
                <ExternalLink className="h-3.5 w-3.5" />
                {event.source_url.length > 80
                  ? event.source_url.slice(0, 80) + "…"
                  : event.source_url}
              </a>
            </div>
          )}
        </div>
      </div>

      {/* AI Analysis Panel */}
      {(event.ai_summary || event.ai_implications) ? (
        <div className="rounded-xl border bg-white overflow-hidden">
          <div className="bg-gradient-to-r from-purple-50 to-blue-50 px-5 py-3 border-b flex items-center gap-2">
            <Brain className="h-4 w-4 text-purple-600" />
            <span className="text-sm font-semibold text-gray-800">
              AI Analysis
            </span>
          </div>
          <div className="p-5 space-y-4">
            {event.ai_summary && (
              <Section
                title="Summary"
                text={event.ai_summary}
                onCopy={() => handleCopy(event.ai_summary!, "summary")}
                copied={copied === "summary"}
              />
            )}
            {event.ai_implications && (
              <Section
                title="Strategic Implications"
                text={event.ai_implications}
                onCopy={() => handleCopy(event.ai_implications!, "implications")}
                copied={copied === "implications"}
              />
            )}
          </div>
        </div>
      ) : (
        <div className="rounded-xl border bg-white overflow-hidden">
          <div className="bg-gradient-to-r from-purple-50 to-blue-50 px-5 py-3 border-b flex items-center gap-2">
            <Brain className="h-4 w-4 text-purple-600" />
            <span className="text-sm font-semibold text-gray-800">
              AI Analysis
            </span>
          </div>
          <div className="p-8 text-center space-y-3">
            <p className="text-sm text-gray-400">
              AI analysis has not been generated for this signal yet.
            </p>
            <button
              onClick={handleAnalyze}
              disabled={analyzing}
              className="inline-flex items-center gap-2 rounded-lg bg-purple-600 px-4 py-2 text-sm font-medium text-white hover:bg-purple-700 disabled:opacity-50 transition"
            >
              {analyzing ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <RefreshCw className="h-4 w-4" />
              )}
              {analyzing ? "Generating…" : "Generate Analysis"}
            </button>
          </div>
        </div>
      )}

      {/* Metadata */}
      {Object.keys(metadata).length > 0 && (
        <div className="rounded-xl border bg-white overflow-hidden">
          <div className="bg-gray-50 px-5 py-3 border-b flex items-center justify-between">
            <h2 className="text-sm font-semibold text-gray-800">
              Signal Metadata
            </h2>
            <button
              onClick={() =>
                handleCopy(JSON.stringify(metadata, null, 2), "metadata")
              }
              className="text-gray-400 hover:text-gray-600 transition p-0.5"
            >
              {copied === "metadata" ? (
                <Check className="h-3.5 w-3.5 text-green-500" />
              ) : (
                <Copy className="h-3.5 w-3.5" />
              )}
            </button>
          </div>
          <div className="p-5">
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              {Object.entries(metadata).map(([key, value]) => (
                <div key={key} className="text-sm">
                  <span className="text-xs font-medium text-gray-500">
                    {key.replace(/_/g, " ")}
                  </span>
                  <p className="text-gray-800 mt-0.5">
                    {typeof value === "object"
                      ? JSON.stringify(value)
                      : String(value)}
                  </p>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* Debug info */}
      <div className="text-[10px] text-gray-300 flex gap-4">
        <span>ID: {event.id}</span>
        <span>Processed: {event.is_processed ? "Yes" : "No"}</span>
        <span>Created: {new Date(event.created_at).toLocaleString()}</span>
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
      <p className="text-sm text-gray-700 leading-relaxed whitespace-pre-wrap">{text}</p>
    </div>
  );
}
