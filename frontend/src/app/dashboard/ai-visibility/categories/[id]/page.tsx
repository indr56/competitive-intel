"use client";

import { useState, useMemo } from "react";
import { useParams, useRouter } from "next/navigation";
import {
  FolderOpen,
  ArrowLeft,
  BarChart3,
  ListChecks,
  Plus,
  X,
  ArrowRightLeft,
  Trash2,
  TrendingUp,
  Search,
  Check,
} from "lucide-react";
import { useActiveWorkspace, useFetch } from "@/lib/hooks";
import { aiVisibility } from "@/lib/api";
import type { CategoryVisibilityEnriched, AITrackedPrompt } from "@/lib/types";

export default function CategoryDetailPage() {
  const router = useRouter();
  const params = useParams();
  const categoryId = params.id as string;

  const { active, loading: wsLoading } = useActiveWorkspace();
  const wsId = active?.id ?? "";

  const { data: categories, refetch: refetchCats } = useFetch(
    () => (wsId ? aiVisibility.listCategories(wsId) : Promise.resolve([])),
    [wsId]
  );

  const { data: allPrompts, refetch: refetchPrompts } = useFetch(
    () => (wsId ? aiVisibility.listPrompts(wsId) : Promise.resolve([])),
    [wsId]
  );

  const { data: ownershipData, loading: ownershipLoading } = useFetch(
    () =>
      wsId && categoryId
        ? aiVisibility.listCategoryVisibilityEnriched(wsId, categoryId)
        : Promise.resolve([]),
    [wsId, categoryId]
  );

  const [addModalOpen, setAddModalOpen] = useState(false);
  const [movePromptId, setMovePromptId] = useState<string | null>(null);
  const [searchText, setSearchText] = useState("");
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");

  if (wsLoading || !active) return <div className="p-8 text-gray-500">Loading workspace…</div>;

  const cats = categories ?? [];
  const prompts = allPrompts ?? [];
  const ownership = ownershipData ?? [];

  const category = cats.find((c) => c.id === categoryId);
  const catPrompts = prompts.filter((p) => p.category_id === categoryId);

  if (cats.length > 0 && !category) {
    return (
      <div className="p-8 text-center">
        <p className="text-sm text-gray-500">Category not found.</p>
        <button
          onClick={() => router.push("/dashboard/ai-visibility/categories")}
          className="mt-3 text-sm text-indigo-600 hover:underline"
        >
          ← Back to Categories
        </button>
      </div>
    );
  }

  const maxShare = Math.max(...ownership.map((o) => o.visibility_share), 1);

  const flash = (m: string) => { setMsg(m); setTimeout(() => setMsg(""), 3000); };

  const handleRemove = async (promptId: string) => {
    setBusy(true);
    try {
      await aiVisibility.assignPromptCategory(wsId, promptId, null);
      flash("Prompt removed from category");
      refetchPrompts();
    } catch (e: any) { flash(e.message); }
    setBusy(false);
  };

  const handleMove = async (promptId: string, targetCatId: string) => {
    setBusy(true);
    try {
      await aiVisibility.assignPromptCategory(wsId, promptId, targetCatId);
      flash("Prompt moved to new category");
      setMovePromptId(null);
      refetchPrompts();
    } catch (e: any) { flash(e.message); }
    setBusy(false);
  };

  const handleAddPrompts = async () => {
    if (selectedIds.size === 0) return;
    setBusy(true);
    try {
      for (const pid of Array.from(selectedIds)) {
        await aiVisibility.assignPromptCategory(wsId, pid, categoryId);
      }
      flash(`Added ${selectedIds.size} prompt(s) to category`);
      setAddModalOpen(false);
      setSelectedIds(new Set());
      setSearchText("");
      refetchPrompts();
    } catch (e: any) { flash(e.message); }
    setBusy(false);
  };

  // Prompts available to add (not already in this category)
  const availablePrompts = prompts.filter(
    (p) => p.category_id !== categoryId
  );
  const filteredAvailable = searchText
    ? availablePrompts.filter((p) =>
        p.prompt_text.toLowerCase().includes(searchText.toLowerCase())
      )
    : availablePrompts;

  const otherCats = cats.filter((c) => c.id !== categoryId);

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center gap-3">
        <button
          onClick={() => router.push("/dashboard/ai-visibility/categories")}
          className="p-1.5 rounded-lg hover:bg-gray-100 transition"
        >
          <ArrowLeft className="h-4 w-4 text-gray-500" />
        </button>
        <div>
          <h1 className="text-xl font-bold text-gray-900 flex items-center gap-2">
            <FolderOpen className="h-5 w-5 text-indigo-600" />
            {category?.category_name ?? "Loading…"}
          </h1>
          {category?.description && (
            <p className="text-sm text-gray-500 mt-0.5">{category.description}</p>
          )}
        </div>
      </div>

      {msg && (
        <div className="rounded-lg bg-indigo-50 border border-indigo-200 px-4 py-2 text-sm text-indigo-700">{msg}</div>
      )}

      {/* Section 1: Category Overview */}
      <div className="flex gap-4">
        <div className="rounded-xl border bg-white px-5 py-3">
          <p className="text-[11px] font-medium text-gray-400 uppercase">Prompts</p>
          <p className="text-2xl font-bold text-gray-900 mt-0.5">{catPrompts.length}</p>
        </div>
        {ownership.length > 0 && (
          <>
            <div className="rounded-xl border bg-white px-5 py-3">
              <p className="text-[11px] font-medium text-gray-400 uppercase">AI Engines Analyzed</p>
              <p className="text-2xl font-bold text-gray-900 mt-0.5">
                {Math.max(...ownership.map((o) => o.engine_count), 0)}
              </p>
            </div>
            <div className="rounded-xl border bg-white px-5 py-3">
              <p className="text-[11px] font-medium text-gray-400 uppercase">Competitors Tracked</p>
              <p className="text-2xl font-bold text-gray-900 mt-0.5">{ownership.length}</p>
            </div>
          </>
        )}
      </div>

      {/* Section 2: Prompts in this category */}
      <div className="rounded-xl border bg-white p-5">
        <div className="flex items-center justify-between mb-3">
          <h3 className="text-sm font-semibold text-gray-800 flex items-center gap-1.5">
            <ListChecks className="h-4 w-4 text-indigo-500" />
            Prompts in this category
          </h3>
          <button
            onClick={() => { setAddModalOpen(true); setSelectedIds(new Set()); setSearchText(""); }}
            className="flex items-center gap-1 text-xs font-medium text-indigo-600 bg-indigo-50 hover:bg-indigo-100 rounded-lg px-3 py-1.5 transition"
          >
            <Plus className="h-3.5 w-3.5" />
            Add Prompts
          </button>
        </div>

        {catPrompts.length === 0 ? (
          <p className="text-xs text-gray-400 text-center py-6">No prompts assigned to this category yet.</p>
        ) : (
          <div className="space-y-2">
            {catPrompts.map((p) => (
              <div key={p.id} className="flex items-center gap-3 rounded-lg border p-3 group">
                <div className={`w-2 h-2 rounded-full flex-shrink-0 ${p.is_active ? "bg-green-500" : "bg-amber-400"}`} />
                <p className="flex-1 text-sm text-gray-800 truncate">&ldquo;{p.prompt_text}&rdquo;</p>

                {/* Actions */}
                <div className="flex items-center gap-1.5 opacity-0 group-hover:opacity-100 transition">
                  <button
                    onClick={() => handleRemove(p.id)}
                    disabled={busy}
                    className="text-[10px] font-medium px-2 py-1 rounded bg-red-50 text-red-600 hover:bg-red-100 transition disabled:opacity-50"
                    title="Remove from category"
                  >
                    Remove
                  </button>

                  {otherCats.length > 0 && (
                    <div className="relative">
                      <button
                        onClick={() => setMovePromptId(movePromptId === p.id ? null : p.id)}
                        className="text-[10px] font-medium px-2 py-1 rounded bg-amber-50 text-amber-700 hover:bg-amber-100 transition"
                        title="Move to another category"
                      >
                        Move
                      </button>
                      {movePromptId === p.id && (
                        <div className="absolute right-0 top-7 z-20 bg-white border rounded-lg shadow-lg py-1 min-w-[180px]">
                          {otherCats.map((c) => (
                            <button
                              key={c.id}
                              onClick={() => handleMove(p.id, c.id)}
                              className="w-full text-left px-3 py-1.5 text-xs text-gray-700 hover:bg-gray-50 transition"
                            >
                              {c.category_name}
                            </button>
                          ))}
                        </div>
                      )}
                    </div>
                  )}

                  <button
                    onClick={() => router.push("/dashboard/ai-visibility/trends")}
                    className="text-[10px] font-medium px-2 py-1 rounded bg-blue-50 text-blue-600 hover:bg-blue-100 transition"
                    title="View analytics"
                  >
                    Analytics
                  </button>
                </div>

                <span className="text-[11px] text-gray-400">{p.is_active ? "Active" : "Paused"}</span>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Section 3: Category Ownership Distribution */}
      <div className="rounded-xl border bg-white p-5">
        <h3 className="text-sm font-semibold text-gray-800 mb-4 flex items-center gap-1.5">
          <BarChart3 className="h-4 w-4 text-indigo-500" />
          Category Ownership Distribution
        </h3>
        {ownershipLoading ? (
          <p className="text-xs text-gray-400 text-center py-6">Loading ownership data…</p>
        ) : ownership.length === 0 ? (
          <p className="text-xs text-gray-400 text-center py-6">
            No ownership data yet. Run prompts and correlation to generate ownership insights.
          </p>
        ) : (
          <div className="space-y-3">
            {ownership.map((o) => (
              <div key={o.competitor_id} className="flex items-center gap-4">
                <span className="text-sm font-medium text-gray-700 w-36 truncate">{o.competitor_name}</span>
                <div className="flex-1 h-6 bg-gray-100 rounded-full overflow-hidden">
                  <div
                    className="h-full bg-indigo-500 rounded-full transition-all duration-500"
                    style={{ width: `${(o.visibility_share / maxShare) * 100}%` }}
                  />
                </div>
                <span className="text-sm font-semibold text-gray-800 w-14 text-right">
                  {o.visibility_share.toFixed(1)}%
                </span>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Add Prompts Modal */}
      {addModalOpen && (
        <>
          <div className="fixed inset-0 bg-black/20 z-40" onClick={() => setAddModalOpen(false)} />
          <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
            <div className="bg-white rounded-xl shadow-2xl w-full max-w-lg max-h-[70vh] flex flex-col">
              <div className="flex items-center justify-between px-5 py-3 border-b">
                <h3 className="text-sm font-bold text-gray-900">Select prompts to add</h3>
                <button onClick={() => setAddModalOpen(false)} className="p-1 rounded hover:bg-gray-100">
                  <X className="h-4 w-4 text-gray-500" />
                </button>
              </div>

              <div className="px-5 pt-3">
                <div className="relative">
                  <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-gray-400" />
                  <input
                    type="text"
                    placeholder="Search prompts…"
                    value={searchText}
                    onChange={(e) => setSearchText(e.target.value)}
                    className="w-full pl-9 pr-3 py-2 text-sm border rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-300"
                  />
                </div>
              </div>

              <div className="flex-1 overflow-y-auto px-5 py-3 space-y-1">
                {filteredAvailable.length === 0 ? (
                  <p className="text-xs text-gray-400 text-center py-6">No available prompts to add.</p>
                ) : (
                  filteredAvailable.map((p) => {
                    const selected = selectedIds.has(p.id);
                    return (
                      <button
                        key={p.id}
                        onClick={() => {
                          const next = new Set(selectedIds);
                          if (selected) next.delete(p.id); else next.add(p.id);
                          setSelectedIds(next);
                        }}
                        className={`w-full text-left flex items-center gap-3 rounded-lg border p-3 transition ${
                          selected ? "border-indigo-300 bg-indigo-50" : "hover:bg-gray-50"
                        }`}
                      >
                        <div className={`w-4 h-4 rounded border flex items-center justify-center flex-shrink-0 ${
                          selected ? "bg-indigo-600 border-indigo-600" : "border-gray-300"
                        }`}>
                          {selected && <Check className="h-3 w-3 text-white" />}
                        </div>
                        <span className="text-sm text-gray-800 truncate flex-1">{p.prompt_text}</span>
                        <span className="text-[10px] text-gray-400">
                          {p.category_name ?? "Uncategorized"}
                        </span>
                      </button>
                    );
                  })
                )}
              </div>

              <div className="px-5 py-3 border-t flex items-center justify-between">
                <span className="text-xs text-gray-500">{selectedIds.size} selected</span>
                <button
                  onClick={handleAddPrompts}
                  disabled={selectedIds.size === 0 || busy}
                  className="text-sm font-medium px-4 py-2 rounded-lg bg-indigo-600 text-white hover:bg-indigo-700 transition disabled:opacity-50"
                >
                  Add to category
                </button>
              </div>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
