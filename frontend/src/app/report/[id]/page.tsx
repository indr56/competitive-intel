"use client";

import { useEffect, useState } from "react";
import { useParams, useSearchParams } from "next/navigation";
import { API_URL } from "@/lib/api";

export default function PublicReportPage() {
  const params = useParams();
  const searchParams = useSearchParams();
  const id = params.id as string;
  const sig = searchParams.get("sig") ?? "";
  const exp = searchParams.get("exp") ?? "";
  const [html, setHtml] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!sig || !exp) {
      setError("Missing signature or expiry parameters.");
      setLoading(false);
      return;
    }

    fetch(
      `${API_URL}/api/report/${id}?sig=${encodeURIComponent(sig)}&exp=${exp}`
    )
      .then(async (res) => {
        if (!res.ok) {
          const body = await res.text();
          throw new Error(
            res.status === 403
              ? "This link has expired or is invalid."
              : `Error ${res.status}: ${body}`
          );
        }
        const ct = res.headers.get("content-type") ?? "";
        if (ct.includes("text/html")) {
          return res.text();
        }
        // JSON fallback
        const json = await res.json();
        return `<pre style="font-family:monospace;white-space:pre-wrap;padding:20px;">${JSON.stringify(json, null, 2)}</pre>`;
      })
      .then((body) => setHtml(body ?? null))
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, [id, sig, exp]);

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-50">
        <div className="text-center">
          <div className="h-8 w-8 animate-spin rounded-full border-2 border-gray-300 border-t-blue-600 mx-auto mb-4" />
          <p className="text-sm text-gray-500">Loading report...</p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-50">
        <div className="text-center max-w-md">
          <h1 className="text-xl font-bold text-gray-900 mb-2">
            Report Unavailable
          </h1>
          <p className="text-sm text-gray-500">{error}</p>
        </div>
      </div>
    );
  }

  if (!html) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-50">
        <p className="text-gray-400">No content available.</p>
      </div>
    );
  }

  return (
    <iframe
      srcDoc={html}
      className="w-full min-h-screen border-0"
      title="Competitive Intel Report"
    />
  );
}
