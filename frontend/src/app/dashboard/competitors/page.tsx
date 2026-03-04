"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Plus, Globe, ChevronRight, Trash2 } from "lucide-react";
import { useActiveWorkspace } from "@/lib/hooks";
import { competitors as compApi } from "@/lib/api";
import type { Competitor } from "@/lib/types";

export default function CompetitorsPage() {
  const { activeId } = useActiveWorkspace();
  const [comps, setComps] = useState<Competitor[]>([]);
  const [loading, setLoading] = useState(true);
  const [showAdd, setShowAdd] = useState(false);
  const [form, setForm] = useState({ name: "", domain: "" });
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!activeId) return;
    setLoading(true);
    compApi
      .list(activeId)
      .then(setComps)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, [activeId]);

  const handleAdd = async () => {
    if (!form.name.trim() || !form.domain.trim() || !activeId) return;
    setSubmitting(true);
    setError(null);
    try {
      const c = await compApi.create(activeId, {
        name: form.name.trim(),
        domain: form.domain.trim(),
      });
      setComps((prev) => [c, ...prev]);
      setForm({ name: "", domain: "" });
      setShowAdd(false);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setSubmitting(false);
    }
  };

  const handleDelete = async (id: string) => {
    if (!confirm("Delete this competitor and all tracked pages?")) return;
    try {
      await compApi.delete(id);
      setComps((prev) => prev.filter((c) => c.id !== id));
    } catch (e: any) {
      setError(e.message);
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
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-gray-900">Competitors</h1>
        <button
          onClick={() => setShowAdd(!showAdd)}
          className="inline-flex items-center gap-2 rounded-lg bg-gray-900 px-4 py-2 text-sm text-white hover:bg-gray-700 transition"
        >
          <Plus className="h-4 w-4" /> Add Competitor
        </button>
      </div>

      {error && (
        <div className="rounded-lg bg-red-50 border border-red-200 px-4 py-2 text-sm text-red-700">
          {error}
        </div>
      )}

      {showAdd && (
        <div className="rounded-xl border bg-white p-6">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-4">
            <input
              autoFocus
              placeholder="Competitor name"
              value={form.name}
              onChange={(e) => setForm({ ...form, name: e.target.value })}
              onKeyDown={(e) => e.key === "Enter" && handleAdd()}
              className="rounded-lg border px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
            <input
              placeholder="Domain (e.g. competitor.com)"
              value={form.domain}
              onChange={(e) => setForm({ ...form, domain: e.target.value })}
              onKeyDown={(e) => e.key === "Enter" && handleAdd()}
              className="rounded-lg border px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
          </div>
          <div className="flex gap-2">
            <button
              onClick={handleAdd}
              disabled={submitting}
              className="rounded-lg bg-blue-600 px-4 py-2 text-sm text-white hover:bg-blue-500 disabled:opacity-50 transition"
            >
              {submitting ? "Adding..." : "Add"}
            </button>
            <button
              onClick={() => setShowAdd(false)}
              className="rounded-lg border px-4 py-2 text-sm text-gray-600 hover:bg-gray-50 transition"
            >
              Cancel
            </button>
          </div>
        </div>
      )}

      {loading ? (
        <div className="space-y-3">
          {[1, 2, 3].map((i) => (
            <div key={i} className="h-16 animate-pulse rounded-xl bg-gray-100" />
          ))}
        </div>
      ) : comps.length === 0 ? (
        <div className="rounded-xl border bg-white p-12 text-center text-gray-400">
          No competitors yet. Add one to get started.
        </div>
      ) : (
        <div className="space-y-2">
          {comps.map((c) => (
            <div
              key={c.id}
              className="rounded-xl border bg-white p-4 flex items-center justify-between hover:shadow-sm transition"
            >
              <Link
                href={`/dashboard/competitors/${c.id}`}
                className="flex items-center gap-4 flex-1"
              >
                <div className="h-10 w-10 rounded-full bg-gray-100 flex items-center justify-center">
                  <Globe className="h-5 w-5 text-gray-500" />
                </div>
                <div>
                  <h3 className="font-semibold text-gray-900">{c.name}</h3>
                  <p className="text-sm text-gray-500">{c.domain}</p>
                </div>
              </Link>
              <div className="flex items-center gap-3">
                <span
                  className={`text-xs font-medium px-2 py-0.5 rounded-full ${
                    c.is_active
                      ? "bg-green-50 text-green-700"
                      : "bg-gray-100 text-gray-500"
                  }`}
                >
                  {c.is_active ? "Active" : "Inactive"}
                </span>
                <button
                  onClick={() => handleDelete(c.id)}
                  className="text-gray-400 hover:text-red-500 transition p-1"
                >
                  <Trash2 className="h-4 w-4" />
                </button>
                <Link href={`/dashboard/competitors/${c.id}`}>
                  <ChevronRight className="h-4 w-4 text-gray-400" />
                </Link>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
