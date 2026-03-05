"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { ArrowLeft, Globe, Plus, Play, Trash2, ExternalLink } from "lucide-react";
import { competitors as compApi, trackedPages as pagesApi } from "@/lib/api";
import type { Competitor, TrackedPage, PageType } from "@/lib/types";

const PAGE_TYPES: PageType[] = [
  "pricing",
  "home_hero",
  "landing",
  "features_docs",
  "integrations",
  "alternatives",
];

export default function CompetitorDetailPage() {
  const params = useParams();
  const id = params.id as string;
  const [comp, setComp] = useState<Competitor | null>(null);
  const [pages, setPages] = useState<TrackedPage[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showAdd, setShowAdd] = useState(false);
  const [form, setForm] = useState({ url: "", page_type: "pricing" as PageType });
  const [submitting, setSubmitting] = useState(false);
  const [capturing, setCapturing] = useState<string | null>(null);
  const [captureResult, setCaptureResult] = useState<string | null>(null);

  useEffect(() => {
    setLoading(true);
    Promise.all([compApi.get(id), pagesApi.list(id)])
      .then(([c, p]) => {
        setComp(c);
        setPages(p);
      })
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, [id]);

  const handleAddPage = async () => {
    if (!form.url.trim()) return;
    setSubmitting(true);
    setError(null);
    try {
      const page = await pagesApi.create(id, {
        url: form.url.trim(),
        page_type: form.page_type,
      });
      setPages((prev) => [page, ...prev]);
      setForm({ url: "", page_type: "pricing" });
      setShowAdd(false);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setSubmitting(false);
    }
  };

  const handleCapture = async (pageId: string) => {
    setCapturing(pageId);
    setCaptureResult(null);
    try {
      const res = await pagesApi.captureNow(pageId, true);
      const status = (res as any).status ?? "done";
      setCaptureResult(
        status === "no_change" ? "Captured — no changes detected" : "Captured — changes detected!"
      );
      setTimeout(() => setCaptureResult(null), 4000);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setCapturing(null);
    }
  };

  const handleDeletePage = async (pageId: string) => {
    if (!confirm("Delete this tracked page?")) return;
    try {
      await pagesApi.delete(pageId);
      setPages((prev) => prev.filter((p) => p.id !== pageId));
    } catch (e: any) {
      setError(e.message);
    }
  };

  if (loading) {
    return (
      <div className="space-y-4">
        <div className="h-8 w-48 animate-pulse rounded bg-gray-100" />
        <div className="h-64 animate-pulse rounded-xl bg-gray-100" />
      </div>
    );
  }

  if (!comp) {
    return <div className="text-center text-red-500 py-16">Competitor not found.</div>;
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3">
        <Link
          href="/dashboard/competitors"
          className="rounded-lg border p-1.5 text-gray-400 hover:text-gray-600 hover:bg-gray-50 transition"
        >
          <ArrowLeft className="h-4 w-4" />
        </Link>
        <div className="flex items-center gap-3">
          <div className="h-10 w-10 rounded-full bg-gray-100 flex items-center justify-center">
            <Globe className="h-5 w-5 text-gray-500" />
          </div>
          <div>
            <h1 className="text-xl font-bold text-gray-900">{comp.name}</h1>
            <p className="text-sm text-gray-500">{comp.domain}</p>
          </div>
        </div>
      </div>

      {error && (
        <div className="rounded-lg bg-red-50 border border-red-200 px-4 py-2 text-sm text-red-700">
          {error}
        </div>
      )}

      {captureResult && (
        <div className="rounded-lg bg-green-50 border border-green-200 px-4 py-2 text-sm text-green-700">
          {captureResult}
        </div>
      )}

      {/* Tracked Pages */}
      <div>
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-lg font-semibold text-gray-900">Tracked Pages</h2>
          <button
            onClick={() => setShowAdd(!showAdd)}
            className="inline-flex items-center gap-1.5 rounded-lg bg-gray-900 px-3 py-1.5 text-xs text-white hover:bg-gray-700 transition"
          >
            <Plus className="h-3 w-3" /> Add Page
          </button>
        </div>

        {showAdd && (
          <div className="rounded-xl border bg-white p-5 mb-4">
            <div className="grid grid-cols-1 md:grid-cols-3 gap-3 mb-3">
              <input
                autoFocus
                placeholder="URL (e.g. https://competitor.com/pricing)"
                value={form.url}
                onChange={(e) => setForm({ ...form, url: e.target.value })}
                onKeyDown={(e) => e.key === "Enter" && handleAddPage()}
                className="col-span-2 rounded-lg border px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
              <select
                value={form.page_type}
                onChange={(e) =>
                  setForm({ ...form, page_type: e.target.value as PageType })
                }
                className="rounded-lg border px-3 py-2 text-sm bg-white focus:outline-none focus:ring-2 focus:ring-blue-500"
              >
                {PAGE_TYPES.map((t) => (
                  <option key={t} value={t}>
                    {t.replace(/_/g, " ")}
                  </option>
                ))}
              </select>
            </div>
            <div className="flex gap-2">
              <button
                onClick={handleAddPage}
                disabled={submitting}
                className="rounded-lg bg-blue-600 px-3 py-1.5 text-xs text-white hover:bg-blue-500 disabled:opacity-50 transition"
              >
                {submitting ? "Adding..." : "Add Page"}
              </button>
              <button
                onClick={() => setShowAdd(false)}
                className="rounded-lg border px-3 py-1.5 text-xs text-gray-600 hover:bg-gray-50 transition"
              >
                Cancel
              </button>
            </div>
          </div>
        )}

        {pages.length === 0 ? (
          <div className="rounded-xl border bg-white p-8 text-center text-sm text-gray-400">
            No pages tracked yet. Add a URL to start monitoring.
          </div>
        ) : (
          <div className="space-y-2">
            {pages.map((p) => (
              <div
                key={p.id}
                className="rounded-xl border bg-white p-4 flex items-center justify-between hover:shadow-sm transition"
              >
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="text-xs font-medium bg-blue-50 text-blue-700 px-2 py-0.5 rounded-full">
                      {p.page_type.replace(/_/g, " ")}
                    </span>
                    <span
                      className={`text-xs px-2 py-0.5 rounded-full ${
                        p.is_active
                          ? "bg-green-50 text-green-700"
                          : "bg-gray-100 text-gray-500"
                      }`}
                    >
                      {p.is_active ? "Active" : "Paused"}
                    </span>
                  </div>
                  <p className="text-sm text-gray-700 truncate mt-1">{p.url}</p>
                  <p className="text-xs text-gray-400 mt-0.5">
                    Every {p.check_interval_hours}h
                    {p.last_checked_at &&
                      ` · Last: ${new Date(p.last_checked_at).toLocaleString()}`}
                  </p>
                </div>
                <div className="flex items-center gap-1.5 ml-4">
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
                  <button
                    onClick={() => handleDeletePage(p.id)}
                    className="p-1.5 text-gray-400 hover:text-red-500 transition"
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
