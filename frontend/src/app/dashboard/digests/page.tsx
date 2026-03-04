"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Mail, ExternalLink, RefreshCw, Link2, Plus } from "lucide-react";
import { useActiveWorkspace } from "@/lib/hooks";
import { digests as digestApi, API_URL } from "@/lib/api";
import type { Digest } from "@/lib/types";

export default function DigestsPage() {
  const { activeId } = useActiveWorkspace();
  const [list, setList] = useState<Digest[]>([]);
  const [loading, setLoading] = useState(true);
  const [generating, setGenerating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!activeId) return;
    setLoading(true);
    digestApi
      .list(activeId)
      .then(setList)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, [activeId]);

  const handleGenerate = async () => {
    if (!activeId) return;
    setGenerating(true);
    setError(null);
    try {
      const res = await digestApi.generate(activeId, 7);
      if (res.status === "generated") {
        const updated = await digestApi.list(activeId);
        setList(updated);
      } else {
        setError("No changes in the past 7 days to generate a digest.");
      }
    } catch (e: any) {
      setError(e.message);
    } finally {
      setGenerating(false);
    }
  };

  const handleGetSignedUrl = async (digestId: string) => {
    try {
      const res = await digestApi.signedUrl(digestId);
      await navigator.clipboard.writeText(res.signed_url);
      alert("Signed URL copied to clipboard!");
    } catch (e: any) {
      setError(e.message);
    }
  };

  if (!activeId) {
    return (
      <div className="text-center text-gray-400 py-16">
        Select a workspace first.
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-gray-900">Weekly Digests</h1>
        <button
          onClick={handleGenerate}
          disabled={generating}
          className="inline-flex items-center gap-2 rounded-lg bg-gray-900 px-4 py-2 text-sm text-white hover:bg-gray-700 disabled:opacity-50 transition"
        >
          {generating ? (
            <RefreshCw className="h-4 w-4 animate-spin" />
          ) : (
            <Plus className="h-4 w-4" />
          )}
          {generating ? "Generating..." : "Generate Digest"}
        </button>
      </div>

      {error && (
        <div className="rounded-lg bg-red-50 border border-red-200 px-4 py-2 text-sm text-red-700">
          {error}
        </div>
      )}

      {loading ? (
        <div className="space-y-3">
          {[1, 2, 3].map((i) => (
            <div key={i} className="h-20 animate-pulse rounded-xl bg-gray-100" />
          ))}
        </div>
      ) : list.length === 0 ? (
        <div className="rounded-xl border bg-white p-12 text-center text-gray-400">
          No digests yet. Click &quot;Generate Digest&quot; or wait for the
          automatic Monday 9am UTC schedule.
        </div>
      ) : (
        <div className="space-y-2">
          {list.map((d) => (
            <div
              key={d.id}
              className="rounded-xl border bg-white p-5 hover:shadow-sm transition"
            >
              <div className="flex items-center justify-between">
                <Link
                  href={`/dashboard/digests/${d.id}`}
                  className="flex items-center gap-4 flex-1"
                >
                  <div className="h-10 w-10 rounded-full bg-blue-50 flex items-center justify-center">
                    <Mail className="h-5 w-5 text-blue-600" />
                  </div>
                  <div>
                    <h3 className="font-semibold text-gray-900">
                      {new Date(d.period_start).toLocaleDateString()} –{" "}
                      {new Date(d.period_end).toLocaleDateString()}
                    </h3>
                    <p className="text-sm text-gray-500">
                      {d.change_event_ids.length} change
                      {d.change_event_ids.length !== 1 ? "s" : ""}
                      {d.email_sent_at && (
                        <span className="ml-2 text-green-600">
                          · Sent{" "}
                          {new Date(d.email_sent_at).toLocaleDateString()}
                        </span>
                      )}
                      {d.ranking_data && d.ranking_data.length > 0 && (
                        <span className="ml-2 text-gray-400">
                          · Top score:{" "}
                          {d.ranking_data[0].rank_score.toFixed(0)}
                        </span>
                      )}
                    </p>
                  </div>
                </Link>
                <div className="flex items-center gap-1.5">
                  {d.web_view_token && (
                    <a
                      href={`${API_URL}/api/digest-view/${d.web_view_token}`}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="inline-flex items-center gap-1 rounded-lg border px-2.5 py-1.5 text-xs text-gray-600 hover:bg-gray-50 transition"
                    >
                      <ExternalLink className="h-3 w-3" /> View
                    </a>
                  )}
                  <button
                    onClick={() => handleGetSignedUrl(d.id)}
                    className="inline-flex items-center gap-1 rounded-lg border px-2.5 py-1.5 text-xs text-gray-600 hover:bg-gray-50 transition"
                  >
                    <Link2 className="h-3 w-3" /> Share
                  </button>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
