"use client";

import { useCallback, useEffect, useState } from "react";
import { workspaces } from "./api";
import type { Workspace } from "./types";

// ── Workspace context (simple global state for MVP) ──

let _cachedWorkspaces: Workspace[] | null = null;
let _activeWorkspaceId: string | null = null;
const _listeners = new Set<() => void>();

function notify() {
  _listeners.forEach((fn) => fn());
}

export function useWorkspaces() {
  const [wsList, setWsList] = useState<Workspace[]>(_cachedWorkspaces ?? []);
  const [loading, setLoading] = useState(!_cachedWorkspaces);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (_cachedWorkspaces) return;
    setLoading(true);
    workspaces
      .list()
      .then((data) => {
        _cachedWorkspaces = data;
        setWsList(data);
        if (data.length > 0 && !_activeWorkspaceId) {
          _activeWorkspaceId = data[0].id;
          notify();
        }
      })
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false));
  }, []);

  return { workspaces: wsList, loading, error };
}

export function useActiveWorkspace() {
  const [activeId, setActiveId] = useState<string | null>(_activeWorkspaceId);
  const { workspaces: wsList, loading } = useWorkspaces();

  useEffect(() => {
    const handler = () => setActiveId(_activeWorkspaceId);
    _listeners.add(handler);
    return () => { _listeners.delete(handler); };
  }, []);

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
