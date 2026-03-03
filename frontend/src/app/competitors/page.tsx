"use client";

import { useEffect, useState } from "react";
import { Plus, Globe, ChevronRight } from "lucide-react";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

interface Workspace {
  id: string;
  name: string;
  slug: string;
}

interface Competitor {
  id: string;
  name: string;
  domain: string;
  is_active: boolean;
  created_at: string;
}

export default function CompetitorsPage() {
  const [workspaces, setWorkspaces] = useState<Workspace[]>([]);
  const [activeWs, setActiveWs] = useState<string>("");
  const [competitors, setCompetitors] = useState<Competitor[]>([]);
  const [showAdd, setShowAdd] = useState(false);
  const [form, setForm] = useState({ name: "", domain: "" });
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    fetch(`${API_URL}/api/workspaces`)
      .then((r) => r.json())
      .then((data) => {
        setWorkspaces(data);
        if (data.length > 0) setActiveWs(data[0].id);
      })
      .catch(console.error);
  }, []);

  useEffect(() => {
    if (!activeWs) return;
    fetch(`${API_URL}/api/workspaces/${activeWs}/competitors`)
      .then((r) => r.json())
      .then(setCompetitors)
      .catch(console.error);
  }, [activeWs]);

  const handleAdd = async () => {
    if (!form.name || !form.domain || !activeWs) return;
    setLoading(true);
    try {
      const res = await fetch(
        `${API_URL}/api/workspaces/${activeWs}/competitors`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(form),
        }
      );
      if (res.ok) {
        const c = await res.json();
        setCompetitors((prev) => [c, ...prev]);
        setForm({ name: "", domain: "" });
        setShowAdd(false);
      }
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-gray-50">
      <nav className="border-b bg-white">
        <div className="mx-auto max-w-6xl flex items-center justify-between px-6 py-4">
          <a href="/" className="text-lg font-bold text-gray-900">
            Competitive Moves Intelligence
          </a>
          <div className="flex gap-6 text-sm text-gray-600">
            <a href="/competitors" className="text-gray-900 font-medium">Competitors</a>
            <a href="/changes" className="hover:text-gray-900">Changes</a>
            <a href="/digests" className="hover:text-gray-900">Digests</a>
          </div>
        </div>
      </nav>

      <main className="mx-auto max-w-6xl px-6 py-8">
        <div className="flex items-center justify-between mb-6">
          <h2 className="text-2xl font-bold text-gray-900">Competitors</h2>
          <button
            onClick={() => setShowAdd(!showAdd)}
            className="inline-flex items-center gap-2 rounded-lg bg-gray-900 px-4 py-2 text-sm text-white hover:bg-gray-700 transition"
          >
            <Plus className="w-4 h-4" /> Add Competitor
          </button>
        </div>

        {showAdd && (
          <div className="rounded-xl border bg-white p-6 mb-6">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-4">
              <input
                placeholder="Competitor name"
                value={form.name}
                onChange={(e) => setForm({ ...form, name: e.target.value })}
                className="rounded-lg border px-3 py-2 text-sm"
              />
              <input
                placeholder="Domain (e.g. competitor.com)"
                value={form.domain}
                onChange={(e) => setForm({ ...form, domain: e.target.value })}
                className="rounded-lg border px-3 py-2 text-sm"
              />
            </div>
            <button
              onClick={handleAdd}
              disabled={loading}
              className="rounded-lg bg-blue-600 px-4 py-2 text-sm text-white hover:bg-blue-500 disabled:opacity-50 transition"
            >
              {loading ? "Adding..." : "Add"}
            </button>
          </div>
        )}

        {competitors.length === 0 ? (
          <div className="rounded-xl border bg-white p-12 text-center text-gray-400">
            No competitors yet. Add one to get started.
          </div>
        ) : (
          <div className="space-y-3">
            {competitors.map((c) => (
              <div
                key={c.id}
                className="rounded-xl border bg-white p-5 flex items-center justify-between hover:shadow-sm transition"
              >
                <div className="flex items-center gap-4">
                  <div className="w-10 h-10 rounded-full bg-gray-100 flex items-center justify-center">
                    <Globe className="w-5 h-5 text-gray-500" />
                  </div>
                  <div>
                    <h3 className="font-semibold text-gray-900">{c.name}</h3>
                    <p className="text-sm text-gray-500">{c.domain}</p>
                  </div>
                </div>
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
                  <ChevronRight className="w-4 h-4 text-gray-400" />
                </div>
              </div>
            ))}
          </div>
        )}
      </main>
    </div>
  );
}
