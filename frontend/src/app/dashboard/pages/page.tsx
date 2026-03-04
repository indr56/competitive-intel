"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { FileText, Play, ExternalLink } from "lucide-react";
import { useActiveWorkspace } from "@/lib/hooks";
import {
  competitors as compApi,
  trackedPages as pagesApi,
} from "@/lib/api";
import type { Competitor, TrackedPage } from "@/lib/types";

interface PageWithComp extends TrackedPage {
  competitor_name: string;
}

export default function TrackedPagesPage() {
  const { activeId } = useActiveWorkspace();
  const [pages, setPages] = useState<PageWithComp[]>([]);
  const [loading, setLoading] = useState(true);
  const [capturing, setCapturing] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!activeId) return;
    setLoading(true);
    compApi
      .list(activeId)
      .then(async (comps) => {
        const all: PageWithComp[] = [];
        for (const c of comps) {
          const ps = await pagesApi.list(c.id);
          ps.forEach((p) =>
            all.push({ ...p, competitor_name: c.name })
          );
        }
        setPages(all);
      })
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, [activeId]);

  const handleCapture = async (pageId: string) => {
    setCapturing(pageId);
    try {
      await pagesApi.captureNow(pageId, true);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setCapturing(null);
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
      <h1 className="text-2xl font-bold text-gray-900">Tracked Pages</h1>

      {error && (
        <div className="rounded-lg bg-red-50 border border-red-200 px-4 py-2 text-sm text-red-700">
          {error}
        </div>
      )}

      {loading ? (
        <div className="space-y-3">
          {[1, 2, 3].map((i) => (
            <div key={i} className="h-16 animate-pulse rounded-xl bg-gray-100" />
          ))}
        </div>
      ) : pages.length === 0 ? (
        <div className="rounded-xl border bg-white p-12 text-center text-gray-400">
          No tracked pages. Go to a{" "}
          <Link
            href="/dashboard/competitors"
            className="text-blue-600 hover:underline"
          >
            competitor
          </Link>{" "}
          to add pages.
        </div>
      ) : (
        <div className="space-y-2">
          {pages.map((p) => (
            <div
              key={p.id}
              className="rounded-xl border bg-white p-4 flex items-center justify-between hover:shadow-sm transition"
            >
              <div className="flex items-center gap-3 flex-1 min-w-0">
                <FileText className="h-4 w-4 text-gray-400 flex-shrink-0" />
                <div className="min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="text-xs font-medium text-blue-600">
                      {p.competitor_name}
                    </span>
                    <span className="text-xs bg-blue-50 text-blue-700 px-1.5 py-0.5 rounded-full">
                      {p.page_type.replace(/_/g, " ")}
                    </span>
                    <span
                      className={`text-xs px-1.5 py-0.5 rounded-full ${
                        p.is_active
                          ? "bg-green-50 text-green-700"
                          : "bg-gray-100 text-gray-500"
                      }`}
                    >
                      {p.is_active ? "Active" : "Paused"}
                    </span>
                  </div>
                  <p className="text-sm text-gray-700 truncate">{p.url}</p>
                  <p className="text-xs text-gray-400">
                    Every {p.check_interval_hours}h
                    {p.last_checked_at &&
                      ` · Last: ${new Date(p.last_checked_at).toLocaleString()}`}
                  </p>
                </div>
              </div>
              <div className="flex items-center gap-1.5 ml-3">
                <a
                  href={p.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="p-1.5 text-gray-400 hover:text-gray-600 transition"
                >
                  <ExternalLink className="h-3.5 w-3.5" />
                </a>
                <button
                  onClick={() => handleCapture(p.id)}
                  disabled={capturing === p.id}
                  className="inline-flex items-center gap-1 rounded-lg border px-2 py-1 text-xs text-gray-600 hover:bg-gray-50 disabled:opacity-50 transition"
                >
                  <Play className="h-3 w-3" />
                  {capturing === p.id ? "..." : "Capture"}
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
