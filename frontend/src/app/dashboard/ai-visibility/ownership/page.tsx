"use client";

import { useState } from "react";
import {
  PieChart,
  RefreshCw,
  TrendingUp,
  TrendingDown,
  Minus,
  BarChart3,
  FolderOpen,
} from "lucide-react";
import { useActiveWorkspace, useFetch } from "@/lib/hooks";
import { aiVisibility } from "@/lib/api";
import type { CategoryVisibilityEnriched, PromptCategory } from "@/lib/types";

export default function CategoryOwnershipPage() {
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

  const {
    data: ownershipData,
    loading: ownershipLoading,
    refetch,
  } = useFetch(
    () =>
      wsId
        ? aiVisibility.listCategoryVisibilityEnriched(wsId)
        : Promise.resolve([]),
    [wsId]
  );

  if (wsLoading || !active) {
    return <div className="p-8 text-gray-500">Loading workspace…</div>;
  }

  const cats = categories ?? [];
  const prompts = allPrompts ?? [];
  const ownership = ownershipData ?? [];

  // Group ownership by category
  const byCat: Record<
    string,
    { category_name: string; prompt_count: number; engine_count: number; competitors: CategoryVisibilityEnriched[] }
  > = {};
  for (const o of ownership) {
    if (!byCat[o.category_id]) {
      byCat[o.category_id] = {
        category_name: o.category_name,
        prompt_count: o.prompt_count,
        engine_count: o.engine_count,
        competitors: [],
      };
    }
    byCat[o.category_id].competitors.push(o);
  }

  // Prompt counts per category for categories without ownership data
  const promptCountMap: Record<string, number> = {};
  for (const p of prompts) {
    if (p.category_id) {
      promptCountMap[p.category_id] = (promptCountMap[p.category_id] || 0) + 1;
    }
  }

  // Sort competitors within each category by visibility_share desc
  for (const catId of Object.keys(byCat)) {
    byCat[catId].competitors.sort((a, b) => b.visibility_share - a.visibility_share);
  }

  const categoryIds = Object.keys(byCat);

  // Categories with no ownership data yet
  const emptyCats = cats.filter((c) => !byCat[c.id]);

  const COLORS = [
    "bg-indigo-500",
    "bg-violet-500",
    "bg-blue-500",
    "bg-emerald-500",
    "bg-amber-500",
    "bg-rose-500",
    "bg-cyan-500",
    "bg-pink-500",
  ];

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-gray-900 flex items-center gap-2">
            <PieChart className="h-5 w-5 text-indigo-600" />
            Category Ownership
          </h1>
          <p className="text-sm text-gray-500 mt-0.5">
            See which competitors dominate AI answers in each category
          </p>
        </div>
        <button
          onClick={refetch}
          className="flex items-center gap-1.5 text-sm text-gray-600 hover:text-gray-900 bg-gray-100 hover:bg-gray-200 rounded-lg px-3 py-2 transition"
        >
          <RefreshCw className="h-3.5 w-3.5" />
          Refresh
        </button>
      </div>

      {ownershipLoading ? (
        <div className="text-sm text-gray-400 py-8 text-center">Loading ownership data…</div>
      ) : categoryIds.length === 0 && emptyCats.length === 0 ? (
        <div className="rounded-xl border bg-white p-8 text-center">
          <PieChart className="h-10 w-10 text-gray-300 mx-auto mb-3" />
          <p className="text-sm text-gray-500">
            No categories with ownership data yet. Create categories, assign prompts, run them, and then run correlation.
          </p>
        </div>
      ) : (
        <div className="space-y-6">
          {/* Category cards with ownership */}
          {categoryIds.map((catId) => {
            const catData = byCat[catId];
            const maxShare = Math.max(...catData.competitors.map((c) => c.visibility_share), 1);
            return (
              <div key={catId} className="rounded-xl border bg-white p-6">
                {/* Category header */}
                <div className="flex items-center justify-between mb-4">
                  <div>
                    <h2 className="text-base font-bold text-gray-900 flex items-center gap-2">
                      <FolderOpen className="h-4 w-4 text-indigo-500" />
                      {catData.category_name}
                    </h2>
                    <div className="flex items-center gap-4 mt-1">
                      <span className="text-xs text-gray-400">
                        Prompts tracked: <span className="font-semibold text-gray-600">{catData.prompt_count}</span>
                      </span>
                      <span className="text-xs text-gray-400">
                        AI engines analyzed: <span className="font-semibold text-gray-600">{catData.engine_count}</span>
                      </span>
                    </div>
                  </div>
                </div>

                {/* Ownership distribution */}
                <div className="space-y-3">
                  {catData.competitors.map((comp, idx) => {
                    const barWidth = (comp.visibility_share / maxShare) * 100;
                    const colorClass = COLORS[idx % COLORS.length];
                    return (
                      <div key={comp.competitor_id} className="flex items-center gap-4">
                        <span className="text-sm font-medium text-gray-700 w-40 truncate">
                          {comp.competitor_name}
                        </span>
                        <div className="flex-1 h-7 bg-gray-100 rounded-full overflow-hidden relative">
                          <div
                            className={`h-full ${colorClass} rounded-full transition-all duration-500`}
                            style={{ width: `${Math.max(barWidth, 2)}%` }}
                          />
                        </div>
                        <span className="text-sm font-bold text-gray-800 w-14 text-right">
                          {comp.visibility_share.toFixed(1)}%
                        </span>
                      </div>
                    );
                  })}
                </div>
              </div>
            );
          })}

          {/* Categories with no ownership data yet */}
          {emptyCats.length > 0 && (
            <div className="rounded-xl border bg-gray-50 p-5">
              <h3 className="text-sm font-semibold text-gray-600 mb-2">Categories awaiting data</h3>
              <p className="text-xs text-gray-400 mb-3">
                These categories have no ownership data yet. Assign prompts, run them, and then run correlation.
              </p>
              <div className="flex flex-wrap gap-2">
                {emptyCats.map((c) => (
                  <span key={c.id} className="inline-flex items-center gap-1 rounded-lg bg-white border px-3 py-1.5 text-xs text-gray-600">
                    <FolderOpen className="h-3 w-3 text-gray-400" />
                    {c.category_name}
                    <span className="text-gray-300 ml-1">{promptCountMap[c.id] || 0} prompts</span>
                  </span>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
