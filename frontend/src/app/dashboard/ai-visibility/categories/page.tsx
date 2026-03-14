"use client";

import { useState } from "react";
import {
  FolderOpen,
  Plus,
  Pencil,
  Trash2,
  ChevronRight,
  X,
  Tag,
  ListChecks,
} from "lucide-react";
import { useActiveWorkspace, useFetch } from "@/lib/hooks";
import { aiVisibility } from "@/lib/api";
import type { PromptCategory, AITrackedPrompt } from "@/lib/types";

export default function CategoriesPage() {
  const { active, loading: wsLoading } = useActiveWorkspace();
  const wsId = active?.id ?? "";

  const [showCreate, setShowCreate] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editName, setEditName] = useState("");
  const [editDesc, setEditDesc] = useState("");
  const [newName, setNewName] = useState("");
  const [newDesc, setNewDesc] = useState("");
  const [selectedCatId, setSelectedCatId] = useState<string | null>(null);
  const [msg, setMsg] = useState("");
  const [busy, setBusy] = useState(false);

  const { data: categories, loading: catsLoading, refetch: refetchCats } = useFetch(
    () => (wsId ? aiVisibility.listCategories(wsId) : Promise.resolve([])),
    [wsId]
  );

  const { data: allPrompts, loading: promptsLoading, refetch: refetchPrompts } = useFetch(
    () => (wsId ? aiVisibility.listPrompts(wsId) : Promise.resolve([])),
    [wsId]
  );

  if (wsLoading || !active) return <div className="p-8 text-gray-500">Loading workspace…</div>;

  const cats = categories ?? [];
  const prompts = allPrompts ?? [];

  const flash = (m: string) => { setMsg(m); setTimeout(() => setMsg(""), 4000); };

  // Prompt counts per category
  const promptCountMap: Record<string, number> = {};
  const uncategorizedPrompts: AITrackedPrompt[] = [];
  for (const p of prompts) {
    if (p.category_id) {
      promptCountMap[p.category_id] = (promptCountMap[p.category_id] || 0) + 1;
    } else {
      uncategorizedPrompts.push(p);
    }
  }

  // Prompts in selected category
  const selectedCat = cats.find((c) => c.id === selectedCatId);
  const catPrompts = selectedCatId
    ? prompts.filter((p) => p.category_id === selectedCatId)
    : uncategorizedPrompts;

  const handleCreate = async () => {
    if (!newName.trim()) return;
    setBusy(true);
    try {
      await aiVisibility.createCategory(wsId, newName.trim(), newDesc.trim() || undefined);
      setNewName(""); setNewDesc(""); setShowCreate(false);
      flash("Category created");
      refetchCats();
    } catch (e: any) { flash(e.message); }
    setBusy(false);
  };

  const handleRename = async (catId: string) => {
    if (!editName.trim()) return;
    setBusy(true);
    try {
      await aiVisibility.updateCategory(wsId, catId, {
        category_name: editName.trim(),
        description: editDesc.trim() || undefined,
      });
      setEditingId(null);
      flash("Category updated");
      refetchCats();
    } catch (e: any) { flash(e.message); }
    setBusy(false);
  };

  const handleDelete = async (catId: string) => {
    setBusy(true);
    try {
      await aiVisibility.deleteCategory(wsId, catId);
      if (selectedCatId === catId) setSelectedCatId(null);
      flash("Category deleted — prompts unlinked");
      refetchCats(); refetchPrompts();
    } catch (e: any) { flash(e.message); }
    setBusy(false);
  };

  const handleAssign = async (promptId: string, categoryId: string | null) => {
    try {
      await aiVisibility.assignPromptCategory(wsId, promptId, categoryId);
      refetchPrompts();
    } catch (e: any) { flash(e.message); }
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-gray-900 flex items-center gap-2">
            <FolderOpen className="h-5 w-5 text-indigo-600" />
            Prompt Categories
          </h1>
          <p className="text-sm text-gray-500 mt-0.5">
            Group prompts into categories for market-level intelligence
          </p>
        </div>
        <button
          onClick={() => setShowCreate(true)}
          className="flex items-center gap-1.5 rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700 transition"
        >
          <Plus className="h-4 w-4" /> Create Category
        </button>
      </div>

      {msg && (
        <div className="rounded-lg bg-indigo-50 border border-indigo-200 px-4 py-2 text-sm text-indigo-700">{msg}</div>
      )}

      {/* Create form */}
      {showCreate && (
        <div className="rounded-xl border bg-white p-5 space-y-3">
          <h3 className="text-sm font-semibold text-gray-700">New Category</h3>
          <input
            value={newName} onChange={(e) => setNewName(e.target.value)}
            placeholder="Category Name" autoFocus
            className="w-full rounded-lg border px-3 py-2 text-sm focus:ring-2 focus:ring-indigo-500 focus:outline-none"
          />
          <input
            value={newDesc} onChange={(e) => setNewDesc(e.target.value)}
            placeholder="Description (optional)"
            className="w-full rounded-lg border px-3 py-2 text-sm focus:ring-2 focus:ring-indigo-500 focus:outline-none"
          />
          <div className="flex gap-2">
            <button onClick={handleCreate} disabled={busy || !newName.trim()}
              className="rounded-lg bg-indigo-600 px-4 py-1.5 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-50 transition">
              Create
            </button>
            <button onClick={() => setShowCreate(false)}
              className="rounded-lg border px-4 py-1.5 text-sm text-gray-500 hover:bg-gray-50 transition">
              Cancel
            </button>
          </div>
        </div>
      )}

      <div className="grid grid-cols-12 gap-6">
        {/* Left — Category list */}
        <div className="col-span-4 space-y-2">
          {/* Uncategorized section */}
          <button
            onClick={() => setSelectedCatId(null)}
            className={`w-full text-left rounded-xl border p-3 flex items-center justify-between transition ${
              selectedCatId === null ? "border-indigo-300 bg-indigo-50" : "bg-white hover:bg-gray-50"
            }`}
          >
            <div className="flex items-center gap-2">
              <ListChecks className="h-4 w-4 text-gray-400" />
              <span className="text-sm font-medium text-gray-700">Uncategorized</span>
            </div>
            <span className="text-xs text-gray-400">{uncategorizedPrompts.length}</span>
          </button>

          {catsLoading ? (
            <p className="text-xs text-gray-400 text-center py-4">Loading…</p>
          ) : cats.length === 0 ? (
            <p className="text-xs text-gray-400 text-center py-4">No categories yet</p>
          ) : (
            cats.map((cat) => (
              <div key={cat.id}
                className={`rounded-xl border p-3 transition ${
                  selectedCatId === cat.id ? "border-indigo-300 bg-indigo-50" : "bg-white hover:bg-gray-50"
                }`}
              >
                {editingId === cat.id ? (
                  <div className="space-y-2">
                    <input value={editName} onChange={(e) => setEditName(e.target.value)}
                      className="w-full rounded border px-2 py-1 text-sm focus:ring-2 focus:ring-indigo-500 focus:outline-none" autoFocus />
                    <input value={editDesc} onChange={(e) => setEditDesc(e.target.value)}
                      placeholder="Description" className="w-full rounded border px-2 py-1 text-sm focus:ring-2 focus:ring-indigo-500 focus:outline-none" />
                    <div className="flex gap-1">
                      <button onClick={() => handleRename(cat.id)} disabled={busy}
                        className="text-xs bg-indigo-600 text-white px-2 py-0.5 rounded hover:bg-indigo-700">Save</button>
                      <button onClick={() => setEditingId(null)}
                        className="text-xs text-gray-500 px-2 py-0.5 rounded hover:bg-gray-100">Cancel</button>
                    </div>
                  </div>
                ) : (
                  <div className="flex items-center justify-between cursor-pointer" onClick={() => setSelectedCatId(cat.id)}>
                    <div className="flex items-center gap-2 min-w-0">
                      <Tag className="h-4 w-4 text-indigo-500 flex-shrink-0" />
                      <div className="min-w-0">
                        <p className="text-sm font-medium text-gray-700 truncate">{cat.category_name}</p>
                        {cat.description && <p className="text-[11px] text-gray-400 truncate">{cat.description}</p>}
                      </div>
                    </div>
                    <div className="flex items-center gap-1 flex-shrink-0">
                      <span className="text-xs text-gray-400 mr-1">{promptCountMap[cat.id] || 0}</span>
                      <button onClick={(e) => { e.stopPropagation(); setEditingId(cat.id); setEditName(cat.category_name); setEditDesc(cat.description || ""); }}
                        className="p-1 rounded hover:bg-indigo-100 text-gray-400 hover:text-indigo-600 transition" title="Edit">
                        <Pencil className="h-3.5 w-3.5" />
                      </button>
                      <button onClick={(e) => { e.stopPropagation(); handleDelete(cat.id); }}
                        className="p-1 rounded hover:bg-red-50 text-gray-400 hover:text-red-500 transition" title="Delete">
                        <Trash2 className="h-3.5 w-3.5" />
                      </button>
                      <ChevronRight className="h-3.5 w-3.5 text-gray-300" />
                    </div>
                  </div>
                )}
              </div>
            ))
          )}
        </div>

        {/* Right — Prompts in selected category */}
        <div className="col-span-8">
          <div className="rounded-xl border bg-white p-5">
            <h3 className="text-sm font-semibold text-gray-700 mb-1">
              {selectedCat ? selectedCat.category_name : "Uncategorized Prompts"}
            </h3>
            {selectedCat?.description && (
              <p className="text-xs text-gray-400 mb-3">{selectedCat.description}</p>
            )}
            <p className="text-xs text-gray-400 mb-3">{catPrompts.length} prompt(s)</p>

            {promptsLoading ? (
              <p className="text-xs text-gray-400 text-center py-8">Loading…</p>
            ) : catPrompts.length === 0 ? (
              <p className="text-xs text-gray-400 text-center py-8">
                {selectedCat ? "No prompts assigned to this category" : "All prompts are categorized"}
              </p>
            ) : (
              <div className="space-y-2">
                {catPrompts.map((p) => (
                  <div key={p.id} className="flex items-center gap-3 rounded-lg border p-3">
                    <div className={`w-2 h-2 rounded-full flex-shrink-0 ${p.is_active ? "bg-green-500" : "bg-amber-400"}`} />
                    <p className="flex-1 text-sm text-gray-800 truncate">&ldquo;{p.prompt_text}&rdquo;</p>
                    <select
                      value={p.category_id || ""}
                      onChange={(e) => handleAssign(p.id, e.target.value || null)}
                      className="text-xs border rounded px-2 py-1 text-gray-600 focus:ring-2 focus:ring-indigo-500 focus:outline-none"
                    >
                      <option value="">— Uncategorized —</option>
                      {cats.map((c) => (
                        <option key={c.id} value={c.id}>{c.category_name}</option>
                      ))}
                    </select>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
