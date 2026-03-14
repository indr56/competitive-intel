"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import {
  FolderOpen,
  Plus,
  Pencil,
  Trash2,
  X,
  AlertTriangle,
} from "lucide-react";
import { useActiveWorkspace, useFetch } from "@/lib/hooks";
import { aiVisibility } from "@/lib/api";
import type { PromptCategory, AITrackedPrompt } from "@/lib/types";

export default function CategoriesPage() {
  const router = useRouter();
  const { active, loading: wsLoading } = useActiveWorkspace();
  const wsId = active?.id ?? "";

  const [showCreate, setShowCreate] = useState(false);
  const [editCat, setEditCat] = useState<PromptCategory | null>(null);
  const [deleteCat, setDeleteCat] = useState<PromptCategory | null>(null);
  const [formName, setFormName] = useState("");
  const [formDesc, setFormDesc] = useState("");
  const [msg, setMsg] = useState("");
  const [busy, setBusy] = useState(false);

  const { data: categories, loading: catsLoading, refetch: refetchCats } = useFetch(
    () => (wsId ? aiVisibility.listCategories(wsId) : Promise.resolve([])),
    [wsId]
  );

  const { data: allPrompts, refetch: refetchPrompts } = useFetch(
    () => (wsId ? aiVisibility.listPrompts(wsId) : Promise.resolve([])),
    [wsId]
  );

  if (wsLoading || !active) return <div className="p-8 text-gray-500">Loading workspace…</div>;

  const cats = categories ?? [];
  const prompts = allPrompts ?? [];

  const flash = (m: string) => { setMsg(m); setTimeout(() => setMsg(""), 4000); };

  const promptCountMap: Record<string, number> = {};
  for (const p of prompts) {
    if (p.category_id) {
      promptCountMap[p.category_id] = (promptCountMap[p.category_id] || 0) + 1;
    }
  }

  const openCreate = () => {
    setFormName(""); setFormDesc(""); setShowCreate(true);
  };

  const openEdit = (cat: PromptCategory) => {
    setFormName(cat.category_name); setFormDesc(cat.description || ""); setEditCat(cat);
  };

  const handleCreate = async () => {
    if (!formName.trim()) return;
    setBusy(true);
    try {
      await aiVisibility.createCategory(wsId, formName.trim(), formDesc.trim() || undefined);
      setShowCreate(false);
      flash("Category created");
      refetchCats();
    } catch (e: any) { flash(e.message); }
    setBusy(false);
  };

  const handleUpdate = async () => {
    if (!editCat || !formName.trim()) return;
    setBusy(true);
    try {
      await aiVisibility.updateCategory(wsId, editCat.id, {
        category_name: formName.trim(),
        description: formDesc.trim() || undefined,
      });
      setEditCat(null);
      flash("Category updated");
      refetchCats();
    } catch (e: any) { flash(e.message); }
    setBusy(false);
  };

  const handleDelete = async () => {
    if (!deleteCat) return;
    setBusy(true);
    try {
      await aiVisibility.deleteCategory(wsId, deleteCat.id);
      setDeleteCat(null);
      flash("Category deleted — prompts moved to Uncategorized");
      refetchCats(); refetchPrompts();
    } catch (e: any) { flash(e.message); }
    setBusy(false);
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
            Create and manage categories to group prompts into AI market segments
          </p>
        </div>
        <button
          onClick={openCreate}
          className="flex items-center gap-1.5 rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700 transition"
        >
          <Plus className="h-4 w-4" /> Create Category
        </button>
      </div>

      {msg && (
        <div className="rounded-lg bg-indigo-50 border border-indigo-200 px-4 py-2 text-sm text-indigo-700">{msg}</div>
      )}

      {/* Category Table */}
      {catsLoading ? (
        <div className="text-sm text-gray-400 py-8 text-center">Loading categories…</div>
      ) : cats.length === 0 ? (
        <div className="rounded-xl border bg-white p-8 text-center">
          <FolderOpen className="h-10 w-10 text-gray-300 mx-auto mb-3" />
          <p className="text-sm text-gray-500">
            No categories yet. Click <strong>+ Create Category</strong> to get started.
          </p>
          <p className="text-xs text-gray-400 mt-1">
            Categories represent AI market segments like &ldquo;AI Code Editors&rdquo; or &ldquo;AI Writing Tools&rdquo;.
          </p>
        </div>
      ) : (
        <div className="rounded-xl border bg-white overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-[11px] text-gray-400 uppercase border-b bg-gray-50/50">
                <th className="px-5 py-3 text-left font-medium">Category Name</th>
                <th className="px-5 py-3 text-left font-medium">Description</th>
                <th className="px-5 py-3 text-center font-medium">Prompts</th>
                <th className="px-5 py-3 text-left font-medium">Created</th>
                <th className="px-5 py-3 text-right font-medium">Actions</th>
              </tr>
            </thead>
            <tbody>
              {cats.map((cat) => (
                <tr
                  key={cat.id}
                  onClick={() => router.push(`/dashboard/ai-visibility/categories/${cat.id}`)}
                  className="border-b last:border-0 hover:bg-indigo-50/50 cursor-pointer transition"
                >
                  <td className="px-5 py-3">
                    <span className="font-medium text-gray-800">{cat.category_name}</span>
                  </td>
                  <td className="px-5 py-3 text-gray-500 max-w-[250px] truncate">
                    {cat.description || <span className="text-gray-300 italic">—</span>}
                  </td>
                  <td className="px-5 py-3 text-center">
                    <span className="inline-flex items-center justify-center min-w-[28px] rounded-full bg-indigo-100 text-indigo-700 text-xs font-semibold px-2 py-0.5">
                      {promptCountMap[cat.id] || 0}
                    </span>
                  </td>
                  <td className="px-5 py-3 text-gray-400 text-xs">
                    {new Date(cat.created_at).toLocaleDateString("en-US", { month: "short", day: "numeric" })}
                  </td>
                  <td className="px-5 py-3 text-right">
                    <div className="flex items-center justify-end gap-1">
                      <button
                        onClick={(e) => { e.stopPropagation(); openEdit(cat); }}
                        className="p-1.5 rounded-md hover:bg-indigo-100 text-gray-400 hover:text-indigo-600 transition"
                        title="Edit"
                      >
                        <Pencil className="h-3.5 w-3.5" />
                      </button>
                      <button
                        onClick={(e) => { e.stopPropagation(); setDeleteCat(cat); }}
                        className="p-1.5 rounded-md hover:bg-red-50 text-gray-400 hover:text-red-500 transition"
                        title="Delete"
                      >
                        <Trash2 className="h-3.5 w-3.5" />
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Create Modal */}
      {showCreate && (
        <Modal title="Create Category" onClose={() => setShowCreate(false)}>
          <div className="space-y-3">
            <div>
              <label className="block text-xs font-medium text-gray-500 mb-1">Category Name *</label>
              <input
                value={formName} onChange={(e) => setFormName(e.target.value)}
                placeholder="e.g. AI Code Editors" autoFocus
                className="w-full rounded-lg border px-3 py-2 text-sm focus:ring-2 focus:ring-indigo-500 focus:outline-none"
              />
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-500 mb-1">Description</label>
              <input
                value={formDesc} onChange={(e) => setFormDesc(e.target.value)}
                placeholder="e.g. Prompts related to coding assistant tools"
                className="w-full rounded-lg border px-3 py-2 text-sm focus:ring-2 focus:ring-indigo-500 focus:outline-none"
              />
            </div>
            <div className="flex justify-end gap-2 pt-2">
              <button onClick={() => setShowCreate(false)}
                className="rounded-lg border px-4 py-2 text-sm text-gray-500 hover:bg-gray-50 transition">
                Cancel
              </button>
              <button onClick={handleCreate} disabled={busy || !formName.trim()}
                className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-50 transition">
                Create
              </button>
            </div>
          </div>
        </Modal>
      )}

      {/* Edit Modal */}
      {editCat && (
        <Modal title="Edit Category" onClose={() => setEditCat(null)}>
          <div className="space-y-3">
            <div>
              <label className="block text-xs font-medium text-gray-500 mb-1">Category Name *</label>
              <input
                value={formName} onChange={(e) => setFormName(e.target.value)}
                autoFocus
                className="w-full rounded-lg border px-3 py-2 text-sm focus:ring-2 focus:ring-indigo-500 focus:outline-none"
              />
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-500 mb-1">Description</label>
              <input
                value={formDesc} onChange={(e) => setFormDesc(e.target.value)}
                placeholder="Description (optional)"
                className="w-full rounded-lg border px-3 py-2 text-sm focus:ring-2 focus:ring-indigo-500 focus:outline-none"
              />
            </div>
            <div className="flex justify-end gap-2 pt-2">
              <button onClick={() => setEditCat(null)}
                className="rounded-lg border px-4 py-2 text-sm text-gray-500 hover:bg-gray-50 transition">
                Cancel
              </button>
              <button onClick={handleUpdate} disabled={busy || !formName.trim()}
                className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-50 transition">
                Save Changes
              </button>
            </div>
          </div>
        </Modal>
      )}

      {/* Delete Confirmation Dialog */}
      {deleteCat && (
        <Modal title="Delete Category" onClose={() => setDeleteCat(null)}>
          <div className="space-y-4">
            <div className="flex items-start gap-3">
              <div className="flex-shrink-0 w-10 h-10 rounded-full bg-red-100 flex items-center justify-center">
                <AlertTriangle className="h-5 w-5 text-red-600" />
              </div>
              <div>
                <p className="text-sm text-gray-700">
                  Are you sure you want to delete <strong>&ldquo;{deleteCat.category_name}&rdquo;</strong>?
                </p>
                <p className="text-xs text-gray-400 mt-1">
                  {promptCountMap[deleteCat.id] || 0} prompt(s) in this category will become Uncategorized. No prompts will be deleted.
                </p>
              </div>
            </div>
            <div className="flex justify-end gap-2">
              <button onClick={() => setDeleteCat(null)}
                className="rounded-lg border px-4 py-2 text-sm text-gray-500 hover:bg-gray-50 transition">
                Cancel
              </button>
              <button onClick={handleDelete} disabled={busy}
                className="rounded-lg bg-red-600 px-4 py-2 text-sm font-medium text-white hover:bg-red-700 disabled:opacity-50 transition">
                Delete Category
              </button>
            </div>
          </div>
        </Modal>
      )}
    </div>
  );
}


function Modal({ title, onClose, children }: { title: string; onClose: () => void; children: React.ReactNode }) {
  return (
    <>
      <div className="fixed inset-0 bg-black/30 z-40" onClick={onClose} />
      <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
        <div className="bg-white rounded-xl shadow-xl w-full max-w-md p-6" onClick={(e) => e.stopPropagation()}>
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-base font-bold text-gray-900">{title}</h3>
            <button onClick={onClose} className="p-1 rounded-lg hover:bg-gray-100 transition">
              <X className="h-4 w-4 text-gray-500" />
            </button>
          </div>
          {children}
        </div>
      </div>
    </>
  );
}
