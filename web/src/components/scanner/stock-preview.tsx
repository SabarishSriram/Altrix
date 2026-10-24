"use client";

import Link from "next/link";
import { ArrowRight, X } from "lucide-react";

import { ErrorState } from "@/components/common/states";
import { ChartPanel } from "@/components/stocks/chart-panel";
import { CrossoverContext, StockStats } from "@/components/stocks/stock-stats";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { useHistory } from "@/hooks/use-history";
import { displaySymbol } from "@/lib/format";
import { stockHref } from "@/lib/routes";
import type { StockScan } from "@/lib/types";

/** Side panel for the selected scanner row (desktop). */
export function StockPreview({ stock, asOf, onClose }: { stock: StockScan; asOf: string | null; onClose: () => void }) {
  const history = useHistory(stock.symbol, asOf);

  return (
    <section aria-label={`${displaySymbol(stock.symbol)} preview`} className="flex flex-col gap-4 rounded-lg border bg-card p-4">
      <header className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <h2 className="text-base font-semibold tracking-tight">{displaySymbol(stock.symbol)}</h2>
          <p className="truncate text-xs text-muted-foreground">{stock.name ?? stock.symbol}</p>
        </div>
        <Button variant="ghost" size="icon-sm" onClick={onClose} aria-label="Close preview">
          <X className="size-4" />
        </Button>
      </header>
      <StockStats stock={stock} className="sm:grid-cols-3" />
      <CrossoverContext stock={stock} />
      <div className="border-t pt-3">
        {history.error ? (
          <ErrorState error={history.error} onRetry={() => void history.reload()} className="py-6" />
        ) : history.data ? (
          <ChartPanel points={history.data.points} height={240} initial="6M" showVolume={false} />
        ) : (
          <div className="space-y-3">
            <Skeleton className="h-7 w-48" />
            <Skeleton className="h-[240px] w-full" />
          </div>
        )}
      </div>
      <Button asChild className="w-full">
        <Link href={stockHref(stock.symbol)}>
          Open full analysis
          <ArrowRight className="size-3.5" aria-hidden />
        </Link>
      </Button>
    </section>
  );
}
