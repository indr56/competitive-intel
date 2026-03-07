"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { ArrowLeft, Mail, ExternalLink, Link2 } from "lucide-react";
import { digests as digestApi, API_URL } from "@/lib/api";
import type { Digest } from "@/lib/types";

export default function DigestDetailPage() {
  const params = useParams();
  const id = params.id as string;
  const [digest, setDigest] = useState<Digest | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setLoading(true);
    digestApi
      .get(id)
      .then(setDigest)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, [id]);

  const handleCopySignedUrl = async () => {
    try {
      const res = await digestApi.signedUrl(id);
      await navigator.clipboard.writeText(res.signed_url);
      alert("Signed URL copied to clipboard!");
    } catch (e: any) {
      setError(e.message);
    }
  };

  if (loading) {
    return (
      <div className="space-y-4">
        <div className="h-8 w-64 animate-pulse rounded bg-gray-100" />
        <div className="h-96 animate-pulse rounded-xl bg-gray-100" />
      </div>
    );
  }

  if (!digest) {
    return (
      <div className="text-center text-red-500 py-16">
        {error || "Digest not found."}
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3">
        <Link
          href="/dashboard/digests"
          className="rounded-lg border p-1.5 text-gray-400 hover:text-gray-600 hover:bg-gray-50 transition"
        >
          <ArrowLeft className="h-4 w-4" />
        </Link>
        <div>
          <h1 className="text-xl font-bold text-gray-900">Digest Detail</h1>
          <p className="text-sm text-gray-500">
            {new Date(digest.period_start).toLocaleDateString()} –{" "}
            {new Date(digest.period_end).toLocaleDateString()} ·{" "}
            {digest.change_event_ids.length} changes
          </p>
        </div>
      </div>

      {error && (
        <div className="rounded-lg bg-red-50 border border-red-200 px-4 py-2 text-sm text-red-700">
          {error}
        </div>
      )}

      {/* Actions */}
      <div className="flex gap-2">
        {digest.web_view_token && (
          <a
            href={`${API_URL}/api/digest-view/${digest.web_view_token}`}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-1.5 rounded-lg border px-3 py-1.5 text-xs text-gray-600 hover:bg-gray-50 transition"
          >
            <ExternalLink className="h-3.5 w-3.5" /> Open Web View
          </a>
        )}
        <button
          onClick={handleCopySignedUrl}
          className="inline-flex items-center gap-1.5 rounded-lg border px-3 py-1.5 text-xs text-gray-600 hover:bg-gray-50 transition"
        >
          <Link2 className="h-3.5 w-3.5" /> Copy Signed URL
        </button>
      </div>

      {/* Ranking data */}
      {digest.ranking_data && digest.ranking_data.length > 0 && (
        <div className="rounded-xl border bg-white overflow-hidden">
          <div className="px-5 py-3 border-b bg-gray-50">
            <h2 className="text-sm font-semibold text-gray-800">
              Ranked Events
            </h2>
          </div>
          <div className="divide-y">
            {digest.ranking_data.map((r, i) => {
              const isSignalEvent = !!r.event_id && !r.change_event_id;
              const entryId = r.change_event_id || r.event_id || `entry-${i}`;
              const href = isSignalEvent
                ? `/dashboard/activity/event/${r.event_id}`
                : `/dashboard/changes/${r.change_event_id}`;

              const SIGNAL_LABELS: Record<string, string> = {
                blog_post: "Blog Post",
                hiring: "Hiring",
                funding: "Funding",
                review: "Review",
                marketing: "Marketing",
                positioning_change: "Positioning",
                integration_added: "Integration Added",
                integration_removed: "Integration Removed",
                landing_page_created: "Landing Page",
              };

              return (
                <Link
                  key={entryId}
                  href={href}
                  className="flex items-center justify-between px-5 py-3 hover:bg-gray-50 transition"
                >
                  <div className="flex items-center gap-3">
                    <span className="text-xs font-bold text-gray-400 w-5">
                      #{i + 1}
                    </span>
                    <span
                      className={`text-[10px] font-semibold px-2 py-0.5 rounded-full ${
                        r.severity === "critical"
                          ? "bg-red-50 text-red-700"
                          : r.severity === "high"
                          ? "bg-orange-50 text-orange-700"
                          : r.severity === "medium"
                          ? "bg-yellow-50 text-yellow-700"
                          : "bg-green-50 text-green-700"
                      }`}
                    >
                      {(r.severity ?? "medium").toUpperCase()}
                    </span>
                    {isSignalEvent && r.signal_type && (
                      <span className="text-[10px] bg-purple-50 text-purple-700 px-1.5 py-0.5 rounded-full">
                        {SIGNAL_LABELS[r.signal_type] || r.signal_type}
                      </span>
                    )}
                    {!isSignalEvent && (
                      <span className="text-[10px] bg-blue-50 text-blue-700 px-1.5 py-0.5 rounded-full">
                        Website Change
                      </span>
                    )}
                    <span className="text-xs text-gray-500 font-mono">
                      {entryId.slice(0, 8)}…
                    </span>
                  </div>
                  <div className="flex items-center gap-4 text-xs text-gray-400">
                    <span>Score: {r.rank_score.toFixed(0)}</span>
                    {r.impact_score != null && (
                      <span>Impact: {r.impact_score.toFixed(0)}</span>
                    )}
                  </div>
                </Link>
              );
            })}
          </div>
        </div>
      )}

      {/* Markdown body */}
      {digest.markdown_body && (
        <div className="rounded-xl border bg-white overflow-hidden">
          <div className="px-5 py-3 border-b bg-gray-50">
            <h2 className="text-sm font-semibold text-gray-800">
              Markdown Preview
            </h2>
          </div>
          <pre className="p-5 text-xs text-gray-600 overflow-x-auto whitespace-pre-wrap max-h-96">
            {digest.markdown_body}
          </pre>
        </div>
      )}

      {/* HTML body preview */}
      {digest.html_body && (
        <div className="rounded-xl border bg-white overflow-hidden">
          <div className="px-5 py-3 border-b bg-gray-50">
            <h2 className="text-sm font-semibold text-gray-800">
              HTML Email Preview
            </h2>
          </div>
          <div className="p-2">
            <iframe
              srcDoc={digest.html_body}
              className="w-full h-[500px] border rounded-lg"
              title="Digest HTML Preview"
            />
          </div>
        </div>
      )}
    </div>
  );
}
