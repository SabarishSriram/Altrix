"use client";

import { useCallback, useEffect, useRef, useState } from "react";

export interface Resource<T> {
  data: T | undefined;
  error: Error | undefined;
  /** First load, nothing to show yet. */
  loading: boolean;
  /** Reloading while previous data stays visible. */
  reloading: boolean;
  reload: () => Promise<void>;
}

/**
 * Fetch on mount and whenever `key` changes; `reload()` refetches in place.
 * Responses that arrive after a newer request started are ignored.
 * Pass `key = null` to skip fetching.
 */
export function useResource<T>(key: string | null, fetcher: () => Promise<T>): Resource<T> {
  const [state, setState] = useState<{ key: string | null; data?: T; error?: Error; pending: boolean }>({
    key,
    pending: key !== null,
  });
  const requestId = useRef(0);
  const fetcherRef = useRef(fetcher);
  useEffect(() => {
    fetcherRef.current = fetcher;
  });

  const run = useCallback(async (k: string | null) => {
    if (k === null) return;
    const id = ++requestId.current;
    setState((s) => ({ ...s, key: k, pending: true, error: undefined }));
    try {
      const data = await fetcherRef.current();
      if (id === requestId.current) setState({ key: k, data, pending: false });
    } catch (e) {
      if (id === requestId.current) {
        setState((s) => ({ ...s, pending: false, error: e instanceof Error ? e : new Error(String(e)) }));
      }
    }
  }, []);

  useEffect(() => {
    void run(key);
  }, [key, run]);

  const reload = useCallback(() => run(key), [key, run]);
  const sameKey = state.key === key;
  const data = sameKey ? state.data : undefined;
  return {
    data,
    error: sameKey ? state.error : undefined,
    loading: key !== null && data === undefined && (!sameKey || state.pending),
    reloading: data !== undefined && state.pending,
    reload,
  };
}
