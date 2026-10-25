"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { ArrowLeft } from "lucide-react";

import { EmptyState, ErrorState } from "@/components/common/states";
import { useScanner } from "@/components/providers/scanner-provider";
import { ChartPanel } from "@/components/stocks/chart-panel";
import { CrossoverTable, CrossoversByYear } from "@/components/stocks/crossover-history";
import { SignalBadge } from "@/components/stocks/signal-badge";
import { CrossoverContext, StockStats } from "@/components/stocks/stock-stats";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { useHistory } from "@/hooks/use-history";
import { ApiError } from "@/lib/api";
import { displaySymbol, formatDate, formatNumber } from "@/lib/format";

function Panel({ title, description, children, className }: { title: string; description?: string; children: React.ReactNode; className?: string }) {
  return (
    <section className={`rounded-lg border bg-card ${className ?? ""}`}>
      <header className="border-b px-4 py-3">
        <h2 className="text-sm font-semibold">{title}</h2>
        {description && <p className="text-xs text-muted-foreground">{description}</p>}
      </header>
      <div className="p-4">{children}</div>
    </section>
  );
}

export function StockDetail() {
  const params = useParams<{ symbol: string }>();
  const symbol = decodeURIComponent(params.symbol).toUpperCase();
  const { scanner } = useScanner();
  const history = useHistory(symbol, scanner.data?.data_as_of);

  const back = (
    <Link href="/scanner" className="inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground">
      <ArrowLeft className="size-3.5" aria-hidden /> Stock Scanner
    </Link>
  );

  if (history.error) {
    const notFound = history.error instanceof ApiError && (history.error.status === 404 || history.error.status === 422);
    return (
      <div className="space-y-4">
        {back}
        {notFound ? (
          <div className="rounded-lg border">
            <EmptyState
              title={`${displaySymbol(symbol)} is not available`}
              description={history.error.message}
              action={<Button asChild variant="outline" size="sm"><Link href="/stocks">Choose another stock</Link></Button>}
            />
          </div>
        ) : (
          <ErrorState error={history.error} onRetry={() => void history.reload()} />
        )}
      </div>
    );
  }

  const h = history.data;
  if (!h) return <DetailSkeleton back={back} />;
  const stock = h.stock;
  const enoughHistory = stock.ema50 !== null;

  return (
    <div className="flex flex-col gap-5">
      <div className="space-y-2">
        {back}
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div>
            <div className="flex items-center gap-2.5">
              <h2 className="text-2xl font-semibold tracking-tight">{displaySymbol(stock.symbol)}</h2>
              <SignalBadge signal={stock.signal} />
            </div>
            <p className="text-sm text-muted-foreground">
              {h.name ?? stock.symbol} · NSE · {stock.symbol}
            </p>
          </div>
          <p className="num text-xs text-muted-foreground">
            {formatNumber(h.total_bars)} daily bars · {formatDate(h.start)} – {formatDate(h.end)}
          </p>
        </div>
      </div>

      <section className="space-y-4 rounded-lg border bg-card p-4">
        <StockStats stock={stock} className="lg:grid-cols-6" />
        <CrossoverContext stock={stock} />
      </section>

      <Panel title="Price and moving averages" description="Daily close with EMA20 and EMA50. Markers are the strategy's crossover days.">
        {h.points.length === 0 ? (
          <EmptyState title="No price history stored" />
        ) : (
          <>
            {!enoughHistory && (
              <p className="mb-3 text-xs text-muted-foreground">
                Only {h.total_bars} bars are stored; EMA50 needs 50, so no crossover signals can be generated yet.
              </p>
            )}
            <ChartPanel points={h.points} height={460} initial="1Y" />
          </>
        )}
      </Panel>

      <div className="grid gap-5 lg:grid-cols-[minmax(0,2fr)_minmax(0,3fr)]">
        <Panel title="Crossovers per year" description={`${h.crossovers.length} BUY/SELL signals in the stored history`}>
          <CrossoversByYear crossovers={h.crossovers} />
        </Panel>
        <Panel title="Signal history" description="Most recent first. A signal dated D uses D's close.">
          <div className="-m-4 max-h-80 overflow-y-auto">
            <CrossoverTable crossovers={h.crossovers} />
          </div>
        </Panel>
      </div>
      <p className="text-xs text-muted-foreground">
        Backtested performance for this strategy is on the Backtesting page. Research only, not investment advice.
      </p>
    </div>
  );
}

function DetailSkeleton({ back }: { back: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-5" aria-busy="true">
      <div className="space-y-2">
        {back}
        <Skeleton className="h-8 w-48" />
        <Skeleton className="h-4 w-64" />
      </div>
      <Skeleton className="h-28 w-full rounded-lg" />
      <Skeleton className="h-[540px] w-full rounded-lg" />
    </div>
  );
}
