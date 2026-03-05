"use client";

import { useCallback, useEffect, useState } from "react";
import { workspaces } from "./api";
import type { Workspace } from "./types";

// ── Workspace context (simple global state for MVP) ──

let _cachedWorkspaces: Workspace[] | null = null;
let _activeWorkspaceId: string | null = null;
let _fetching = false;
const _listeners = new Set<() => void>();

function notify() {
  _listeners.forEach((fn) => fn());
}

export function invalidateWorkspaceCache() {
  _cachedWorkspaces = null;
  _fetching = false;
}

function ensureFetched() {
  if (_cachedWorkspaces || _fetching) return;
  _fetching = true;
  workspaces
    .list()
    .then((data) => {
      _cachedWorkspaces = data;
      if (data.length > 0 && !_activeWorkspaceId) {
        _activeWorkspaceId = data[0].id;
      }
      notify();
    })
    .catch(() => {
      _fetching = false;
    });
}

export function useWorkspaces() {
  const [, rerender] = useState(0);
  const wsList = _cachedWorkspaces ?? [];
  const loading = !_cachedWorkspaces;

  useEffect(() => {
    const handler = () => rerender((n) => n + 1);
    _listeners.add(handler);
    ensureFetched();
    return () => { _listeners.delete(handler); };
  }, []);

  return { workspaces: wsList, loading, error: null as string | null };
}

export function useActiveWorkspace() {
  const [, rerender] = useState(0);
  const { workspaces: wsList, loading } = useWorkspaces();

  useEffect(() => {
    const handler = () => rerender((n) => n + 1);
    _listeners.add(handler);
    return () => { _listeners.delete(handler); };
  }, []);

  // Always read from the global — never stale
  const activeId = _activeWorkspaceId;

  const setActive = useCallback((id: string) => {
    _activeWorkspaceId = id;
    notify();
  }, []);

  const active = wsList.find((w) => w.id === activeId) ?? null;
  return { active, activeId, setActive, workspaces: wsList, loading };
}

// ── Generic fetch hook ──

export function useFetch<T>(
  fetcher: () => Promise<T>,
  deps: unknown[] = []
) {
  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refetch = useCallback(() => {
    setLoading(true);
    setError(null);
    fetcher()
      .then(setData)
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);

  useEffect(() => {
    refetch();
  }, [refetch]);

  return { data, loading, error, refetch };
}
