"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  Activity,
  BarChart3,
  CreditCard,
  Globe,
  Home,
  Mail,
  FileText,
  Settings,
  Zap,
  Eye,
  Search,
  ListChecks,
  TrendingUp,
  Lightbulb,
} from "lucide-react";

const NAV_ITEMS = [
  { href: "/dashboard", label: "Dashboard", icon: Home },
  { href: "/dashboard/competitors", label: "Competitors", icon: Globe },
  { href: "/dashboard/activity", label: "Activity Feed", icon: Zap },
  { href: "/dashboard/changes", label: "Change Feed", icon: Activity },
  { href: "/dashboard/digests", label: "Digests", icon: Mail },
  { href: "/dashboard/pages", label: "Tracked Pages", icon: FileText },
  { href: "/dashboard/billing", label: "Billing", icon: CreditCard },
  { href: "/dashboard/settings", label: "Settings", icon: Settings },
];

const AI_VIS_ITEMS = [
  { href: "/dashboard/ai-visibility/setup", label: "Prompt Setup", icon: Search },
  { href: "/dashboard/ai-visibility/prompts", label: "Tracked Prompts", icon: ListChecks },
  { href: "/dashboard/ai-visibility/trends", label: "Visibility Trends", icon: TrendingUp },
  { href: "/dashboard/ai-visibility/insights", label: "AI Impact Insights", icon: Lightbulb },
];

export default function Sidebar() {
  const pathname = usePathname();

  return (
    <aside className="fixed inset-y-0 left-0 z-30 flex w-60 flex-col border-r bg-white">
      {/* Brand */}
      <div className="flex h-14 items-center gap-2 border-b px-4">
        <BarChart3 className="h-5 w-5 text-blue-600" />
        <span className="text-sm font-bold text-gray-900 truncate">
          CompetitiveMoves
        </span>
      </div>

      {/* Nav */}
      <nav className="flex-1 overflow-y-auto px-2 py-3">
        <ul className="space-y-0.5">
          {NAV_ITEMS.map(({ href, label, icon: Icon }) => {
            const active =
              pathname === href ||
              (href !== "/dashboard" && pathname.startsWith(href));
            return (
              <li key={href}>
                <Link
                  href={href}
                  className={`flex items-center gap-2.5 rounded-lg px-3 py-2 text-sm font-medium transition ${
                    active
                      ? "bg-blue-50 text-blue-700"
                      : "text-gray-600 hover:bg-gray-50 hover:text-gray-900"
                  }`}
                >
                  <Icon className="h-4 w-4 flex-shrink-0" />
                  {label}
                </Link>
              </li>
            );
          })}
        </ul>

        {/* AI Visibility Section */}
        <div className="mt-4 mb-1 px-3">
          <div className="flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-wider text-violet-500">
            <Eye className="h-3 w-3" />
            AI Visibility
          </div>
        </div>
        <ul className="space-y-0.5">
          {AI_VIS_ITEMS.map(({ href, label, icon: Icon }) => {
            const active = pathname.startsWith(href);
            return (
              <li key={href}>
                <Link
                  href={href}
                  className={`flex items-center gap-2.5 rounded-lg px-3 py-2 text-sm font-medium transition ${
                    active
                      ? "bg-violet-50 text-violet-700"
                      : "text-gray-600 hover:bg-gray-50 hover:text-gray-900"
                  }`}
                >
                  <Icon className="h-4 w-4 flex-shrink-0" />
                  {label}
                </Link>
              </li>
            );
          })}
        </ul>
      </nav>

      {/* Footer */}
      <div className="border-t px-4 py-3">
        <p className="text-[10px] text-gray-400">v0.1.0 &middot; MVP</p>
      </div>
    </aside>
  );
}
