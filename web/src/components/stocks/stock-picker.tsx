"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import { Search } from "lucide-react";

import { EmptyState, ErrorState } from "@/components/common/states";
import { useScanner } from "@/components/providers/scanner-provider";
import { SignalBadge } from "@/components/stocks/signal-badge";
import { Skeleton } from "@/components/ui/skeleton";
import { displaySymbol, formatPrice } from "@/lib/format";
import { stockHref } from "@/lib/routes";

/** Stock Analysis landing page: choose a stock from the scanned universe. */
export function StockPicker() {
  const { scanner } = useScanner();
  const [query, setQuery] = useState("");
  const stocks = useMemo(() => {
    const q = query.trim().toUpperCase();
    return (scanner.data?.stocks ?? [])
      .filter((s) => !q || s.symbol.includes(q) || (s.name ?? "").toUpperCase().includes(q))
      .sort((a, b) => a.symbol.localeCompare(b.symbol));
  }, [scanner.data, query]);

  if (scanner.error && !scanner.data) return <ErrorState error={scanner.error} onRetry={() => void scanner.reload()} />;

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <p className="text-sm text-muted-foreground">Choose a stock to see its price history, moving averages and every crossover signal.</p>
        <div className="relative sm:w-72">
          <Search className="pointer-events-none absolute top-1/2 left-2.5 size-3.5 -translate-y-1/2 text-muted-foreground" aria-hidden />
          <input
            type="search"
            autoFocus
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Symbol or company name"
            aria-label="Find a stock"
            className="h-9 w-full rounded-md border bg-background pr-2 pl-8 text-sm outline-none placeholder:text-muted-foreground focus-visible:border-ring focus-visible:ring-2 focus-visible:ring-ring/30"
          />
        </div>
      </div>
      {scanner.loading ? (
        <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
          {Array.from({ length: 12 }, (_, i) => <Skeleton key={i} className="h-16 rounded-lg" />)}
        </div>
      ) : stocks.length === 0 ? (
        <div className="rounded-lg border"><EmptyState title="No matching stock" /></div>
      ) : (
        <ul className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
          {stocks.map((s) => (
            <li key={s.symbol}>
              <Link
                href={stockHref(s.symbol)}
                className="flex items-center justify-between gap-3 rounded-lg border bg-card px-3 py-2.5 outline-none transition-colors hover:border-foreground/30 focus-visible:ring-2 focus-visible:ring-ring/50"
              >
                <span className="min-w-0">
                  <span className="block text-[13px] font-medium">{displaySymbol(s.symbol)}</span>
                  <span className="block truncate text-xs text-muted-foreground">{s.name}</span>
                </span>
                <span className="flex shrink-0 flex-col items-end gap-1">
                  <span className="num text-[13px]">{formatPrice(s.close)}</span>
                  {s.signal !== "HOLD" && <SignalBadge signal={s.signal} />}
                </span>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
