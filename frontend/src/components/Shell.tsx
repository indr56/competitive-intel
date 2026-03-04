"use client";

import WorkspaceSwitcher from "./WorkspaceSwitcher";

export default function Shell({ children }: { children: React.ReactNode }) {
  return (
    <div className="pl-60 min-h-screen bg-gray-50">
      {/* Topbar */}
      <header className="sticky top-0 z-20 flex h-14 items-center justify-between border-b bg-white/80 backdrop-blur px-6">
        <WorkspaceSwitcher />
        <div className="flex items-center gap-3">
          <span className="text-xs text-gray-400">MVP</span>
          <div className="h-7 w-7 rounded-full bg-gray-200 flex items-center justify-center text-xs font-bold text-gray-600">
            U
          </div>
        </div>
      </header>

      {/* Page content */}
      <main className="p-6">{children}</main>
    </div>
  );
}
