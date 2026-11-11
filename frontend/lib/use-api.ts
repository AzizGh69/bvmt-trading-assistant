"use client";

import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";

interface Loaded<T> {
  key: string | null;
  data: T | null;
  error: string | null;
}

/**
 * Load one GET endpoint. A null path loads nothing (use it to wait for a
 * parameter). While a new path loads, the previous data stays available.
 */
export function useApi<T>(path: string | null) {
  const [tick, setTick] = useState(0);
  const [loaded, setLoaded] = useState<Loaded<T>>({ key: null, data: null, error: null });
  const key = path === null ? null : `${path}#${tick}`;

  useEffect(() => {
    if (path === null || key === null) return;
    let cancelled = false;
    api
      .get<T>(path)
      .then((data) => {
        if (!cancelled) setLoaded({ key, data, error: null });
      })
      .catch((e: Error) => {
        if (!cancelled) setLoaded((previous) => ({ key, data: previous.data, error: e.message }));
      });
    return () => {
      cancelled = true;
    };
  }, [path, key]);

  const reload = useCallback(() => setTick((t) => t + 1), []);
  const current = key !== null && loaded.key === key;
  return {
    data: path === null ? null : loaded.data,
    error: current ? loaded.error : null,
    loading: key !== null && !current,
    reload,
  };
}
