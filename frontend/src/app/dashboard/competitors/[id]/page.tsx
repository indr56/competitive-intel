"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import {
  ArrowLeft, Globe, Plus, Play, Trash2, ExternalLink,
  Radar, CheckCircle, XCircle, AlertTriangle, Loader2,
} from "lucide-react";
import {
  competitors as compApi,
  trackedPages as pagesApi,
  signalSources as srcApi,
} from "@/lib/api";
import type {
  Competitor, TrackedPage, PageType,
  SignalSource, TestSourceResult, ScanResult,
} from "@/lib/types";

const PAGE_TYPES: PageType[] = [
  "pricing", "home_hero", "landing", "features_docs", "integrations", "alternatives",
];

const SIGNAL_TYPES = [
  { value: "blog_post", label: "Blog / RSS Feed" },
  { value: "hiring", label: "Hiring / Careers" },
  { value: "funding", label: "Funding / Press" },
  { value: "review", label: "Reviews" },
  { value: "marketing", label: "Marketing" },
];

const TEST_STATUS_ICON: Record<string, typeof CheckCircle> = {
  valid: CheckCircle,
  unreachable: XCircle,
  unexpected_content: AlertTriangle,
  no_items_found: AlertTriangle,
};
const TEST_STATUS_COLOR: Record<string, string> = {
  valid: "text-green-600",
  unreachable: "text-red-600",
  unexpected_content: "text-yellow-600",
  no_items_found: "text-yellow-600",
};

export default function CompetitorDetailPage() {
  const params = useParams();
  const id = params.id as string;
  const [comp, setComp] = useState<Competitor | null>(null);
  const [pages, setPages] = useState<TrackedPage[]>([]);
  const [sources, setSources] = useState<SignalSource[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  // Tracked page form
  const [showAddPage, setShowAddPage] = useState(false);
  const [pageForm, setPageForm] = useState({ url: "", page_type: "pricing" as PageType });
  const [submittingPage, setSubmittingPage] = useState(false);
  const [capturing, setCapturing] = useState<string | null>(null);

  // Signal source form
  const [showAddSource, setShowAddSource] = useState(false);
  const [srcForm, setSrcForm] = useState({ signal_type: "blog_post", source_url: "", source_label: "" });
  const [submittingSrc, setSubmittingSrc] = useState(false);

  // Test / Scan state
  const [testingId, setTestingId] = useState<string | null>(null);
  const [testResults, setTestResults] = useState<Record<string, TestSourceResult>>({});
  const [scanning, setScanning] = useState(false);
  const [scanResult, setScanResult] = useState<ScanResult | null>(null);

  useEffect(() => {
    setLoading(true);
    Promise.all([compApi.get(id), pagesApi.list(id), srcApi.list(id)])
      .then(([c, p, s]) => { setComp(c); setPages(p); setSources(s); })
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, [id]);

  const clearMessages = () => { setError(null); setSuccess(null); };

  // ── Tracked Pages handlers ──
  const handleAddPage = async () => {
    if (!pageForm.url.trim()) { setError("URL is required."); return; }
    setSubmittingPage(true); clearMessages();
    try {
      const page = await pagesApi.create(id, { url: pageForm.url.trim(), page_type: pageForm.page_type });
      setPages((prev) => [page, ...prev]);
      setPageForm({ url: "", page_type: "pricing" });
      setShowAddPage(false);
    } catch (e: any) { setError(e.message); }
    finally { setSubmittingPage(false); }
  };

  const handleCapture = async (pageId: string) => {
    setCapturing(pageId); clearMessages();
    try {
      const res = await pagesApi.captureNow(pageId, true);
      const status = (res as any).status ?? "done";
      setSuccess(status === "no_change" ? "Captured — no changes detected" : "Captured — changes detected!");
      setTimeout(() => setSuccess(null), 4000);
    } catch (e: any) { setError(e.message); }
    finally { setCapturing(null); }
  };

  const handleDeletePage = async (pageId: string) => {
    if (!confirm("Delete this tracked page?")) return;
    try { await pagesApi.delete(pageId); setPages((prev) => prev.filter((p) => p.id !== pageId)); }
    catch (e: any) { setError(e.message); }
  };

  // ── Signal Sources handlers ──
  const handleAddSource = async () => {
    if (!srcForm.source_url.trim()) { setError("Source URL is required."); return; }
    setSubmittingSrc(true); clearMessages();
    try {
      const s = await srcApi.create(id, {
        signal_type: srcForm.signal_type,
        source_url: srcForm.source_url.trim(),
        source_label: srcForm.source_label.trim() || undefined,
      });
      setSources((prev) => [s, ...prev]);
      setSrcForm({ signal_type: "blog_post", source_url: "", source_label: "" });
      setShowAddSource(false);
      setSuccess("Signal source added.");
      setTimeout(() => setSuccess(null), 3000);
    } catch (e: any) { setError(e.message); }
    finally { setSubmittingSrc(false); }
  };

  const handleDeleteSource = async (sourceId: string) => {
    if (!confirm("Delete this signal source?")) return;
    try { await srcApi.delete(sourceId); setSources((prev) => prev.filter((s) => s.id !== sourceId)); }
    catch (e: any) { setError(e.message); }
  };

  const handleToggleSource = async (source: SignalSource) => {
    try {
      const updated = await srcApi.update(source.id, { is_active: !source.is_active });
      setSources((prev) => prev.map((s) => (s.id === source.id ? updated : s)));
    } catch (e: any) { setError(e.message); }
  };

  const handleTestSource = async (sourceId: string) => {
    setTestingId(sourceId);
    try {
      const result = await srcApi.test(sourceId);
      setTestResults((prev) => ({ ...prev, [sourceId]: result }));
    } catch (e: any) { setError(e.message); }
    finally { setTestingId(null); }
  };

  // ── Scan ──
  const handleScan = async () => {
    setScanning(true); clearMessages(); setScanResult(null);
    try {
      const result = await srcApi.scan(id);
      setScanResult(result);
      setSuccess(`Scan complete: ${result.total_events_found} found, ${result.total_events_created} new events created.`);
      // Refresh sources to get updated last_checked_at
      srcApi.list(id).then(setSources).catch(() => {});
    } catch (e: any) { setError(e.message); }
    finally { setScanning(false); }
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
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Link href="/dashboard/competitors" className="rounded-lg border p-1.5 text-gray-400 hover:text-gray-600 hover:bg-gray-50 transition">
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
        <button
          onClick={handleScan}
          disabled={scanning}
          className="inline-flex items-center gap-2 rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50 transition"
        >
          {scanning ? <Loader2 className="h-4 w-4 animate-spin" /> : <Radar className="h-4 w-4" />}
          {scanning ? "Scanning…" : "Scan Signals"}
        </button>
      </div>

      {error && (
        <div className="rounded-lg bg-red-50 border border-red-200 px-4 py-2 text-sm text-red-700">{error}</div>
      )}
      {success && (
        <div className="rounded-lg bg-green-50 border border-green-200 px-4 py-2 text-sm text-green-700">{success}</div>
      )}

      {/* Scan Results */}
      {scanResult && (
        <div className="rounded-xl border-2 border-blue-200 bg-blue-50/50 p-4 space-y-2">
          <h3 className="text-sm font-semibold text-gray-900">Scan Results — {scanResult.competitor_name}</h3>
          <p className="text-xs text-gray-600">
            {scanResult.sources_scanned} sources scanned · {scanResult.total_events_found} signals found · {scanResult.total_events_created} new events
          </p>
          {scanResult.results.length > 0 && (
            <div className="space-y-1 mt-2">
              {scanResult.results.map((r, i) => (
                <div key={i} className="flex items-center gap-2 text-xs">
                  <span className="font-medium text-gray-700 w-20">{r.signal_type}</span>
                  {r.error ? (
                    <span className="text-red-600">Error: {r.error}</span>
                  ) : (
                    <span className="text-gray-600">
                      {r.events_found} found, {r.events_created} new, {r.events_skipped_dedup} dedup
                    </span>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* ════════ Signal Sources ════════ */}
      <div>
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-lg font-semibold text-gray-900">Signal Sources</h2>
          <button
            onClick={() => { setShowAddSource(!showAddSource); clearMessages(); }}
            className="inline-flex items-center gap-1.5 rounded-lg bg-gray-900 px-3 py-1.5 text-xs text-white hover:bg-gray-700 transition"
          >
            <Plus className="h-3 w-3" /> Add Source
          </button>
        </div>

        {showAddSource && (
          <div className="rounded-xl border bg-white p-5 mb-4 space-y-3">
            <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
              <select
                value={srcForm.signal_type}
                onChange={(e) => setSrcForm({ ...srcForm, signal_type: e.target.value })}
                className="rounded-lg border px-3 py-2 text-sm bg-white focus:outline-none focus:ring-2 focus:ring-blue-500"
              >
                {SIGNAL_TYPES.map((t) => (
                  <option key={t.value} value={t.value}>{t.label}</option>
                ))}
              </select>
              <input
                placeholder="Source URL (e.g. https://cursor.com/blog/feed)"
                value={srcForm.source_url}
                onChange={(e) => setSrcForm({ ...srcForm, source_url: e.target.value })}
                onKeyDown={(e) => e.key === "Enter" && handleAddSource()}
                className="rounded-lg border px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
              <input
                placeholder="Label (optional)"
                value={srcForm.source_label}
                onChange={(e) => setSrcForm({ ...srcForm, source_label: e.target.value })}
                className="rounded-lg border px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
            </div>
            <div className="flex gap-2">
              <button onClick={handleAddSource} disabled={submittingSrc}
                className="rounded-lg bg-blue-600 px-3 py-1.5 text-xs text-white hover:bg-blue-500 disabled:opacity-50 transition">
                {submittingSrc ? "Adding…" : "Add Source"}
              </button>
              <button onClick={() => setShowAddSource(false)}
                className="rounded-lg border px-3 py-1.5 text-xs text-gray-600 hover:bg-gray-50 transition">
                Cancel
              </button>
            </div>
          </div>
        )}

        {sources.length === 0 ? (
          <div className="rounded-xl border bg-white p-8 text-center text-sm text-gray-400">
            No signal sources configured. Add sources like blog feeds, careers pages, or review URLs to enable scanning.
          </div>
        ) : (
          <div className="space-y-2">
            {sources.map((s) => {
              const sigLabel = SIGNAL_TYPES.find((t) => t.value === s.signal_type)?.label || s.signal_type;
              const testResult = testResults[s.id];
              const StatusIcon = testResult ? (TEST_STATUS_ICON[testResult.status] || AlertTriangle) : null;
              const statusColor = testResult ? (TEST_STATUS_COLOR[testResult.status] || "text-gray-500") : "";

              return (
                <div key={s.id} className="rounded-xl border bg-white p-4 hover:shadow-sm transition">
                  <div className="flex items-start justify-between">
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 mb-1">
                        <span className="text-xs font-medium bg-purple-50 text-purple-700 px-2 py-0.5 rounded-full">
                          {sigLabel}
                        </span>
                        <span className={`text-xs px-2 py-0.5 rounded-full cursor-pointer ${
                          s.is_active ? "bg-green-50 text-green-700" : "bg-gray-100 text-gray-500"
                        }`} onClick={() => handleToggleSource(s)}>
                          {s.is_active ? "Active" : "Paused"}
                        </span>
                        <span className="text-[10px] text-gray-400">{s.source_kind}</span>
                      </div>
                      <p className="text-sm text-gray-700 truncate">{s.source_url}</p>
                      {s.source_label && <p className="text-xs text-gray-500">{s.source_label}</p>}
                      <div className="flex items-center gap-3 mt-1 text-[10px] text-gray-400">
                        <span>Poll: every {s.poll_interval_hours}h</span>
                        {s.last_checked_at && <span>Checked: {new Date(s.last_checked_at).toLocaleString()}</span>}
                        {s.last_success_at && <span className="text-green-600">Last OK: {new Date(s.last_success_at).toLocaleString()}</span>}
                        {s.last_error && <span className="text-red-500 truncate max-w-[200px]" title={s.last_error}>Error: {s.last_error}</span>}
                      </div>
                    </div>
                    <div className="flex items-center gap-1.5 ml-4">
                      <a href={s.source_url} target="_blank" rel="noopener noreferrer"
                        className="p-1.5 text-gray-400 hover:text-gray-600 transition">
                        <ExternalLink className="h-3.5 w-3.5" />
                      </a>
                      <button onClick={() => handleTestSource(s.id)} disabled={testingId === s.id}
                        className="inline-flex items-center gap-1 rounded-lg border px-2 py-1 text-xs text-gray-600 hover:bg-gray-50 disabled:opacity-50 transition">
                        {testingId === s.id ? <Loader2 className="h-3 w-3 animate-spin" /> : <Play className="h-3 w-3" />}
                        {testingId === s.id ? "Testing…" : "Test"}
                      </button>
                      <button onClick={() => handleDeleteSource(s.id)}
                        className="p-1.5 text-gray-400 hover:text-red-500 transition">
                        <Trash2 className="h-3.5 w-3.5" />
                      </button>
                    </div>
                  </div>
                  {/* Test result inline */}
                  {testResult && (
                    <div className={`mt-2 flex items-center gap-1.5 text-xs ${statusColor}`}>
                      {StatusIcon && <StatusIcon className="h-3.5 w-3.5" />}
                      <span className="font-medium">{testResult.status}</span>
                      <span className="text-gray-500">— {testResult.message}</span>
                      {testResult.items_found > 0 && (
                        <span className="text-gray-600">({testResult.items_found} items)</span>
                      )}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* ════════ Tracked Pages ════════ */}
      <div>
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-lg font-semibold text-gray-900">Tracked Pages</h2>
          <button
            onClick={() => { setShowAddPage(!showAddPage); clearMessages(); }}
            className="inline-flex items-center gap-1.5 rounded-lg bg-gray-900 px-3 py-1.5 text-xs text-white hover:bg-gray-700 transition"
          >
            <Plus className="h-3 w-3" /> Add Page
          </button>
        </div>

        {showAddPage && (
          <div className="rounded-xl border bg-white p-5 mb-4">
            <div className="grid grid-cols-1 md:grid-cols-3 gap-3 mb-3">
              <input
                autoFocus
                placeholder="URL (e.g. https://competitor.com/pricing)"
                value={pageForm.url}
                onChange={(e) => setPageForm({ ...pageForm, url: e.target.value })}
                onKeyDown={(e) => e.key === "Enter" && handleAddPage()}
                className="col-span-2 rounded-lg border px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
              <select
                value={pageForm.page_type}
                onChange={(e) => setPageForm({ ...pageForm, page_type: e.target.value as PageType })}
                className="rounded-lg border px-3 py-2 text-sm bg-white focus:outline-none focus:ring-2 focus:ring-blue-500"
              >
                {PAGE_TYPES.map((t) => (
                  <option key={t} value={t}>{t.replace(/_/g, " ")}</option>
                ))}
              </select>
            </div>
            <div className="flex gap-2">
              <button onClick={handleAddPage} disabled={submittingPage}
                className="rounded-lg bg-blue-600 px-3 py-1.5 text-xs text-white hover:bg-blue-500 disabled:opacity-50 transition">
                {submittingPage ? "Adding…" : "Add Page"}
              </button>
              <button onClick={() => setShowAddPage(false)}
                className="rounded-lg border px-3 py-1.5 text-xs text-gray-600 hover:bg-gray-50 transition">
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
              <div key={p.id} className="rounded-xl border bg-white p-4 flex items-center justify-between hover:shadow-sm transition">
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="text-xs font-medium bg-blue-50 text-blue-700 px-2 py-0.5 rounded-full">
                      {p.page_type.replace(/_/g, " ")}
                    </span>
                    <span className={`text-xs px-2 py-0.5 rounded-full ${
                      p.is_active ? "bg-green-50 text-green-700" : "bg-gray-100 text-gray-500"
                    }`}>
                      {p.is_active ? "Active" : "Paused"}
                    </span>
                  </div>
                  <p className="text-sm text-gray-700 truncate mt-1">{p.url}</p>
                  <p className="text-xs text-gray-400 mt-0.5">
                    Every {p.check_interval_hours}h
                    {p.last_checked_at && ` · Last: ${new Date(p.last_checked_at).toLocaleString()}`}
                  </p>
                </div>
                <div className="flex items-center gap-1.5 ml-4">
                  <a href={p.url} target="_blank" rel="noopener noreferrer"
                    className="p-1.5 text-gray-400 hover:text-gray-600 transition">
                    <ExternalLink className="h-3.5 w-3.5" />
                  </a>
                  <button onClick={() => handleCapture(p.id)} disabled={capturing === p.id}
                    className="inline-flex items-center gap-1 rounded-lg border px-2 py-1 text-xs text-gray-600 hover:bg-gray-50 disabled:opacity-50 transition">
                    <Play className="h-3 w-3" />
                    {capturing === p.id ? "…" : "Capture"}
                  </button>
                  <button onClick={() => handleDeletePage(p.id)}
                    className="p-1.5 text-gray-400 hover:text-red-500 transition">
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
