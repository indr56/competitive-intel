"use client";

import { CreditCard } from "lucide-react";

export default function BillingPage() {
  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold text-gray-900">Billing</h1>

      <div className="rounded-xl border bg-white p-12 text-center">
        <CreditCard className="h-12 w-12 text-gray-300 mx-auto mb-4" />
        <h2 className="text-lg font-semibold text-gray-700 mb-2">
          Billing Coming Soon
        </h2>
        <p className="text-sm text-gray-500 max-w-md mx-auto">
          Subscription management, usage tracking, and invoices will be
          available here. For now, all features are available during the MVP
          beta period.
        </p>
        <div className="mt-6 inline-flex items-center gap-2 rounded-full bg-green-50 px-4 py-2 text-sm text-green-700 font-medium">
          Current plan: Free Beta
        </div>
      </div>
    </div>
  );
}
