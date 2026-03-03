"use client";

import { useEffect, useState } from "react";
import { Mail, ExternalLink } from "lucide-react";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

interface DigestItem {
  id: string;
  workspace_id: string;
  period_start: string;
  period_end: string;
  change_event_ids: string[];
  email_sent_at: string | null;
  web_view_token: string | null;
  created_at: string;
}

export default function DigestsPage() {
  const [digests, setDigests] = useState<DigestItem[]>([]);
  const [workspaceId, setWorkspaceId] = useState("");

  useEffect(() => {
    fetch(`${API_URL}/api/workspaces`)
      .then((r) => r.json())
      .then((data) => {
        if (data.length > 0) setWorkspaceId(data[0].id);
      })
      .catch(console.error);
  }, []);

  useEffect(() => {
    if (!workspaceId) return;
    fetch(`${API_URL}/api/workspaces/${workspaceId}/digests`)
      .then((r) => r.json())
      .then(setDigests)
      .catch(console.error);
  }, [workspaceId]);

  const handleResend = async (digestId: string) => {
    await fetch(`${API_URL}/api/digests/${digestId}/resend`, { method: "POST" });
    alert("Digest resend queued.");
  };

  return (
    <div className="min-h-screen bg-gray-50">
      <nav className="border-b bg-white">
        <div className="mx-auto max-w-6xl flex items-center justify-between px-6 py-4">
          <a href="/" className="text-lg font-bold text-gray-900">
            Competitive Moves Intelligence
          </a>
          <div className="flex gap-6 text-sm text-gray-600">
            <a href="/competitors" className="hover:text-gray-900">Competitors</a>
            <a href="/changes" className="hover:text-gray-900">Changes</a>
            <a href="/digests" className="text-gray-900 font-medium">Digests</a>
          </div>
        </div>
      </nav>

      <main className="mx-auto max-w-6xl px-6 py-8">
        <h2 className="text-2xl font-bold text-gray-900 mb-6">Weekly Digests</h2>

        {digests.length === 0 ? (
          <div className="rounded-xl border bg-white p-12 text-center text-gray-400">
            No digests yet. Digests are generated automatically every Monday at 9am UTC.
          </div>
        ) : (
          <div className="space-y-3">
            {digests.map((d) => (
              <div
                key={d.id}
                className="rounded-xl border bg-white p-5 flex items-center justify-between hover:shadow-sm transition"
              >
                <div className="flex items-center gap-4">
                  <div className="w-10 h-10 rounded-full bg-blue-50 flex items-center justify-center">
                    <Mail className="w-5 h-5 text-blue-600" />
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
                          · Sent {new Date(d.email_sent_at).toLocaleDateString()}
                        </span>
                      )}
                    </p>
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  {d.web_view_token && (
                    <a
                      href={`${API_URL}/api/digest-view/${d.web_view_token}`}
                      target="_blank"
                      className="inline-flex items-center gap-1 rounded-lg border px-3 py-1.5 text-xs text-gray-600 hover:bg-gray-50 transition"
                    >
                      <ExternalLink className="w-3 h-3" /> View
                    </a>
                  )}
                  <button
                    onClick={() => handleResend(d.id)}
                    className="rounded-lg border px-3 py-1.5 text-xs text-gray-600 hover:bg-gray-50 transition"
                  >
                    Resend
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </main>
    </div>
  );
}
