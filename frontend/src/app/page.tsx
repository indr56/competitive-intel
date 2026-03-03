import { Activity, Eye, Zap, Mail } from "lucide-react";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export default function Home() {
  return (
    <div className="min-h-screen bg-gray-50">
      {/* Nav */}
      <nav className="border-b bg-white">
        <div className="mx-auto max-w-6xl flex items-center justify-between px-6 py-4">
          <h1 className="text-lg font-bold text-gray-900">
            Competitive Moves Intelligence
          </h1>
          <div className="flex gap-6 text-sm text-gray-600">
            <a href="/competitors" className="hover:text-gray-900">
              Competitors
            </a>
            <a href="/changes" className="hover:text-gray-900">
              Changes
            </a>
            <a href="/digests" className="hover:text-gray-900">
              Digests
            </a>
          </div>
        </div>
      </nav>

      {/* Hero */}
      <main className="mx-auto max-w-6xl px-6 py-16">
        <div className="text-center mb-16">
          <h2 className="text-4xl font-bold text-gray-900 mb-4">
            Know what your competitors change — before your team asks.
          </h2>
          <p className="text-lg text-gray-500 max-w-2xl mx-auto">
            Automated tracking of competitor pricing, positioning, features, and
            CTAs. AI-powered insights delivered to your inbox weekly.
          </p>
        </div>

        {/* Feature cards */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
          <Card
            icon={<Eye className="w-6 h-6 text-blue-600" />}
            title="Capture"
            description="Rendered screenshots + extracted text from competitor pages, on autopilot."
          />
          <Card
            icon={<Activity className="w-6 h-6 text-orange-600" />}
            title="Diff & Classify"
            description="Noise-suppressed diffs with AI classification: pricing, CTA, positioning, and more."
          />
          <Card
            icon={<Zap className="w-6 h-6 text-purple-600" />}
            title="AI Insights"
            description="What changed, why it matters, next moves, battlecard blocks, and sales talk tracks."
          />
          <Card
            icon={<Mail className="w-6 h-6 text-green-600" />}
            title="Weekly Digest"
            description="Curated email + shareable web view. White-label ready for agencies."
          />
        </div>

        {/* Quick status */}
        <div className="mt-16 rounded-xl border bg-white p-8">
          <h3 className="text-lg font-semibold text-gray-900 mb-4">
            System Status
          </h3>
          <p className="text-sm text-gray-500 mb-4">
            API:{" "}
            <code className="bg-gray-100 px-2 py-0.5 rounded text-xs">
              {API_URL}
            </code>
          </p>
          <div className="flex gap-4">
            <a
              href={`${API_URL}/health`}
              target="_blank"
              className="inline-flex items-center gap-2 rounded-lg bg-gray-900 px-4 py-2 text-sm text-white hover:bg-gray-700 transition"
            >
              Check Health
            </a>
            <a
              href={`${API_URL}/docs`}
              target="_blank"
              className="inline-flex items-center gap-2 rounded-lg border border-gray-300 px-4 py-2 text-sm text-gray-700 hover:bg-gray-50 transition"
            >
              API Docs (Swagger)
            </a>
          </div>
        </div>
      </main>
    </div>
  );
}

function Card({
  icon,
  title,
  description,
}: {
  icon: React.ReactNode;
  title: string;
  description: string;
}) {
  return (
    <div className="rounded-xl border bg-white p-6 hover:shadow-md transition">
      <div className="mb-3">{icon}</div>
      <h3 className="font-semibold text-gray-900 mb-1">{title}</h3>
      <p className="text-sm text-gray-500">{description}</p>
    </div>
  );
}
