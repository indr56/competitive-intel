"use client";

import { useState } from "react";
import {
  ListChecks,
  Play,
  Pause,
  Trash2,
  RefreshCw,
  Clock,
  CheckCircle2,
  XCircle,
  Tag,
} from "lucide-react";
import { useActiveWorkspace, useFetch } from "@/lib/hooks";
import { aiVisibility } from "@/lib/api";
import type { AITrackedPrompt, PromptCategory } from "@/lib/types";

const ENGINE_COLORS: Record<string, string> = {
  chatgpt: "bg-green-100 text-green-700",
  perplexity: "bg-blue-100 text-blue-700",
  claude: "bg-orange-100 text-orange-700",
  gemini: "bg-purple-100 text-purple-700",
};

export default function TrackedPromptsPage() {
  const { active, loading: wsLoading } = useActiveWorkspace();
  const wsId = active?.id ?? "";

  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");
  const [runningId, setRunningId] = useState<string | null>(null);

  const {
    data: prompts,
    loading,
    refetch,
  } = useFetch(
    () => (wsId ? aiVisibility.listPrompts(wsId) : Promise.resolve([])),
    [wsId]
  );

  const { data: limits, refetch: refetchLimits } = useFetch(
    () => (wsId ? aiVisibility.getPromptLimits(wsId) : Promise.resolve(null)),
    [wsId]
  );

  const { data: categories } = useFetch(
    () => (wsId ? aiVisibility.listCategories(wsId) : Promise.resolve([])),
    [wsId]
  );

  const cats = categories ?? [];

  if (wsLoading || !active) {
    return <div className="p-8 text-gray-500">Loading workspace…</div>;
  }

  const flash = (m: string) => {
    setMsg(m);
    setTimeout(() => setMsg(""), 4000);
  };

  const handleRunAll = async () => {
    setBusy(true);
    try {
      const res = await aiVisibility.runAllPrompts(wsId);
      flash(res.message);
      refetch();
    } catch (e: any) {
      flash(e.message);
    }
    setBusy(false);
  };

  const handleRunOne = async (promptId: string) => {
    setRunningId(promptId);
    try {
      const res = await aiVisibility.runSinglePrompt(wsId, promptId);
      flash(res.message);
      refetch();
    } catch (e: any) {
      flash(e.message);
    }
    setRunningId(null);
  };

  const handlePause = async (promptId: string) => {
    try {
      await aiVisibility.pausePrompt(wsId, promptId);
      refetch();
    } catch {}
  };

  const handleDelete = async (promptId: string) => {
    try {
      await aiVisibility.deletePrompt(wsId, promptId);
      refetch();
      refetchLimits();
    } catch {}
  };

  const handleAssignCategory = async (promptId: string, categoryId: string | null) => {
    try {
      await aiVisibility.assignPromptCategory(wsId, promptId, categoryId);
      refetch();
    } catch (e: any) {
      flash(e.message);
    }
  };

  const items = prompts ?? [];
  const activeCount = items.filter((p) => p.is_active).length;
  const pausedCount = items.filter((p) => !p.is_active).length;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-gray-900 flex items-center gap-2">
            <ListChecks className="h-5 w-5 text-violet-600" />
            Tracked Prompts
          </h1>
          <p className="text-sm text-gray-500 mt-0.5">
            Manage approved prompts that run daily across AI engines
          </p>
        </div>
        <div className="flex items-center gap-3">
          {limits && (
            <div className="text-xs text-gray-500 bg-gray-50 rounded-lg px-3 py-2">
              <span className="font-semibold text-gray-700">{limits.used}</span> / {limits.limit}
              <span className="ml-1 text-gray-400">({limits.plan})</span>
            </div>
          )}
          <button
            onClick={handleRunAll}
            disabled={busy || activeCount === 0}
            className="flex items-center gap-1.5 rounded-lg bg-violet-600 px-4 py-2 text-sm font-medium text-white hover:bg-violet-700 transition disabled:opacity-50"
          >
            <Play className="h-4 w-4" />
            Run All Now
          </button>
        </div>
      </div>

      {msg && (
        <div className="rounded-lg bg-violet-50 border border-violet-200 px-4 py-2 text-sm text-violet-700">
          {msg}
        </div>
      )}

      {/* Stats bar */}
      <div className="flex gap-4">
        <div className="flex items-center gap-1.5 text-xs text-gray-500">
          <CheckCircle2 className="h-3.5 w-3.5 text-green-500" />
          {activeCount} active
        </div>
        <div className="flex items-center gap-1.5 text-xs text-gray-500">
          <Pause className="h-3.5 w-3.5 text-amber-500" />
          {pausedCount} paused
        </div>
        <div className="flex items-center gap-1.5 text-xs text-gray-500">
          <Clock className="h-3.5 w-3.5 text-gray-400" />
          Runs daily at 2:00 AM UTC
        </div>
      </div>

      {/* Prompt list */}
      {loading ? (
        <div className="text-sm text-gray-400 py-8 text-center">Loading…</div>
      ) : items.length === 0 ? (
        <div className="rounded-xl border bg-white p-8 text-center">
          <ListChecks className="h-10 w-10 text-gray-300 mx-auto mb-3" />
          <p className="text-sm text-gray-500">
            No tracked prompts yet. Go to{" "}
            <a href="/dashboard/ai-visibility/setup" className="text-violet-600 underline">
              Prompt Setup
            </a>{" "}
            to generate and approve prompts.
          </p>
        </div>
      ) : (
        <div className="space-y-2">
          {items.map((p) => (
            <div
              key={p.id}
              className={`rounded-xl border bg-white p-4 flex items-center gap-4 transition ${
                p.is_active ? "" : "opacity-60"
              }`}
            >
              {/* Status indicator */}
              <div className={`w-2 h-2 rounded-full flex-shrink-0 ${p.is_active ? "bg-green-500" : "bg-amber-400"}`} />

              {/* Content */}
              <div className="flex-1 min-w-0">
                <p className="text-sm font-medium text-gray-800 truncate">
                  &ldquo;{p.prompt_text}&rdquo;
                </p>
                <div className="flex items-center gap-3 mt-1">
                  <span className="text-[11px] text-gray-400">
                    Source: <span className="font-medium text-gray-500">{p.source_type}</span>
                  </span>
                  {p.last_run_at && (
                    <span className="text-[11px] text-gray-400 flex items-center gap-0.5">
                      <Clock className="h-3 w-3" />
                      Last run: {new Date(p.last_run_at).toLocaleDateString()}
                    </span>
                  )}
                </div>
              </div>

              {/* Category dropdown */}
              <div className="flex items-center gap-1.5 flex-shrink-0">
                <Tag className="h-3.5 w-3.5 text-gray-400" />
                <select
                  value={p.category_id || ""}
                  onChange={(e) => handleAssignCategory(p.id, e.target.value || null)}
                  className="text-xs border rounded px-2 py-1 text-gray-600 focus:ring-2 focus:ring-violet-500 focus:outline-none max-w-[140px]"
                >
                  <option value="">—</option>
                  {cats.map((c) => (
                    <option key={c.id} value={c.id}>{c.category_name}</option>
                  ))}
                </select>
              </div>

              {/* Actions */}
              <div className="flex items-center gap-1.5 flex-shrink-0">
                <button
                  onClick={() => handleRunOne(p.id)}
                  disabled={runningId === p.id || !p.is_active}
                  className="p-1.5 rounded-md hover:bg-violet-50 text-violet-600 transition disabled:opacity-40"
                  title="Run Now"
                >
                  {runningId === p.id ? (
                    <RefreshCw className="h-4 w-4 animate-spin" />
                  ) : (
                    <Play className="h-4 w-4" />
                  )}
                </button>
                <button
                  onClick={() => handlePause(p.id)}
                  className="p-1.5 rounded-md hover:bg-amber-50 text-amber-600 transition"
                  title={p.is_active ? "Pause" : "Resume"}
                >
                  {p.is_active ? <Pause className="h-4 w-4" /> : <Play className="h-4 w-4" />}
                </button>
                <button
                  onClick={() => handleDelete(p.id)}
                  className="p-1.5 rounded-md hover:bg-red-50 text-red-500 transition"
                  title="Delete"
                >
                  <Trash2 className="h-4 w-4" />
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
