"use client";

import { useState } from "react";
import { useParams, useRouter } from "next/navigation";
import {
  FolderOpen,
  ArrowLeft,
  Tag,
  BarChart3,
  ListChecks,
} from "lucide-react";
import { useActiveWorkspace, useFetch } from "@/lib/hooks";
import { aiVisibility } from "@/lib/api";
import type { CategoryVisibilityEnriched } from "@/lib/types";

export default function CategoryDetailPage() {
  const router = useRouter();
  const params = useParams();
  const categoryId = params.id as string;

  const { active, loading: wsLoading } = useActiveWorkspace();
  const wsId = active?.id ?? "";

  const { data: categories } = useFetch(
    () => (wsId ? aiVisibility.listCategories(wsId) : Promise.resolve([])),
    [wsId]
  );

  const { data: allPrompts } = useFetch(
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

      {/* Stats row */}
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

      {/* Prompts in this category */}
      <div className="rounded-xl border bg-white p-5">
        <h3 className="text-sm font-semibold text-gray-800 mb-3 flex items-center gap-1.5">
          <ListChecks className="h-4 w-4 text-indigo-500" />
          Prompts in this category
        </h3>
        {catPrompts.length === 0 ? (
          <p className="text-xs text-gray-400 text-center py-6">No prompts assigned to this category yet.</p>
        ) : (
          <div className="space-y-2">
            {catPrompts.map((p) => (
              <div key={p.id} className="flex items-center gap-3 rounded-lg border p-3">
                <div className={`w-2 h-2 rounded-full flex-shrink-0 ${p.is_active ? "bg-green-500" : "bg-amber-400"}`} />
                <p className="flex-1 text-sm text-gray-800 truncate">&ldquo;{p.prompt_text}&rdquo;</p>
                <span className="text-[11px] text-gray-400">{p.is_active ? "Active" : "Paused"}</span>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Category Ownership Distribution */}
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
    </div>
  );
}
