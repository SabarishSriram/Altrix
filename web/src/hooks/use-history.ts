"use client";

import { useResource } from "@/hooks/use-resource";
import { api } from "@/lib/api";
import type { HistoryResponse } from "@/lib/types";

// Per-session cache keyed by symbol and data date, so flipping between stocks
// does not refetch; a new data date (after a refresh) fetches fresh history.
const cache = new Map<string, Promise<HistoryResponse>>();

function cachedHistory(symbol: string, asOf: string): Promise<HistoryResponse> {
  const key = `${symbol}@${asOf}`;
  let hit = cache.get(key);
  if (!hit) {
    hit = api.history(symbol);
    hit.catch(() => cache.delete(key)); // never cache failures
    cache.set(key, hit);
  }
  return hit;
}

/** History for `symbol`; `asOf` (the scanner's data date) keys the cache. */
export function useHistory(symbol: string | null, asOf: string | null | undefined) {
  const key = symbol ? `${symbol}@${asOf ?? "?"}` : null;
  return useResource(key, () => (asOf ? cachedHistory(symbol!, asOf) : api.history(symbol!)));
}
