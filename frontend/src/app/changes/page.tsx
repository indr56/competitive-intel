"use client";

import { useEffect, useState } from "react";
import { AlertTriangle, ArrowRight } from "lucide-react";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

interface ChangeEvent {
  id: string;
  competitor_id: string;
  categories: string[];
  severity: string | null;
  ai_summary: string | null;
  ai_why_it_matters: string | null;
  ai_next_moves: string | null;
  created_at: string;
}

const SEVERITY_COLORS: Record<string, string> = {
  critical: "bg-red-50 text-red-700 border-red-200",
  high: "bg-orange-50 text-orange-700 border-orange-200",
  medium: "bg-yellow-50 text-yellow-700 border-yellow-200",
  low: "bg-green-50 text-green-700 border-green-200",
};

export default function ChangesPage() {
  const [changes, setChanges] = useState<ChangeEvent[]>([]);
  const [severityFilter, setSeverityFilter] = useState("");

  useEffect(() => {
    const qs = new URLSearchParams();
    if (severityFilter) qs.set("severity", severityFilter);
    qs.set("limit", "50");
    fetch(`${API_URL}/api/changes?${qs.toString()}`)
      .then((r) => r.json())
      .then(setChanges)
      .catch(console.error);
  }, [severityFilter]);

  return (
    <div className="min-h-screen bg-gray-50">
      <nav className="border-b bg-white">
        <div className="mx-auto max-w-6xl flex items-center justify-between px-6 py-4">
          <a href="/" className="text-lg font-bold text-gray-900">
            Competitive Moves Intelligence
          </a>
          <div className="flex gap-6 text-sm text-gray-600">
            <a href="/competitors" className="hover:text-gray-900">Competitors</a>
            <a href="/changes" className="text-gray-900 font-medium">Changes</a>
            <a href="/digests" className="hover:text-gray-900">Digests</a>
          </div>
        </div>
      </nav>

      <main className="mx-auto max-w-6xl px-6 py-8">
        <div className="flex items-center justify-between mb-6">
          <h2 className="text-2xl font-bold text-gray-900">Change Feed</h2>
          <div className="flex gap-2">
            {["", "critical", "high", "medium", "low"].map((s) => (
              <button
                key={s}
                onClick={() => setSeverityFilter(s)}
                className={`rounded-full px-3 py-1 text-xs font-medium border transition ${
                  severityFilter === s
                    ? "bg-gray-900 text-white border-gray-900"
                    : "bg-white text-gray-600 border-gray-200 hover:border-gray-400"
                }`}
              >
                {s || "All"}
              </button>
            ))}
          </div>
        </div>

        {changes.length === 0 ? (
          <div className="rounded-xl border bg-white p-12 text-center text-gray-400">
            No changes detected yet. Start tracking competitor pages to see changes here.
          </div>
        ) : (
          <div className="space-y-4">
            {changes.map((ce) => (
              <div
                key={ce.id}
                className="rounded-xl border bg-white p-6 hover:shadow-sm transition"
              >
                <div className="flex items-start justify-between mb-3">
                  <div className="flex items-center gap-3">
                    <AlertTriangle className="w-5 h-5 text-orange-500" />
                    <span
                      className={`text-xs font-semibold px-2 py-0.5 rounded-full border ${
                        SEVERITY_COLORS[ce.severity || "medium"]
                      }`}
                    >
                      {(ce.severity || "medium").toUpperCase()}
                    </span>
                    <div className="flex gap-1.5">
                      {ce.categories.map((cat) => (
                        <span
                          key={cat}
                          className="text-xs bg-gray-100 text-gray-600 px-2 py-0.5 rounded-full"
                        >
                          {cat.replace(/_/g, " ")}
                        </span>
                      ))}
                    </div>
                  </div>
                  <span className="text-xs text-gray-400">
                    {new Date(ce.created_at).toLocaleDateString()}
                  </span>
                </div>

                {ce.ai_summary && (
                  <p className="text-sm text-gray-800 mb-2">{ce.ai_summary}</p>
                )}
                {ce.ai_why_it_matters && (
                  <p className="text-sm text-gray-500 mb-2">
                    <strong className="text-gray-700">Why it matters:</strong>{" "}
                    {ce.ai_why_it_matters}
                  </p>
                )}
                {ce.ai_next_moves && (
                  <p className="text-sm text-gray-500">
                    <strong className="text-gray-700">Next moves:</strong>{" "}
                    {ce.ai_next_moves}
                  </p>
                )}
              </div>
            ))}
          </div>
        )}
      </main>
    </div>
  );
}
