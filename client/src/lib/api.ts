// The only place the frontend talks to the Altrix API. No market data is
// computed here or anywhere else in the frontend: Python is the source of truth.

import type {
  BacktestParams,
  BacktestResponse,
  HealthResponse,
  HistoryResponse,
  MetaResponse,
  RecentSignalsResponse,
  RefreshStatus,
  ScannerResponse,
} from "@/lib/types";

export const API_BASE_URL = (process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000").replace(/\/+$/, "");

export class ApiError extends Error {
  constructor(
    message: string,
    /** HTTP status, or 0 when the API could not be reached. */
    readonly status: number,
  ) {
    super(message);
    this.name = "ApiError";
  }

  get unreachable(): boolean {
    return this.status === 0;
  }
}

async function request<T>(path: string, init?: RequestInit & { allowStatus?: number[] }): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${API_BASE_URL}${path}`, {
      ...init,
      headers: { Accept: "application/json", ...init?.headers },
      cache: "no-store",
    });
  } catch {
    throw new ApiError(`Cannot reach the Altrix API at ${API_BASE_URL}. Is it running?`, 0);
  }
  if (!res.ok && !init?.allowStatus?.includes(res.status)) {
    throw new ApiError(await errorDetail(res), res.status);
  }
  return (await res.json()) as T;
}

async function errorDetail(res: Response): Promise<string> {
  try {
    const body: unknown = await res.json();
    if (body && typeof body === "object" && "detail" in body) {
      const detail = (body as { detail: unknown }).detail;
      if (typeof detail === "string") return detail;
      if (Array.isArray(detail)) {
        return detail
          .map((d) => (d && typeof d === "object" && "msg" in d ? String((d as { msg: unknown }).msg) : String(d)))
          .join("; ");
      }
    }
  } catch {
    // fall through to the status text
  }
  return `Request failed (${res.status} ${res.statusText})`;
}

/** Yahoo tickers contain '&' (M&M.NS), so path segments must be encoded. */
export const symbolPath = (symbol: string) => encodeURIComponent(symbol);

export const api = {
  health: () => request<HealthResponse>("/health"),
  meta: () => request<MetaResponse>("/api/meta"),
  scanner: () => request<ScannerResponse>("/api/scanner"),
  history: (symbol: string) => request<HistoryResponse>(`/api/scanner/${symbolPath(symbol)}/history`),
  recentSignals: (days = 30) => request<RecentSignalsResponse>(`/api/signals/recent?days=${days}`),
  backtest: (params: BacktestParams) => {
    const q = new URLSearchParams({
      initial_capital: String(params.initial_capital),
      transaction_cost: String(params.transaction_cost),
      max_position_weight: String(params.max_position_weight),
      years: String(params.years),
    });
    return request<BacktestResponse>(`/api/backtest?${q}`);
  },
  refreshStatus: () => request<RefreshStatus>("/api/refresh"),
  /** Rescan stored data (synchronous) or start the incremental download (202, or 409 if one is running). */
  refresh: (download: boolean) =>
    request<RefreshStatus>(`/api/refresh?download=${download}`, { method: "POST", allowStatus: [409] }),
};

export function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : "Something went wrong.";
}
