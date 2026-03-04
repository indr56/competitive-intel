"use client";

import { useEffect, useState } from "react";
import { Activity, Globe, Mail, Zap } from "lucide-react";
import Link from "next/link";
import { useActiveWorkspace } from "@/lib/hooks";
import { changes, competitors, digests } from "@/lib/api";
import type { ChangeEvent, Competitor, Digest } from "@/lib/types";

export default function DashboardPage() {
  const { activeId, active } = useActiveWorkspace();
  const [recentChanges, setRecentChanges] = useState<ChangeEvent[]>([]);
  const [comps, setComps] = useState<Competitor[]>([]);
  const [latestDigests, setLatestDigests] = useState<Digest[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!activeId) return;
    setLoading(true);
    Promise.all([
      changes.list({ workspace_id: activeId, limit: 5 }),
      competitors.list(activeId),
      digests.list(activeId),
    ])
      .then(([c, comp, d]) => {
        setRecentChanges(c);
        setComps(comp);
        setLatestDigests(d.slice(0, 3));
      })
      .catch(console.error)
      .finally(() => setLoading(false));
  }, [activeId]);

  if (!activeId) {
    return (
      <div className="flex items-center justify-center h-64 text-gray-400">
        Select or create a workspace to get started.
      </div>
    );
  }

  if (loading) {
    return (
      <div className="space-y-4">
        {[1, 2, 3].map((i) => (
          <div key={i} className="h-24 animate-pulse rounded-xl bg-gray-100" />
        ))}
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold text-gray-900">
        {active?.name ?? "Dashboard"}
      </h1>

      {/* Stat cards */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <StatCard
          icon={<Globe className="h-5 w-5 text-blue-600" />}
          label="Competitors"
          value={comps.length}
          href="/dashboard/competitors"
        />
        <StatCard
          icon={<Activity className="h-5 w-5 text-orange-600" />}
          label="Recent Changes"
          value={recentChanges.length}
          href="/dashboard/changes"
        />
        <StatCard
          icon={<Mail className="h-5 w-5 text-green-600" />}
          label="Digests"
          value={latestDigests.length}
          href="/dashboard/digests"
        />
      </div>

      {/* Recent changes */}
      <div>
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-lg font-semibold text-gray-900">
            Recent Changes
          </h2>
          <Link
            href="/dashboard/changes"
            className="text-xs text-blue-600 hover:underline"
          >
            View all
          </Link>
        </div>
        {recentChanges.length === 0 ? (
          <div className="rounded-xl border bg-white p-8 text-center text-sm text-gray-400">
            No changes detected yet. Add competitors and tracked pages to start.
          </div>
        ) : (
          <div className="space-y-2">
            {recentChanges.map((ce) => (
              <Link
                key={ce.id}
                href={`/dashboard/changes/${ce.id}`}
                className="flex items-center justify-between rounded-xl border bg-white p-4 hover:shadow-sm transition"
              >
                <div className="flex items-center gap-3">
                  <Zap className="h-4 w-4 text-purple-500" />
                  <div>
                    <p className="text-sm font-medium text-gray-800 line-clamp-1">
                      {ce.ai_summary ?? "Change detected"}
                    </p>
                    <p className="text-xs text-gray-400">
                      {ce.categories.map((c) => c.replace(/_/g, " ")).join(", ")}
                    </p>
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  <SeverityBadge severity={ce.severity} />
                  <span className="text-xs text-gray-400">
                    {new Date(ce.created_at).toLocaleDateString()}
                  </span>
                </div>
              </Link>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function StatCard({
  icon,
  label,
  value,
  href,
}: {
  icon: React.ReactNode;
  label: string;
  value: number;
  href: string;
}) {
  return (
    <Link
      href={href}
      className="rounded-xl border bg-white p-5 hover:shadow-sm transition"
    >
      <div className="flex items-center gap-3 mb-2">
        {icon}
        <span className="text-sm text-gray-500">{label}</span>
      </div>
      <p className="text-3xl font-bold text-gray-900">{value}</p>
    </Link>
  );
}

const SEV_COLORS: Record<string, string> = {
  critical: "bg-red-50 text-red-700",
  high: "bg-orange-50 text-orange-700",
  medium: "bg-yellow-50 text-yellow-700",
  low: "bg-green-50 text-green-700",
};

function SeverityBadge({ severity }: { severity: string | null }) {
  const s = severity ?? "medium";
  return (
    <span
      className={`rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase ${
        SEV_COLORS[s] ?? SEV_COLORS.medium
      }`}
    >
      {s}
    </span>
  );
}
