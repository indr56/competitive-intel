"use client";

import { useState } from "react";
import { ChevronDown, Plus, Check } from "lucide-react";
import { useActiveWorkspace } from "@/lib/hooks";
import { workspaces as wsApi } from "@/lib/api";

export default function WorkspaceSwitcher() {
  const { active, activeId, setActive, workspaces, loading } =
    useActiveWorkspace();
  const [open, setOpen] = useState(false);
  const [creating, setCreating] = useState(false);
  const [name, setName] = useState("");

  const handleCreate = async () => {
    if (!name.trim()) return;
    const slug = name.trim().toLowerCase().replace(/\s+/g, "-");
    const ws = await wsApi.create({ name: name.trim(), slug });
    setActive(ws.id);
    setName("");
    setCreating(false);
    setOpen(false);
    window.location.reload();
  };

  if (loading) {
    return (
      <div className="h-9 w-48 animate-pulse rounded-lg bg-gray-100" />
    );
  }

  return (
    <div className="relative">
      <button
        onClick={() => setOpen(!open)}
        className="flex items-center gap-2 rounded-lg border bg-white px-3 py-1.5 text-sm font-medium text-gray-700 hover:bg-gray-50 transition"
      >
        <span className="truncate max-w-[160px]">
          {active?.name ?? "Select workspace"}
        </span>
        <ChevronDown className="h-3.5 w-3.5 text-gray-400" />
      </button>

      {open && (
        <>
          <div
            className="fixed inset-0 z-40"
            onClick={() => {
              setOpen(false);
              setCreating(false);
            }}
          />
          <div className="absolute left-0 top-full z-50 mt-1 w-64 rounded-lg border bg-white shadow-lg">
            <div className="max-h-60 overflow-y-auto p-1">
              {workspaces.map((ws) => (
                <button
                  key={ws.id}
                  onClick={() => {
                    setActive(ws.id);
                    setOpen(false);
                  }}
                  className="flex w-full items-center justify-between rounded-md px-3 py-2 text-sm text-gray-700 hover:bg-gray-50"
                >
                  <span className="truncate">{ws.name}</span>
                  {ws.id === activeId && (
                    <Check className="h-3.5 w-3.5 text-blue-600" />
                  )}
                </button>
              ))}
            </div>
            <div className="border-t p-2">
              {creating ? (
                <div className="flex gap-1.5">
                  <input
                    autoFocus
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    onKeyDown={(e) => e.key === "Enter" && handleCreate()}
                    placeholder="Workspace name"
                    className="flex-1 rounded border px-2 py-1 text-xs"
                  />
                  <button
                    onClick={handleCreate}
                    className="rounded bg-blue-600 px-2 py-1 text-xs text-white hover:bg-blue-500"
                  >
                    Add
                  </button>
                </div>
              ) : (
                <button
                  onClick={() => setCreating(true)}
                  className="flex w-full items-center gap-2 rounded-md px-3 py-1.5 text-xs text-gray-500 hover:bg-gray-50"
                >
                  <Plus className="h-3 w-3" /> New workspace
                </button>
              )}
            </div>
          </div>
        </>
      )}
    </div>
  );
}
