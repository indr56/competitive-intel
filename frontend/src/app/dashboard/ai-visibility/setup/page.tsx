"use client";

import { useEffect, useState } from "react";
import {
  Search,
  Plus,
  Sparkles,
  Check,
  X,
  Tag,
  Trash2,
  RefreshCw,
} from "lucide-react";
import { useActiveWorkspace, useFetch } from "@/lib/hooks";
import { aiVisibility } from "@/lib/api";
import type { AIKeyword, AIPromptSource } from "@/lib/types";

const SOURCE_TABS = [
  { key: "all", label: "All" },
  { key: "manual", label: "Manual" },
  { key: "competitor", label: "Competitor" },
  { key: "keyword", label: "Keywords" },
  { key: "template", label: "Templates" },
];

export default function PromptSetupPage() {
  const { active, loading: wsLoading } = useActiveWorkspace();
  const wsId = active?.id ?? "";

  const [tab, setTab] = useState("all");
  const [newPrompt, setNewPrompt] = useState("");
  const [newKeyword, setNewKeyword] = useState("");
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");

  // Fetch suggestions
  const {
    data: suggestions,
    loading: sugLoading,
    refetch: refetchSuggestions,
  } = useFetch(
    () =>
      wsId
        ? aiVisibility.listSuggestions(wsId, tab === "all" ? undefined : tab, "suggested")
        : Promise.resolve([]),
    [wsId, tab]
  );

  // Fetch keywords
  const {
    data: keywords,
    loading: kwLoading,
    refetch: refetchKeywords,
  } = useFetch(() => (wsId ? aiVisibility.listKeywords(wsId) : Promise.resolve([])), [wsId]);

  // Fetch limits
  const { data: limits } = useFetch(
    () => (wsId ? aiVisibility.getPromptLimits(wsId) : Promise.resolve(null)),
    [wsId]
  );

  if (wsLoading || !active) {
    return <div className="p-8 text-gray-500">Loading workspace…</div>;
  }

  const flash = (m: string) => {
    setMsg(m);
    setTimeout(() => setMsg(""), 3000);
  };

  const handleAddManual = async () => {
    if (!newPrompt.trim()) return;
    setBusy(true);
    try {
      await aiVisibility.addSuggestion(wsId, newPrompt.trim(), "manual");
      setNewPrompt("");
      refetchSuggestions();
      flash("Suggestion added");
    } catch (e: any) {
      flash(e.message);
    }
    setBusy(false);
  };

  const handleGenerate = async () => {
    setBusy(true);
    try {
      const res = await aiVisibility.generateSuggestions(wsId);
      refetchSuggestions();
      flash(`Generated ${res.suggestions_created} suggestions`);
    } catch (e: any) {
      flash(e.message);
    }
    setBusy(false);
  };

  const handleApprove = async () => {
    if (selected.size === 0) return;
    setBusy(true);
    try {
      await aiVisibility.approveSuggestions(wsId, Array.from(selected));
      setSelected(new Set());
      refetchSuggestions();
      flash(`Approved ${selected.size} prompts`);
    } catch (e: any) {
      flash(e.message);
    }
    setBusy(false);
  };

  const handleReject = async () => {
    if (selected.size === 0) return;
    setBusy(true);
    try {
      await aiVisibility.rejectSuggestions(wsId, Array.from(selected));
      setSelected(new Set());
      refetchSuggestions();
      flash(`Rejected ${selected.size} prompts`);
    } catch (e: any) {
      flash(e.message);
    }
    setBusy(false);
  };

  const handleAddKeyword = async () => {
    if (!newKeyword.trim()) return;
    setBusy(true);
    try {
      await aiVisibility.addKeyword(wsId, newKeyword.trim());
      setNewKeyword("");
      refetchKeywords();
      flash("Keyword added");
    } catch (e: any) {
      flash(e.message);
    }
    setBusy(false);
  };

  const handleExtractKeywords = async () => {
    setBusy(true);
    try {
      const res = await aiVisibility.extractKeywords(wsId);
      refetchKeywords();
      flash(`Extracted ${res.keywords_created} keywords`);
    } catch (e: any) {
      flash(e.message);
    }
    setBusy(false);
  };

  const handleDeleteKeyword = async (kwId: string) => {
    try {
      await aiVisibility.deleteKeyword(wsId, kwId);
      refetchKeywords();
    } catch {}
  };

  const handleApproveKeywords = async () => {
    const unapproved = (keywords ?? []).filter((k) => !k.is_approved);
    if (unapproved.length === 0) return;
    setBusy(true);
    try {
      await aiVisibility.approveKeywords(
        wsId,
        unapproved.map((k) => k.id)
      );
      refetchKeywords();
      flash(`Approved ${unapproved.length} keywords`);
    } catch (e: any) {
      flash(e.message);
    }
    setBusy(false);
  };

  const toggleSelect = (id: string) => {
    const next = new Set(selected);
    next.has(id) ? next.delete(id) : next.add(id);
    setSelected(next);
  };

  const selectAll = () => {
    if (!suggestions) return;
    if (selected.size === suggestions.length) {
      setSelected(new Set());
    } else {
      setSelected(new Set(suggestions.map((s) => s.id)));
    }
  };

  const items = suggestions ?? [];

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-gray-900 flex items-center gap-2">
            <Search className="h-5 w-5 text-violet-600" />
            Prompt Setup
          </h1>
          <p className="text-sm text-gray-500 mt-0.5">
            Suggest, review, and approve prompts for AI visibility tracking
          </p>
        </div>
        {limits && (
          <div className="text-xs text-gray-500 bg-gray-50 rounded-lg px-3 py-2">
            <span className="font-semibold text-gray-700">{limits.used}</span> / {limits.limit} prompts used
            <span className="ml-1 text-gray-400">({limits.plan})</span>
          </div>
        )}
      </div>

      {msg && (
        <div className="rounded-lg bg-violet-50 border border-violet-200 px-4 py-2 text-sm text-violet-700">
          {msg}
        </div>
      )}

      {/* Keywords Section */}
      <div className="rounded-xl border bg-white p-5">
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-sm font-semibold text-gray-800 flex items-center gap-1.5">
            <Tag className="h-4 w-4 text-violet-500" />
            Keywords
          </h2>
          <div className="flex gap-2">
            <button
              onClick={handleExtractKeywords}
              disabled={busy}
              className="text-xs bg-gray-100 hover:bg-gray-200 text-gray-700 rounded-md px-2.5 py-1.5 flex items-center gap-1 transition disabled:opacity-50"
            >
              <Sparkles className="h-3 w-3" /> Auto-Extract
            </button>
            <button
              onClick={handleApproveKeywords}
              disabled={busy}
              className="text-xs bg-violet-100 hover:bg-violet-200 text-violet-700 rounded-md px-2.5 py-1.5 flex items-center gap-1 transition disabled:opacity-50"
            >
              <Check className="h-3 w-3" /> Approve All
            </button>
          </div>
        </div>

        <div className="flex gap-2 mb-3">
          <input
            value={newKeyword}
            onChange={(e) => setNewKeyword(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleAddKeyword()}
            placeholder="Add keyword…"
            className="flex-1 rounded-md border px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-violet-300"
          />
          <button
            onClick={handleAddKeyword}
            disabled={busy}
            className="bg-violet-600 text-white rounded-md px-3 py-1.5 text-sm hover:bg-violet-700 transition disabled:opacity-50"
          >
            <Plus className="h-4 w-4" />
          </button>
        </div>

        {kwLoading ? (
          <p className="text-xs text-gray-400">Loading…</p>
        ) : (
          <div className="flex flex-wrap gap-2">
            {(keywords ?? []).map((kw) => (
              <span
                key={kw.id}
                className={`inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-xs font-medium ${
                  kw.is_approved
                    ? "bg-violet-100 text-violet-700"
                    : "bg-gray-100 text-gray-600 border border-dashed border-gray-300"
                }`}
              >
                {kw.keyword}
                {!kw.is_approved && (
                  <span className="text-[10px] text-gray-400">(pending)</span>
                )}
                <button
                  onClick={() => handleDeleteKeyword(kw.id)}
                  className="ml-0.5 text-gray-400 hover:text-red-500"
                >
                  <X className="h-3 w-3" />
                </button>
              </span>
            ))}
            {(keywords ?? []).length === 0 && (
              <p className="text-xs text-gray-400">
                No keywords yet. Add manually or auto-extract from competitor content.
              </p>
            )}
          </div>
        )}
      </div>

      {/* Prompt Suggestions */}
      <div className="rounded-xl border bg-white p-5">
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-sm font-semibold text-gray-800">Prompt Suggestions</h2>
          <div className="flex gap-2">
            <button
              onClick={handleGenerate}
              disabled={busy}
              className="text-xs bg-violet-600 hover:bg-violet-700 text-white rounded-md px-3 py-1.5 flex items-center gap-1 transition disabled:opacity-50"
            >
              <Sparkles className="h-3 w-3" /> Generate
            </button>
          </div>
        </div>

        {/* Add manual prompt */}
        <div className="flex gap-2 mb-4">
          <input
            value={newPrompt}
            onChange={(e) => setNewPrompt(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleAddManual()}
            placeholder="Type a custom prompt… (e.g. best CRM tools for startups)"
            className="flex-1 rounded-md border px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-violet-300"
          />
          <button
            onClick={handleAddManual}
            disabled={busy}
            className="bg-violet-600 text-white rounded-md px-4 py-2 text-sm hover:bg-violet-700 transition disabled:opacity-50"
          >
            Add
          </button>
        </div>

        {/* Source tabs */}
        <div className="flex gap-1 border-b mb-3">
          {SOURCE_TABS.map((t) => (
            <button
              key={t.key}
              onClick={() => setTab(t.key)}
              className={`px-3 py-1.5 text-xs font-medium rounded-t-md transition ${
                tab === t.key
                  ? "bg-violet-50 text-violet-700 border-b-2 border-violet-600"
                  : "text-gray-500 hover:text-gray-700"
              }`}
            >
              {t.label}
            </button>
          ))}
        </div>

        {/* Bulk actions */}
        {items.length > 0 && (
          <div className="flex items-center gap-2 mb-3">
            <button onClick={selectAll} className="text-xs text-gray-500 hover:text-gray-700">
              {selected.size === items.length ? "Deselect all" : "Select all"}
            </button>
            {selected.size > 0 && (
              <>
                <button
                  onClick={handleApprove}
                  disabled={busy}
                  className="text-xs bg-green-600 text-white rounded-md px-2.5 py-1 flex items-center gap-1 hover:bg-green-700 disabled:opacity-50"
                >
                  <Check className="h-3 w-3" /> Approve ({selected.size})
                </button>
                <button
                  onClick={handleReject}
                  disabled={busy}
                  className="text-xs bg-red-500 text-white rounded-md px-2.5 py-1 flex items-center gap-1 hover:bg-red-600 disabled:opacity-50"
                >
                  <X className="h-3 w-3" /> Reject ({selected.size})
                </button>
              </>
            )}
          </div>
        )}

        {/* Suggestion list */}
        {sugLoading ? (
          <p className="text-sm text-gray-400">Loading…</p>
        ) : items.length === 0 ? (
          <div className="text-center py-8 text-sm text-gray-400">
            No suggestions yet. Click <strong>Generate</strong> to create prompt suggestions from your keywords and competitors.
          </div>
        ) : (
          <ul className="divide-y">
            {items.map((s) => (
              <li
                key={s.id}
                className="flex items-center gap-3 py-2.5 hover:bg-gray-50 rounded-md px-2 -mx-2"
              >
                <input
                  type="checkbox"
                  checked={selected.has(s.id)}
                  onChange={() => toggleSelect(s.id)}
                  className="rounded border-gray-300 text-violet-600 focus:ring-violet-500"
                />
                <div className="flex-1 min-w-0">
                  <p className="text-sm text-gray-800 truncate">&ldquo;{s.prompt_text}&rdquo;</p>
                  <p className="text-[11px] text-gray-400 mt-0.5">
                    Source: <span className="font-medium text-gray-500">{s.source_type}</span>
                    {s.source_detail && (
                      <span className="ml-2">
                        {Object.entries(s.source_detail)
                          .filter(([k]) => k !== "template")
                          .map(([k, v]) => `${k}: ${v}`)
                          .join(", ")}
                      </span>
                    )}
                  </p>
                </div>
                <span
                  className={`text-[10px] font-medium px-2 py-0.5 rounded-full ${
                    s.status === "suggested"
                      ? "bg-amber-50 text-amber-600"
                      : s.status === "approved"
                      ? "bg-green-50 text-green-600"
                      : "bg-red-50 text-red-600"
                  }`}
                >
                  {s.status}
                </span>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
