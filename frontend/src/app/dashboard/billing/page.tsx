"use client";

import { useEffect, useState, useCallback } from "react";
import Script from "next/script";
import {
  Check,
  AlertTriangle,
  ArrowUpRight,
  Zap,
  Shield,
  Building2,
  XCircle,
  RefreshCw,
} from "lucide-react";
import { useActiveWorkspace } from "@/lib/hooks";
import { billing as billingApi } from "@/lib/api";
import type { BillingOverview, PlanInfo } from "@/lib/types";

declare global {
  interface Window {
    Razorpay: any;
  }
}

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
  const [cancelling, setCancelling] = useState(false);
  const [syncing, setSyncing] = useState(false);
  const [currencyModal, setCurrencyModal] = useState<string | null>(null); // plan_type being upgraded

  const fetchBilling = useCallback(() => {
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

  useEffect(() => {
    fetchBilling();
  }, [fetchBilling]);

  const handleUpgrade = (planType: string) => {
    setCurrencyModal(planType);
  };

  const handleCurrencySelect = async (currency: "USD" | "INR") => {
    const planType = currencyModal;
    setCurrencyModal(null);
    if (!activeId || !planType) return;
    setCheckingOut(planType);
    setError(null);
    try {
      const res = await billingApi.checkout(activeId, planType, currency);

      // Open Razorpay Checkout
      const options = {
        key: res.razorpay_key_id,
        subscription_id: res.subscription_id,
        name: "Competitive Moves Intelligence",
        description: `${planType.charAt(0).toUpperCase() + planType.slice(1)} Plan (${currency})`,
        currency,
        handler: async (response: {
          razorpay_subscription_id: string;
          razorpay_payment_id: string;
          razorpay_signature: string;
        }) => {
          // Verify payment on backend
          try {
            await billingApi.verify(activeId, {
              razorpay_subscription_id: response.razorpay_subscription_id,
              razorpay_payment_id: response.razorpay_payment_id,
              razorpay_signature: response.razorpay_signature,
            });
            // Refresh billing data
            fetchBilling();
          } catch (err: any) {
            setError("Payment verification failed: " + err.message);
          }
        },
        modal: {
          ondismiss: () => {
            setCheckingOut(null);
          },
        },
        theme: {
          color: "#111827",
        },
      };

      if (typeof window.Razorpay === "undefined") {
        setError("Razorpay SDK not loaded. Please refresh the page.");
        return;
      }

      const rzp = new window.Razorpay(options);
      rzp.open();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setCheckingOut(null);
    }
  };

  const handleCancel = async () => {
    if (!activeId || !confirm("Are you sure you want to cancel your subscription?")) return;
    setCancelling(true);
    setError(null);
    try {
      await billingApi.cancel(activeId);
      fetchBilling();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setCancelling(false);
    }
  };

  const handleSync = async () => {
    if (!activeId) return;
    setSyncing(true);
    setError(null);
    try {
      await billingApi.sync(activeId);
      fetchBilling();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setSyncing(false);
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
      {/* Load Razorpay checkout SDK */}
      <Script src="https://checkout.razorpay.com/v1/checkout.js" strategy="lazyOnload" />

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
              Please subscribe again to continue using all features.
              {overview?.billing?.grace_period_ends_at && (
                <> Grace period ends {new Date(overview.billing.grace_period_ends_at).toLocaleDateString()}.</>
              )}
            </p>
          </div>
          <button
            onClick={handleSync}
            disabled={syncing}
            className="ml-auto rounded-lg bg-red-600 px-3 py-1.5 text-xs text-white hover:bg-red-500 transition disabled:opacity-50"
          >
            {syncing ? "Syncing..." : "Refresh Status"}
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
          <div className="flex items-center gap-2">
            <button
              onClick={handleSync}
              disabled={syncing}
              className="inline-flex items-center gap-1.5 rounded-lg border px-3 py-1.5 text-xs text-gray-600 hover:bg-gray-50 transition disabled:opacity-50"
              title="Sync subscription status from Razorpay"
            >
              <RefreshCw className={`h-3.5 w-3.5 ${syncing ? "animate-spin" : ""}`} /> Sync
            </button>
            {overview?.billing?.razorpay_subscription_id &&
              status === "active" && (
                <button
                  onClick={handleCancel}
                  disabled={cancelling}
                  className="inline-flex items-center gap-1.5 rounded-lg border border-red-200 px-3 py-1.5 text-xs text-red-600 hover:bg-red-50 transition disabled:opacity-50"
                >
                  <XCircle className="h-3.5 w-3.5" />
                  {cancelling ? "Cancelling..." : "Cancel Subscription"}
                </button>
              )}
          </div>
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

        {/* Payment methods note */}
        <div className="mt-4 pt-4 border-t">
          <p className="text-xs text-gray-400">
            Payments powered by Razorpay · Supports UPI, Cards, Netbanking, and Wallets
          </p>
        </div>
      </div>

      {/* Plan Cards */}
      <div>
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-lg font-semibold text-gray-900">
            Available Plans
          </h2>
          <span className="text-xs text-gray-500 bg-amber-50 border border-amber-200 px-2.5 py-1 rounded-full">
            🇮🇳 Regional pricing available for Indian customers
          </span>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          {plans.map((plan) => {
            const isCurrent = plan.plan_type === currentPlan;
            const isUpgrade =
              plans.findIndex((p) => p.plan_type === currentPlan) <
              plans.findIndex((p) => p.plan_type === plan.plan_type);

            const usdPrice = plan.pricing?.USD
              ? (plan.pricing.USD / 100).toFixed(0)
              : (plan.price_monthly_cents / 100).toFixed(0);
            const inrPrice = plan.pricing?.INR
              ? (plan.pricing.INR / 100).toFixed(0)
              : null;

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
                  <div>
                    <span className="text-3xl font-bold text-gray-900">
                      ${usdPrice}
                    </span>
                    <span className="text-sm text-gray-500">/mo</span>
                  </div>
                  {inrPrice && (
                    <div className="mt-1">
                      <span className="text-lg font-semibold text-gray-700">
                        ₹{inrPrice}
                      </span>
                      <span className="text-sm text-gray-500">/mo</span>
                      <span className="ml-1.5 text-[11px] text-amber-600 font-medium">
                        India pricing
                      </span>
                    </div>
                  )}
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
                      "Processing..."
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

      {/* Currency Selection Modal */}
      {currencyModal && (
        <CurrencyModal
          planType={currencyModal}
          plans={plans}
          onSelect={handleCurrencySelect}
          onClose={() => setCurrencyModal(null)}
        />
      )}
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

function CurrencyModal({
  planType,
  plans,
  onSelect,
  onClose,
}: {
  planType: string;
  plans: PlanInfo[];
  onSelect: (currency: "USD" | "INR") => void;
  onClose: () => void;
}) {
  const plan = plans.find((p) => p.plan_type === planType);
  const planName = plan?.name ?? planType;
  const usdPrice = plan?.pricing?.USD
    ? (plan.pricing.USD / 100).toFixed(0)
    : plan
      ? (plan.price_monthly_cents / 100).toFixed(0)
      : "—";
  const inrPrice = plan?.pricing?.INR
    ? (plan.pricing.INR / 100).toFixed(0)
    : null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      <div
        className="absolute inset-0 bg-black/40 backdrop-blur-sm"
        onClick={onClose}
      />
      <div className="relative bg-white rounded-2xl shadow-xl w-full max-w-md mx-4 p-6">
        <h3 className="text-lg font-semibold text-gray-900 mb-1">
          Choose currency
        </h3>
        <p className="text-sm text-gray-500 mb-5">
          Select your preferred currency for the <strong>{planName}</strong> plan.
        </p>

        <div className="grid grid-cols-2 gap-3">
          <button
            onClick={() => onSelect("USD")}
            className="flex flex-col items-center gap-2 rounded-xl border-2 border-gray-200 hover:border-gray-900 p-5 transition group"
          >
            <span className="text-2xl font-bold text-gray-900 group-hover:text-gray-900">
              ${usdPrice}
            </span>
            <span className="text-sm text-gray-500">/month</span>
            <span className="mt-1 text-xs font-medium bg-gray-100 text-gray-600 px-2 py-0.5 rounded-full">
              USD
            </span>
            <span className="text-[11px] text-gray-400">
              International cards
            </span>
          </button>

          {inrPrice && (
            <button
              onClick={() => onSelect("INR")}
              className="flex flex-col items-center gap-2 rounded-xl border-2 border-gray-200 hover:border-amber-500 p-5 transition group"
            >
              <span className="text-2xl font-bold text-gray-900 group-hover:text-amber-700">
                ₹{inrPrice}
              </span>
              <span className="text-sm text-gray-500">/month</span>
              <span className="mt-1 text-xs font-medium bg-amber-50 text-amber-700 px-2 py-0.5 rounded-full">
                INR
              </span>
              <span className="text-[11px] text-gray-400">
                UPI, Cards, Netbanking, Wallets
              </span>
            </button>
          )}
        </div>

        <button
          onClick={onClose}
          className="mt-4 w-full text-center text-sm text-gray-500 hover:text-gray-700 transition"
        >
          Cancel
        </button>
      </div>
    </div>
  );
}
