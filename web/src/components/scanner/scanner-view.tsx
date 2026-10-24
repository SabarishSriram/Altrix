"use client";

import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { AlertTriangle, Search } from "lucide-react";

import { EmptyState, ErrorState } from "@/components/common/states";
import { useScanner } from "@/components/providers/scanner-provider";
import { ScannerSummary } from "@/components/scanner/scanner-summary";
import { SIGNAL_FILTERS, SignalTabs, matchesFilter, type SignalFilter } from "@/components/scanner/signal-tabs";
import { StockPreview } from "@/components/scanner/stock-preview";
import { StocksTable } from "@/components/scanner/stocks-table";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { formatDate } from "@/lib/format";
import { stockHref } from "@/lib/routes";

const PREVIEW_QUERY = "(min-width: 1280px)";

function useMediaQuery(query: string): boolean {
  const [matches, setMatches] = useState(false);
  useEffect(() => {
    const mql = window.matchMedia(query);
    const update = () => setMatches(mql.matches);
    update();
    mql.addEventListener("change", update);
    return () => mql.removeEventListener("change", update);
  }, [query]);
  return matches;
}

function parseFilter(v: string | null): SignalFilter {
  return SIGNAL_FILTERS.some((f) => f.key === v) ? (v as SignalFilter) : "ALL";
}

export function ScannerView() {
  const { scanner } = useScanner();
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();
  const wide = useMediaQuery(PREVIEW_QUERY);
  const [query, setQuery] = useState("");

  const filter = parseFilter(params.get("signal"));
  const selected = params.get("selected");

  const setParams = (next: Record<string, string | null>) => {
    const p = new URLSearchParams(params.toString());
    for (const [k, v] of Object.entries(next)) {
      if (v === null) p.delete(k);
      else p.set(k, v);
    }
    const qs = p.toString();
    router.replace(qs ? `${pathname}?${qs}` : pathname, { scroll: false });
  };

  const data = scanner.data;
  const stocks = useMemo(() => {
    if (!data) return [];
    const q = query.trim().toUpperCase();
    return data.stocks.filter(
      (s) => matchesFilter(s.signal, filter) && (!q || s.symbol.includes(q) || (s.name ?? "").toUpperCase().includes(q)),
    );
  }, [data, filter, query]);

  const selectedStock = wide && selected ? data?.stocks.find((s) => s.symbol === selected) : undefined;

  const onSelect = (symbol: string) => {
    if (wide) setParams({ selected: symbol === selected ? null : symbol });
    else router.push(stockHref(symbol));
  };

  if (scanner.error && !data) {
    return <ErrorState error={scanner.error} onRetry={() => void scanner.reload()} title="Scanner unavailable" />;
  }

  const emptyMessage =
    query.trim() !== "" ? (
      <EmptyState title="No matching stocks" description={`Nothing matches “${query.trim()}” in this view.`} action={
        <Button variant="outline" size="sm" onClick={() => setQuery("")}>Clear search</Button>
      } />
    ) : filter === "BUY" ? (
      <EmptyState title="No BUY signals today" description={`No stock had SMA20 cross above SMA50 on ${formatDate(data?.data_as_of)}.`} />
    ) : filter === "SELL" ? (
      <EmptyState title="No SELL signals today" description={`No stock had SMA20 cross below SMA50 on ${formatDate(data?.data_as_of)}.`} />
    ) : (
      <EmptyState title="No stocks in this view" />
    );

  return (
    <div className="flex flex-col gap-5">
      <ScannerSummary data={data} loading={scanner.loading} />

      {data?.is_stale && (
        <Alert>
          <AlertTriangle className="size-4" />
          <AlertTitle>Stored data may be out of date</AlertTitle>
          <AlertDescription>
            The latest bar is from {formatDate(data.data_as_of)}. Use Refresh → Download new bars to fetch newer end-of-day data.
          </AlertDescription>
        </Alert>
      )}
      {data && data.failed_symbols.length > 0 && (
        <Alert>
          <AlertTriangle className="size-4" />
          <AlertTitle>{data.failed_symbols.length} constituent(s) could not be scanned</AlertTitle>
          <AlertDescription>
            {data.failed_symbols.map((f) => `${f.symbol} (${f.reason})`).join("; ")}
          </AlertDescription>
        </Alert>
      )}

      <div className="grid items-start gap-5 xl:grid-cols-[minmax(0,1fr)_400px]">
        <section aria-label="Stocks" className="min-w-0 overflow-hidden rounded-lg border bg-card">
          <div className="flex flex-col gap-3 border-b px-3 pt-2 sm:flex-row sm:items-end sm:justify-between">
            <SignalTabs value={filter} onChange={(f) => setParams({ signal: f === "ALL" ? null : f })} data={data} />
            <div className="flex items-center gap-3 pb-2">
              <p className="num text-xs whitespace-nowrap text-muted-foreground" aria-live="polite">
                {data ? `${stocks.length} of ${data.scanned_count} stocks` : "Loading…"}
              </p>
              <div className="relative w-full sm:w-52">
                <Search className="pointer-events-none absolute top-1/2 left-2.5 size-3.5 -translate-y-1/2 text-muted-foreground" aria-hidden />
                <input
                  type="search"
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  placeholder="Filter by symbol or name"
                  aria-label="Filter stocks by symbol or name"
                  className="h-8 w-full rounded-md border bg-background pr-2 pl-8 text-[13px] outline-none placeholder:text-muted-foreground focus-visible:border-ring focus-visible:ring-2 focus-visible:ring-ring/30"
                />
              </div>
            </div>
          </div>
          <StocksTable
            stocks={stocks}
            loading={scanner.loading}
            selected={selectedStock?.symbol}
            onSelect={onSelect}
            empty={emptyMessage}
          />
        </section>

        <aside className="hidden xl:sticky xl:top-28 xl:block">
          {selectedStock ? (
            <StockPreview
              key={selectedStock.symbol}
              stock={selectedStock}
              asOf={data?.data_as_of ?? null}
              onClose={() => setParams({ selected: null })}
            />
          ) : (
            <div className="rounded-lg border border-dashed bg-card">
              <EmptyState
                title="Select a stock"
                description="Click a row to preview its price, moving averages and crossover history here."
              />
            </div>
          )}
        </aside>
      </div>

      <p className="text-xs leading-relaxed text-muted-foreground">
        Signals come from the Python baseline strategy (20/50-day SMA crossover) on stored end-of-day data. A signal dated D uses D&apos;s
        close, so it is known only after the close; the backtester would act at the next trading day&apos;s open. Research only, not
        investment advice.
      </p>
    </div>
  );
}
