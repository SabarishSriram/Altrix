"use client";

import Link from "next/link";
import { ArrowRight } from "lucide-react";
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { cn } from "cn";

import { EmptyState, ErrorState } from "@/components/common/states";
import { useScanner } from "@/components/providers/scanner-provider";
import { ScannerSummary } from "@/components/scanner/scanner-summary";
import { SignalBadge } from "@/components/stocks/signal-badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { useResource } from "@/hooks/use-resource";
import { CHART } from "@/lib/chart-theme";
import { api } from "@/lib/api";
import { displaySymbol, formatDate, formatPrice } from "@/lib/format";
import { stockHref } from "@/lib/routes";
import type { DailySignalCount } from "@/lib/types";

const RECENT_DAYS = 30;

function Panel({ title, description, action, children }: { title: string; description?: string; action?: React.ReactNode; children: React.ReactNode }) {
  return (
    <section className="flex min-w-0 flex-col rounded-lg border bg-card">
      <header className="flex items-start justify-between gap-3 border-b px-4 py-3">
        <div>
          <h2 className="text-sm font-semibold">{title}</h2>
          {description && <p className="text-xs text-muted-foreground">{description}</p>}
        </div>
        {action}
      </header>
      <div className="flex-1">{children}</div>
    </section>
  );
}

function DailyCrossoverChart({ data }: { data: DailySignalCount[] }) {
  const rows = data.map((d) => ({ ...d, label: formatDate(d.date, "dd MMM"), sellNeg: -d.sell }));
  return (
    <div className="h-56 w-full px-2 pt-3 pb-1">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={rows} margin={{ top: 4, right: 8, bottom: 0, left: -28 }} stackOffset="sign">
          <CartesianGrid vertical={false} stroke={CHART.grid} />
          <XAxis dataKey="label" tickLine={false} axisLine={false} tick={CHART.axisTick} interval="preserveStartEnd" minTickGap={16} />
          <YAxis allowDecimals={false} tickLine={false} axisLine={false} tick={CHART.axisTick} tickFormatter={(v: number) => String(Math.abs(v))} />
          <Tooltip
            cursor={{ fill: CHART.cursor }}
            contentStyle={CHART.tooltip}
            formatter={(value, name) => [Math.abs(Number(value)), name]}
          />
          <Bar dataKey="buy" name="BUY" stackId="s" fill={CHART.gain} maxBarSize={12} />
          <Bar dataKey="sellNeg" name="SELL" stackId="s" fill={CHART.loss} maxBarSize={12} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

export function OverviewView() {
  const { scanner } = useScanner();
  const asOf = scanner.data?.data_as_of ?? null;
  const recent = useResource(asOf ? `recent:${asOf}` : null, () => api.recentSignals(RECENT_DAYS));

  if (scanner.error && !scanner.data) {
    return <ErrorState error={scanner.error} onRetry={() => void scanner.reload()} title="Scanner unavailable" />;
  }

  const current = scanner.data?.stocks.filter((s) => s.signal === "BUY" || s.signal === "SELL") ?? [];

  return (
    <div className="flex flex-col gap-5">
      <ScannerSummary data={scanner.data} loading={scanner.loading} />

      <div className="grid gap-5 lg:grid-cols-2">
        <Panel
          title="Signals on the latest trading day"
          description={asOf ? `Fresh crossovers on ${formatDate(asOf)}` : "Loading…"}
          action={
            <Button asChild variant="outline" size="sm">
              <Link href="/scanner">
                Open scanner <ArrowRight className="size-3.5" aria-hidden />
              </Link>
            </Button>
          }
        >
          {scanner.loading ? (
            <div className="space-y-3 p-4">{[0, 1, 2].map((i) => <Skeleton key={i} className="h-9 w-full" />)}</div>
          ) : current.length === 0 ? (
            <EmptyState
              title="No new BUY or SELL signals"
              description={`No stock's EMA20 crossed its EMA50 on ${formatDate(asOf)}. All ${scanner.data?.scanned_count ?? ""} stocks are HOLD.`}
            />
          ) : (
            <ul className="divide-y">
              {current.map((s) => (
                <li key={s.symbol}>
                  <Link href={stockHref(s.symbol)} className="flex items-center gap-3 px-4 py-2.5 outline-none hover:bg-muted/50 focus-visible:bg-muted">
                    <SignalBadge signal={s.signal} />
                    <span className="min-w-0 flex-1">
                      <span className="block text-[13px] font-medium">{displaySymbol(s.symbol)}</span>
                      <span className="block truncate text-xs text-muted-foreground">{s.name}</span>
                    </span>
                    <span className="num text-[13px]">{formatPrice(s.close)}</span>
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </Panel>

        <Panel
          title="Crossovers per trading day"
          description={`BUY (up) and SELL (down) signals across today's constituents, last ${RECENT_DAYS} trading days. Strategy history, not stored scan snapshots.`}
        >
          {recent.error ? (
            <ErrorState error={recent.error} onRetry={() => void recent.reload()} className="m-4 py-6" />
          ) : recent.data ? (
            <DailyCrossoverChart data={recent.data.daily_counts} />
          ) : (
            <div className="p-4"><Skeleton className="h-48 w-full" /></div>
          )}
        </Panel>
      </div>

      <Panel title="Recent crossovers" description={`Past BUY/SELL signals from the last ${RECENT_DAYS} trading days, for context. Only signals on the latest date are current.`}>
        {recent.error ? null : !recent.data ? (
          <div className="space-y-2 p-4">{[0, 1, 2, 3].map((i) => <Skeleton key={i} className="h-7 w-full" />)}</div>
        ) : recent.data.crossovers.length === 0 ? (
          <EmptyState title="No crossovers in this period" />
        ) : (
          <div className="max-h-96 overflow-auto">
            <table className="w-full text-[13px]">
              <thead className="sticky top-0 border-b bg-surface text-left text-xs text-muted-foreground">
                <tr>
                  <th scope="col" className="h-8 px-4 font-medium">Date</th>
                  <th scope="col" className="h-8 px-4 font-medium">Stock</th>
                  <th scope="col" className="h-8 px-4 font-medium">Signal</th>
                  <th scope="col" className="h-8 px-4 text-right font-medium">Close</th>
                </tr>
              </thead>
              <tbody>
                {recent.data.crossovers.map((c) => (
                  <tr key={`${c.date}-${c.symbol}`} className="border-b last:border-b-0 hover:bg-muted/40">
                    <td className={cn("num px-4 py-1.5", c.date === asOf ? "font-medium" : "text-muted-foreground")}>{formatDate(c.date)}</td>
                    <td className="px-4 py-1.5">
                      <Link href={stockHref(c.symbol)} className="font-medium hover:underline">{displaySymbol(c.symbol)}</Link>
                      <span className="ml-2 hidden text-xs text-muted-foreground sm:inline">{c.name}</span>
                    </td>
                    <td className="px-4 py-1.5"><SignalBadge signal={c.signal} /></td>
                    <td className="num px-4 py-1.5 text-right">{formatPrice(c.close)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Panel>
    </div>
  );
}
