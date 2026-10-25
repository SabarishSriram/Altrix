"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import { Loader2, Play } from "lucide-react";
import { cn } from "cn";

import { DrawdownChart, EquityChart } from "@/components/backtest/backtest-charts";
import { MetricCard } from "@/components/common/metric-card";
import { EmptyState, ErrorState } from "@/components/common/states";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import { useResource } from "@/hooks/use-resource";
import { api } from "@/lib/api";
import { displaySymbol, formatDate, formatFraction, formatNumber, formatPrice, trend, trendClass } from "@/lib/format";
import { stockHref } from "@/lib/routes";
import type { BacktestParams, BacktestResponse } from "@/lib/types";

const TRADE_PAGE = 50;
const PERIODS = [1, 2, 3, 5, 10] as const;
const DEFAULT_YEARS = 10;

interface FormState {
  capital: string;
  costPct: string;
  weightPct: string;
  years: number;
}

function toParams(f: FormState): BacktestParams | string {
  const capital = Number(f.capital);
  const cost = Number(f.costPct) / 100;
  const weight = Number(f.weightPct) / 100;
  if (!Number.isFinite(capital) || capital <= 0) return "Initial capital must be greater than zero.";
  if (!Number.isFinite(cost) || cost < 0 || cost >= 1) return "Transaction cost must be between 0% and 100%.";
  if (!Number.isFinite(weight) || weight <= 0 || weight > 1) return "Maximum position weight must be above 0% and at most 100%.";
  return { initial_capital: capital, transaction_cost: cost, max_position_weight: weight, years: f.years };
}

function Field({ id, label, hint, children }: { id: string; label: string; hint?: string; children: React.ReactNode }) {
  return (
    <div className="space-y-1.5">
      <Label htmlFor={id} className="text-xs font-medium text-muted-foreground">{label}</Label>
      {children}
      {hint && <p className="text-[11px] text-muted-foreground">{hint}</p>}
    </div>
  );
}

const inputClass =
  "num h-8 w-full rounded-md border bg-background px-2.5 text-[13px] outline-none focus-visible:border-ring focus-visible:ring-2 focus-visible:ring-ring/30";

export function BacktestView() {
  const meta = useResource("meta", api.meta);
  const [form, setForm] = useState<FormState | null>(null);
  const [run, setRun] = useState<BacktestParams | null>(null);
  const [formError, setFormError] = useState<string | null>(null);

  const defaults = meta.data?.backtest_defaults;
  const f: FormState = form ?? {
    capital: String(defaults?.initial_capital ?? 100000),
    costPct: String((defaults?.transaction_cost ?? 0.001) * 100),
    weightPct: String((defaults?.max_position_weight ?? 0.1) * 100),
    years: DEFAULT_YEARS,
  };
  const set = (k: keyof FormState) => (e: React.ChangeEvent<HTMLInputElement>) => setForm({ ...f, [k]: e.target.value });

  const result = useResource(run ? JSON.stringify(run) : null, () => api.backtest(run!));

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    const p = toParams(f);
    if (typeof p === "string") return setFormError(p);
    setFormError(null);
    if (run && JSON.stringify(p) === JSON.stringify(run)) void result.reload();
    else setRun(p);
  };

  const busy = result.loading || result.reloading;

  return (
    <div className="flex flex-col gap-5">
      <form onSubmit={submit} className="rounded-lg border bg-card p-4" aria-label="Backtest settings">
        <div className="grid grid-cols-2 gap-4 md:grid-cols-3 xl:grid-cols-6">
          <Field id="bt-strategy" label="Strategy">
            <div id="bt-strategy" className="flex h-8 items-center truncate rounded-md border bg-surface px-2.5 text-[13px]">
              {meta.data?.strategy.name ?? "20 / 50 SMA Crossover"}
            </div>
          </Field>
          <Field id="bt-capital" label="Initial capital (₹)">
            <input id="bt-capital" type="number" min={1} step={1000} value={f.capital} onChange={set("capital")} className={inputClass} />
          </Field>
          <Field id="bt-cost" label="Transaction cost (%)" hint="Per BUY and per SELL">
            <input id="bt-cost" type="number" min={0} max={99} step={0.01} value={f.costPct} onChange={set("costPct")} className={inputClass} />
          </Field>
          <Field id="bt-weight" label="Max position weight (%)">
            <input id="bt-weight" type="number" min={0.1} max={100} step={0.5} value={f.weightPct} onChange={set("weightPct")} className={inputClass} />
          </Field>
          <div className="col-span-2 space-y-1.5">
            <span id="bt-period" className="text-xs font-medium text-muted-foreground">Period</span>
            <ToggleGroup
              type="single"
              variant="outline"
              size="sm"
              spacing={0}
              value={String(f.years)}
              onValueChange={(v) => v && setForm({ ...f, years: Number(v) })}
              aria-labelledby="bt-period"
              className="w-full"
            >
              {PERIODS.map((y) => (
                <ToggleGroupItem
                  key={y}
                  value={String(y)}
                  aria-label={`${y} year${y > 1 ? "s" : ""}`}
                  className="num h-8 flex-1 text-xs data-[state=on]:bg-foreground data-[state=on]:text-background"
                >
                  {y}Y
                </ToggleGroupItem>
              ))}
            </ToggleGroup>
            <p className="text-[11px] text-muted-foreground">Ending on the latest stored trading day</p>
          </div>
        </div>
        <div className="mt-4 flex flex-col gap-3 border-t pt-4 sm:flex-row sm:items-center sm:justify-between">
          <p className={cn("text-xs", formError ? "text-loss" : "text-muted-foreground")} role={formError ? "alert" : undefined}>
            {formError ??
              "Signals fill at the next trading day's open. Long-only, whole shares, flat costs. Survivorship bias: today's NIFTY 100 only."}
          </p>
          <Button type="submit" disabled={busy} className="shrink-0">
            {busy ? <Loader2 className="size-3.5 animate-spin" aria-hidden /> : <Play className="size-3.5" aria-hidden />}
            {busy ? "Running…" : "Run backtest"}
          </Button>
        </div>
      </form>

      {!run ? (
        <div className="rounded-lg border border-dashed bg-card">
          <EmptyState
            title="No backtest run yet"
            description="Choose settings and run the existing Python backtester on the stored data. A full 10-year run takes a few seconds."
          />
        </div>
      ) : result.error ? (
        <ErrorState error={result.error} onRetry={() => void result.reload()} title="Backtest failed" />
      ) : result.loading || !result.data ? (
        <ResultSkeleton />
      ) : (
        <BacktestResults data={result.data} stale={result.reloading} />
      )}
    </div>
  );
}

function ResultSkeleton() {
  return (
    <div className="space-y-5" aria-busy="true" aria-label="Running backtest">
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">{[0, 1, 2, 3].map((i) => <Skeleton key={i} className="h-[84px] rounded-lg" />)}</div>
      <Skeleton className="h-80 rounded-lg" />
    </div>
  );
}

function Panel({ title, description, children }: { title: string; description?: string; children: React.ReactNode }) {
  return (
    <section className="min-w-0 rounded-lg border bg-card">
      <header className="border-b px-4 py-3">
        <h2 className="text-sm font-semibold">{title}</h2>
        {description && <p className="text-xs text-muted-foreground">{description}</p>}
      </header>
      <div className="p-4">{children}</div>
    </section>
  );
}

function BacktestResults({ data, stale }: { data: BacktestResponse; stale: boolean }) {
  const m = data.metrics;
  const [showAll, setShowAll] = useState(false);
  const trades = useMemo(() => [...data.trades].sort((a, b) => b.exit_date.localeCompare(a.exit_date)), [data.trades]);
  const shownTrades = showAll ? trades : trades.slice(0, TRADE_PAGE);

  return (
    <div className={cn("flex flex-col gap-5 transition-opacity", stale && "opacity-60")}>
      <p className="num text-xs text-muted-foreground">
        {formatDate(m.start_date)} – {formatDate(m.end_date)} · {formatNumber(m.trading_days)} trading days · {data.symbols} stocks · stored data{" "}
        {formatDate(data.data_start)} – {formatDate(data.data_end)}
      </p>
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <MetricCard label="Final value" value={formatPrice(m.final_equity, 0)} hint={`from ${formatPrice(m.initial_capital, 0)}`} />
        <MetricCard label="Total return" value={formatFraction(m.total_return)} tone={m.total_return >= 0 ? "gain" : "loss"} hint={m.cagr !== null ? `CAGR ${formatFraction(m.cagr)}` : "CAGR n/a (< 1 year)"} />
        <MetricCard label="Max drawdown" value={formatFraction(m.max_drawdown)} tone={m.max_drawdown < 0 ? "loss" : "default"} hint="Largest fall from an equity peak" />
        <MetricCard
          label="Completed trades"
          value={formatNumber(m.completed_trades)}
          hint={`Win rate ${formatFraction(m.win_rate, { signed: false, decimals: 1 })} · ${m.open_positions} open`}
        />
      </div>

      <Panel title="Portfolio value" description="Daily total equity (cash + positions at the close). Dashed line: initial capital.">
        <EquityChart data={data.equity_curve} initial={m.initial_capital} />
      </Panel>
      <Panel title="Drawdown" description="Percentage below the previous equity peak.">
        <DrawdownChart data={data.equity_curve} />
      </Panel>

      <div className="grid gap-5 xl:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
        <Panel title="Completed trades" description={`${formatNumber(trades.length)} round trips, most recent exit first. Net of transaction costs.`}>
          {trades.length === 0 ? (
            <EmptyState title="No completed trades" />
          ) : (
            <div className="-m-4">
              <div className="max-h-[480px] overflow-auto">
                <table className="w-full text-[13px]">
                  <thead className="sticky top-0 border-b bg-surface text-left text-xs text-muted-foreground">
                    <tr>
                      <th scope="col" className="h-8 px-3 font-medium">Stock</th>
                      <th scope="col" className="h-8 px-3 font-medium">Entry</th>
                      <th scope="col" className="h-8 px-3 font-medium">Exit</th>
                      <th scope="col" className="hidden h-8 px-3 text-right font-medium md:table-cell">Days</th>
                      <th scope="col" className="h-8 px-3 text-right font-medium">Net P&amp;L</th>
                      <th scope="col" className="h-8 px-3 text-right font-medium">Return</th>
                    </tr>
                  </thead>
                  <tbody>
                    {shownTrades.map((t) => (
                      <tr key={`${t.symbol}-${t.entry_date}`} className="border-b last:border-b-0">
                        <td className="px-3 py-1.5 font-medium">
                          <Link href={stockHref(t.symbol)} className="hover:underline">{displaySymbol(t.symbol)}</Link>
                        </td>
                        <td className="num px-3 py-1.5 text-muted-foreground">{formatDate(t.entry_date)}</td>
                        <td className="num px-3 py-1.5 text-muted-foreground">{formatDate(t.exit_date)}</td>
                        <td className="num hidden px-3 py-1.5 text-right text-muted-foreground md:table-cell">{t.holding_days}</td>
                        <td className={cn("num px-3 py-1.5 text-right", trendClass[trend(t.net_pnl)])}>{formatPrice(t.net_pnl, 0)}</td>
                        <td className={cn("num px-3 py-1.5 text-right", trendClass[trend(t.return_pct)])}>{formatFraction(t.return_pct, { decimals: 1 })}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              {trades.length > TRADE_PAGE && (
                <div className="border-t px-3 py-2 text-center">
                  <Button variant="ghost" size="sm" onClick={() => setShowAll((v) => !v)}>
                    {showAll ? `Show latest ${TRADE_PAGE}` : `Show all ${formatNumber(trades.length)} trades`}
                  </Button>
                </div>
              )}
            </div>
          )}
        </Panel>
        <Panel title="Open positions" description="Held on the last day, valued at the last close (not counted as completed trades).">
          {data.open_positions.length === 0 ? (
            <EmptyState title="No open positions" />
          ) : (
            <div className="-m-4 overflow-x-auto">
              <table className="w-full text-[13px]">
                <thead className="border-b bg-surface text-left text-xs text-muted-foreground">
                  <tr>
                    <th scope="col" className="h-8 px-3 font-medium">Stock</th>
                    <th scope="col" className="h-8 px-3 font-medium">Since</th>
                    <th scope="col" className="h-8 px-3 text-right font-medium">Value</th>
                    <th scope="col" className="h-8 px-3 text-right font-medium">Unrealized</th>
                  </tr>
                </thead>
                <tbody>
                  {data.open_positions.map((p) => (
                    <tr key={p.symbol} className="border-b last:border-b-0">
                      <td className="px-3 py-1.5 font-medium">
                        <Link href={stockHref(p.symbol)} className="hover:underline">{displaySymbol(p.symbol)}</Link>
                      </td>
                      <td className="num px-3 py-1.5 text-muted-foreground">{formatDate(p.entry_date)}</td>
                      <td className="num px-3 py-1.5 text-right">{formatPrice(p.market_value, 0)}</td>
                      <td className={cn("num px-3 py-1.5 text-right", trendClass[trend(p.unrealized_pnl)])}>{formatPrice(p.unrealized_pnl, 0)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Panel>
      </div>
      <p className="text-xs text-muted-foreground">
        Historical simulation only. Past results on split-adjusted, survivorship-biased data do not predict future returns.
      </p>
    </div>
  );
}
