"use client";

import { useEffect, useState } from "react";
import { Settings, Save } from "lucide-react";
import { useActiveWorkspace } from "@/lib/hooks";
import { whiteLabel } from "@/lib/api";
import type { WhiteLabelConfigUpsert } from "@/lib/types";

export default function SettingsPage() {
  const { activeId } = useActiveWorkspace();
  const [form, setForm] = useState<WhiteLabelConfigUpsert>({
    logo_url: "",
    brand_color: "#111827",
    sender_name: "",
    sender_email: "",
    company_name: "",
    footer_text: "",
  });
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!activeId) return;
    setLoading(true);
    whiteLabel
      .get(activeId)
      .then((wl) => {
        setForm({
          logo_url: wl.logo_url ?? "",
          brand_color: wl.brand_color ?? "#111827",
          sender_name: wl.sender_name ?? "",
          sender_email: wl.sender_email ?? "",
          company_name: wl.company_name ?? "",
          footer_text: wl.footer_text ?? "",
        });
      })
      .catch(() => {
        // 404 = no config yet, use defaults
      })
      .finally(() => setLoading(false));
  }, [activeId]);

  const handleSave = async () => {
    if (!activeId) return;
    setSaving(true);
    setError(null);
    setSaved(false);
    try {
      await whiteLabel.upsert(activeId, form);
      setSaved(true);
      setTimeout(() => setSaved(false), 3000);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setSaving(false);
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
      <h1 className="text-2xl font-bold text-gray-900">Settings</h1>

      <div className="rounded-xl border bg-white overflow-hidden">
        <div className="px-5 py-3 border-b bg-gray-50 flex items-center gap-2">
          <Settings className="h-4 w-4 text-gray-600" />
          <span className="text-sm font-semibold text-gray-800">
            White-Label Configuration
          </span>
        </div>

        {loading ? (
          <div className="p-6 space-y-4">
            {[1, 2, 3].map((i) => (
              <div key={i} className="h-10 animate-pulse rounded bg-gray-100" />
            ))}
          </div>
        ) : (
          <div className="p-6 space-y-4">
            {error && (
              <div className="rounded-lg bg-red-50 border border-red-200 px-4 py-2 text-sm text-red-700">
                {error}
              </div>
            )}
            {saved && (
              <div className="rounded-lg bg-green-50 border border-green-200 px-4 py-2 text-sm text-green-700">
                Settings saved successfully.
              </div>
            )}

            <Field
              label="Company Name"
              value={form.company_name ?? ""}
              onChange={(v) => setForm({ ...form, company_name: v })}
              placeholder="Acme Corp"
            />
            <Field
              label="Logo URL"
              value={form.logo_url ?? ""}
              onChange={(v) => setForm({ ...form, logo_url: v })}
              placeholder="https://example.com/logo.png"
            />
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-xs font-medium text-gray-600 mb-1">
                  Brand Color
                </label>
                <div className="flex items-center gap-2">
                  <input
                    type="color"
                    value={form.brand_color ?? "#111827"}
                    onChange={(e) =>
                      setForm({ ...form, brand_color: e.target.value })
                    }
                    className="h-9 w-12 rounded border cursor-pointer"
                  />
                  <input
                    value={form.brand_color ?? "#111827"}
                    onChange={(e) =>
                      setForm({ ...form, brand_color: e.target.value })
                    }
                    className="flex-1 rounded-lg border px-3 py-2 text-sm font-mono focus:outline-none focus:ring-2 focus:ring-blue-500"
                  />
                </div>
              </div>
              <Field
                label="Sender Name"
                value={form.sender_name ?? ""}
                onChange={(v) => setForm({ ...form, sender_name: v })}
                placeholder="Acme Intelligence"
              />
            </div>
            <Field
              label="Sender Email"
              value={form.sender_email ?? ""}
              onChange={(v) => setForm({ ...form, sender_email: v })}
              placeholder="reports@acme.com"
            />
            <div>
              <label className="block text-xs font-medium text-gray-600 mb-1">
                Footer Text
              </label>
              <textarea
                value={form.footer_text ?? ""}
                onChange={(e) =>
                  setForm({ ...form, footer_text: e.target.value })
                }
                placeholder="Powered by Acme Intelligence Platform"
                rows={2}
                className="w-full rounded-lg border px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
            </div>

            <button
              onClick={handleSave}
              disabled={saving}
              className="inline-flex items-center gap-2 rounded-lg bg-gray-900 px-4 py-2 text-sm text-white hover:bg-gray-700 disabled:opacity-50 transition"
            >
              <Save className="h-4 w-4" />
              {saving ? "Saving..." : "Save Settings"}
            </button>
          </div>
        )}
      </div>
    </div>
  );
}

function Field({
  label,
  value,
  onChange,
  placeholder,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
}) {
  return (
    <div>
      <label className="block text-xs font-medium text-gray-600 mb-1">
        {label}
      </label>
      <input
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        className="w-full rounded-lg border px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
      />
    </div>
  );
}
