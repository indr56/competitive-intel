"use client";

import { useEffect, useState } from "react";
import {
  CreditCard,
  Check,
  AlertTriangle,
  ArrowUpRight,
  Zap,
  Shield,
  Building2,
} from "lucide-react";
import { useActiveWorkspace } from "@/lib/hooks";
import { billing as billingApi } from "@/lib/api";
import type { BillingOverview, PlanInfo } from "@/lib/types";

const STATUS_COLORS: Record<string, string> = {
  trialing: "bg-blue-50 text-blue-700",
  active: "bg-green-50 text-green-700",
  past_due: "bg-red-50 text-red-700",
  canceled: "bg-gray-100 text-gray-600",
  incomplete: "bg-yellow-50 text-yellow-700",
};

const STATUS_LABELS: Record<string, string> = {
  trialing: "Trial",
  active: "Active",
  past_due: "Past Due",
  canceled: "Canceled",
  incomplete: "Incomplete",
};

const PLAN_ICONS: Record<string, React.ReactNode> = {
  starter: <Zap className="h-5 w-5" />,
  pro: <Shield className="h-5 w-5" />,
  agency: <Building2 className="h-5 w-5" />,
};

export default function BillingPage() {
  const { activeId } = useActiveWorkspace();
  const [overview, setOverview] = useState<BillingOverview | null>(null);
  const [plans, setPlans] = useState<PlanInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [checkingOut, setCheckingOut] = useState<string | null>(null);

  useEffect(() => {
    if (!activeId) return;
    setLoading(true);
    setError(null);
    Promise.all([billingApi.overview(activeId), billingApi.plans()])
      .then(([ov, pl]) => {
        setOverview(ov);
        setPlans(pl);
      })
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, [activeId]);

  const handleUpgrade = async (planType: string) => {
    if (!activeId) return;
    setCheckingOut(planType);
    setError(null);
    try {
      const res = await billingApi.checkout(activeId, planType);
      window.location.href = res.checkout_url;
    } catch (e: any) {
      setError(e.message);
    } finally {
      setCheckingOut(null);
    }
  };

  const handleManage = async () => {
    if (!activeId) return;
    setError(null);
    try {
      const res = await billingApi.portal(activeId);
      window.location.href = res.portal_url;
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

  if (loading) {
    return (
      <div className="space-y-4">
        <div className="h-8 w-48 animate-pulse rounded bg-gray-100" />
        <div className="h-40 animate-pulse rounded-xl bg-gray-100" />
        <div className="grid grid-cols-3 gap-4">
          {[1, 2, 3].map((i) => (
            <div key={i} className="h-64 animate-pulse rounded-xl bg-gray-100" />
          ))}
        </div>
      </div>
    );
  }

  const currentPlan = overview?.billing?.plan_type ?? "starter";
  const status = overview?.billing?.subscription_status ?? "trialing";

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold text-gray-900">Billing</h1>

      {error && (
        <div className="rounded-lg bg-red-50 border border-red-200 px-4 py-2 text-sm text-red-700">
          {error}
        </div>
      )}

      {status === "past_due" && (
        <div className="rounded-lg bg-red-50 border border-red-200 px-4 py-3 flex items-center gap-3">
          <AlertTriangle className="h-5 w-5 text-red-500 flex-shrink-0" />
          <div>
            <p className="text-sm font-medium text-red-800">
              Payment failed
            </p>
            <p className="text-xs text-red-600">
              Please update your payment method to continue using all features.
              {overview?.billing?.grace_period_ends_at && (
                <> Grace period ends {new Date(overview.billing.grace_period_ends_at).toLocaleDateString()}.</>
              )}
            </p>
          </div>
          <button
            onClick={handleManage}
            className="ml-auto rounded-lg bg-red-600 px-3 py-1.5 text-xs text-white hover:bg-red-500 transition"
          >
            Update Payment
          </button>
        </div>
      )}

      {/* Current Plan Card */}
      <div className="rounded-xl border bg-white p-6">
        <div className="flex items-center justify-between">
          <div>
            <div className="flex items-center gap-3 mb-1">
              <h2 className="text-lg font-semibold text-gray-900">
                {overview?.plan.name ?? "Starter"} Plan
              </h2>
              <span
                className={`text-xs font-semibold px-2.5 py-0.5 rounded-full ${
                  STATUS_COLORS[status] ?? STATUS_COLORS.incomplete
                }`}
              >
                {STATUS_LABELS[status] ?? status}
              </span>
            </div>
            <p className="text-sm text-gray-500">
              ${((overview?.plan.price_monthly_cents ?? 4900) / 100).toFixed(0)}/month
              {overview?.billing?.trial_ends_at &&
                status === "trialing" && (
                  <span className="ml-2 text-blue-600">
                    · Trial ends{" "}
                    {new Date(overview.billing.trial_ends_at).toLocaleDateString()}
                  </span>
                )}
              {overview?.billing?.current_period_end &&
                status === "active" && (
                  <span className="ml-2">
                    · Renews{" "}
                    {new Date(overview.billing.current_period_end).toLocaleDateString()}
                  </span>
                )}
            </p>
          </div>
          {overview?.billing?.stripe_customer_id && (
            <button
              onClick={handleManage}
              className="inline-flex items-center gap-1.5 rounded-lg border px-3 py-1.5 text-xs text-gray-600 hover:bg-gray-50 transition"
            >
              <CreditCard className="h-3.5 w-3.5" /> Manage Subscription
            </button>
          )}
        </div>

        {/* Usage bars */}
        {overview?.usage && (
          <div className="mt-5 grid grid-cols-1 md:grid-cols-2 gap-4">
            <UsageBar
              label="Competitors"
              used={overview.usage.competitors}
              limit={overview.usage.competitors_limit}
            />
            <UsageBar
              label="Tracked Pages"
              used={overview.usage.tracked_pages}
              limit={overview.usage.tracked_pages_limit}
            />
          </div>
        )}
      </div>

      {/* Plan Cards */}
      <div>
        <h2 className="text-lg font-semibold text-gray-900 mb-3">
          Available Plans
        </h2>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          {plans.map((plan) => {
            const isCurrent = plan.plan_type === currentPlan;
            const isUpgrade =
              plans.findIndex((p) => p.plan_type === currentPlan) <
              plans.findIndex((p) => p.plan_type === plan.plan_type);

            return (
              <div
                key={plan.plan_type}
                className={`rounded-xl border-2 bg-white p-6 transition ${
                  isCurrent
                    ? "border-blue-500 ring-1 ring-blue-100"
                    : "border-gray-200 hover:border-gray-300"
                }`}
              >
                <div className="flex items-center gap-2 mb-3">
                  <div
                    className={`p-1.5 rounded-lg ${
                      isCurrent
                        ? "bg-blue-50 text-blue-600"
                        : "bg-gray-50 text-gray-500"
                    }`}
                  >
                    {PLAN_ICONS[plan.plan_type] ?? (
                      <Zap className="h-5 w-5" />
                    )}
                  </div>
                  <h3 className="font-semibold text-gray-900">{plan.name}</h3>
                  {isCurrent && (
                    <span className="text-[10px] bg-blue-100 text-blue-700 px-1.5 py-0.5 rounded-full font-medium">
                      Current
                    </span>
                  )}
                </div>

                <div className="mb-4">
                  <span className="text-3xl font-bold text-gray-900">
                    ${(plan.price_monthly_cents / 100).toFixed(0)}
                  </span>
                  <span className="text-sm text-gray-500">/mo</span>
                </div>

                <ul className="space-y-2 mb-5 text-sm">
                  <LimitItem
                    label={`${plan.limits.max_competitors} competitors`}
                  />
                  <LimitItem
                    label={`${plan.limits.max_tracked_pages} tracked pages`}
                  />
                  <LimitItem
                    label={`${plan.limits.min_check_interval_hours}h min check interval`}
                  />
                  <LimitItem
                    label={`${plan.limits.max_workspaces} workspace${
                      plan.limits.max_workspaces > 1 ? "s" : ""
                    }`}
                  />
                  {plan.limits.white_label && (
                    <LimitItem label="White-label reports" />
                  )}
                </ul>

                {isCurrent ? (
                  <div className="rounded-lg bg-blue-50 px-3 py-2 text-center text-xs text-blue-700 font-medium">
                    Your current plan
                  </div>
                ) : (
                  <button
                    onClick={() => handleUpgrade(plan.plan_type)}
                    disabled={checkingOut !== null}
                    className={`w-full inline-flex items-center justify-center gap-1.5 rounded-lg px-3 py-2 text-sm font-medium transition disabled:opacity-50 ${
                      isUpgrade
                        ? "bg-gray-900 text-white hover:bg-gray-700"
                        : "border border-gray-300 text-gray-700 hover:bg-gray-50"
                    }`}
                  >
                    {checkingOut === plan.plan_type ? (
                      "Redirecting..."
                    ) : isUpgrade ? (
                      <>
                        Upgrade <ArrowUpRight className="h-3.5 w-3.5" />
                      </>
                    ) : (
                      "Switch Plan"
                    )}
                  </button>
                )}
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}

function UsageBar({
  label,
  used,
  limit,
}: {
  label: string;
  used: number;
  limit: number;
}) {
  const pct = limit > 0 ? Math.min((used / limit) * 100, 100) : 0;
  const color =
    pct >= 90 ? "bg-red-500" : pct >= 70 ? "bg-yellow-500" : "bg-blue-500";
  return (
    <div>
      <div className="flex items-center justify-between mb-1">
        <span className="text-xs font-medium text-gray-600">{label}</span>
        <span className="text-xs text-gray-500">
          {used} / {limit}
        </span>
      </div>
      <div className="h-2 rounded-full bg-gray-100 overflow-hidden">
        <div
          className={`h-full rounded-full transition-all ${color}`}
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  );
}

function LimitItem({ label }: { label: string }) {
  return (
    <li className="flex items-center gap-2 text-gray-600">
      <Check className="h-3.5 w-3.5 text-green-500 flex-shrink-0" />
      {label}
    </li>
  );
}
