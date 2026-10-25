"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import { ArrowDown, ArrowUp, ArrowUpDown, ChevronRight, Search } from "lucide-react";
import { cn } from "cn";

import { MetricCard } from "@/components/common/metric-card";
import { EmptyState, ErrorState } from "@/components/common/states";
import { Term, type TermKey } from "@/components/common/term";
import { Skeleton } from "@/components/ui/skeleton";
import { useResource } from "@/hooks/use-resource";
import { api } from "@/lib/api";
import { displaySymbol, formatDate, formatPercent, formatPrice, formatRelative, trend, trendClass } from "@/lib/format";
import { stockHref } from "@/lib/routes";
import type { SmartMoneyResponse, SmartMoneyStock, Trend } from "@/lib/types";

type Filter = "ALL" | "PIVOT" | "ACCUMULATION" | "ACTIVE";
type SortKey =
  | "rank"
  | "symbol"
  | "close"
  | "return_1d_pct"
  | "vol_spike_ratio"
  | "clv"
  | "pocket_pivot"
  | "institutional_accumulation"
  | "smart_money_active_10d"
  | "trend"
  | "deliv_spike_ratio"
  | "deliv_per";
type Sort = { key: SortKey; dir: "asc" | "desc" };
type Row = SmartMoneyStock & { rank: number };

const FILTERS: { key: Filter; label: string; match: (s: SmartMoneyStock) => boolean; count: (d: SmartMoneyResponse) => number }[] = [
  { key: "ALL", label: "All stocks", match: () => true, count: (d) => d.stocks.length },
  { key: "PIVOT", label: "Pocket pivots", match: (s) => s.pocket_pivot, count: (d) => d.pocket_pivot_count },
  { key: "ACCUMULATION", label: "Accumulation", match: (s) => s.institutional_accumulation, count: (d) => d.accumulation_count },
  { key: "ACTIVE", label: "Active in 10 days", match: (s) => s.smart_money_active_10d, count: (d) => d.active_10d_count },
];

const TREND_RANK: Record<Trend, number> = { UPTREND: 0, DOWNTREND: 1, INSUFFICIENT_DATA: 2 };

function sortValue(r: Row, key: SortKey): number | string | null {
  if (key === "symbol") return r.symbol;
  if (key === "trend") return TREND_RANK[r.trend];
  const v = r[key];
  return typeof v === "boolean" ? Number(v) : v;
}

function sortRows(rows: Row[], sort: Sort): Row[] {
  const sign = sort.dir === "asc" ? 1 : -1;
  return [...rows].sort((a, b) => {
    const av = sortValue(a, sort.key);
    const bv = sortValue(b, sort.key);
    if (av === null || bv === null) return Number(av === null) - Number(bv === null) || a.rank - b.rank; // missing last
    const c = typeof av === "string" ? av.localeCompare(bv as string) : av - (bv as number);
    return c * sign || a.rank - b.rank;
  });
}

interface Column {
  key: SortKey;
  label: string;
  term?: TermKey;
  align?: "right";
  className?: string;
}

const BASE_COLUMNS: Column[] = [
  { key: "rank", label: "#", align: "right" },
  { key: "symbol", label: "Symbol" },
  { key: "close", label: "Close", align: "right" },
  { key: "return_1d_pct", label: "1D", term: "CHANGE", align: "right" },
  { key: "vol_spike_ratio", label: "Volume spike", term: "VOL_SPIKE", align: "right" },
  { key: "clv", label: "CLV", term: "CLV", align: "right", className: "hidden xl:table-cell" },
  { key: "pocket_pivot", label: "Pocket pivot", term: "POCKET_PIVOT" },
  { key: "institutional_accumulation", label: "Accumulation", term: "ACCUMULATION", className: "hidden lg:table-cell" },
  { key: "smart_money_active_10d", label: "10D active", term: "ACTIVE_10D", className: "hidden lg:table-cell" },
  { key: "trend", label: "EMA 20/50", term: "TREND" },
];
const DELIVERY_COLUMNS: Column[] = [
  { key: "deliv_spike_ratio", label: "Delivery spike", term: "DELIV_SPIKE", align: "right" },
  { key: "deliv_per", label: "Delivered", align: "right", className: "hidden xl:table-cell" },
];

const ratio = (v: number | null) => (v === null ? "—" : `${v.toFixed(2)}×`);

function YesNo({ value, strong }: { value: boolean; strong?: boolean }) {
  return value ? (
    <span className={cn("inline-flex items-center gap-1.5 text-[13px] font-medium", strong ? "text-gain" : "text-foreground")}>
      <span className="size-1.5 rounded-full bg-gain" aria-hidden />
      Yes
    </span>
  ) : (
    <span className="text-[13px] text-muted-foreground">No</span>
  );
}

function TrendBadge({ value }: { value: Trend }) {
  const label = value === "UPTREND" ? "EMA20 > EMA50" : value === "DOWNTREND" ? "EMA20 ≤ EMA50" : "Not enough data";
  return (
    <span
      className={cn(
        "num inline-flex rounded-sm px-1.5 py-px text-[11px] font-medium whitespace-nowrap",
        value === "UPTREND" ? "bg-gain-soft text-gain" : value === "DOWNTREND" ? "bg-loss-soft text-loss" : "bg-muted text-muted-foreground",
      )}
    >
      {label}
    </span>
  );
}

function SortHeader({ col, sort, onSort }: { col: Column; sort: Sort; onSort: (k: SortKey) => void }) {
  const active = sort.key === col.key;
  const Icon = !active ? ArrowUpDown : sort.dir === "asc" ? ArrowUp : ArrowDown;
  return (
    <th
      scope="col"
      aria-sort={active ? (sort.dir === "asc" ? "ascending" : "descending") : "none"}
      className={cn("h-9 px-3 font-medium whitespace-nowrap", col.align === "right" && "text-right", col.className)}
    >
      <span className={cn("inline-flex items-center gap-1", col.align === "right" && "flex-row-reverse")}>
        <button
          type="button"
          onClick={() => onSort(col.key)}
          className={cn(
            "inline-flex items-center gap-1 rounded-sm outline-none hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring/50",
            col.align === "right" && "flex-row-reverse",
            active && "text-foreground",
          )}
        >
          {col.label}
          <Icon className={cn("size-3", !active && "opacity-40")} aria-hidden />
          <span className="sr-only">, sort</span>
        </button>
        {col.term && <Term term={col.term} className="[&>svg]:size-3"><span className="sr-only">{col.label}</span></Term>}
      </span>
    </th>
  );
}

export function SmartMoneyView() {
  const res = useResource("smart-money", api.smartMoney);
  const [filter, setFilter] = useState<Filter>("ALL");
  const [query, setQuery] = useState("");
  const [sort, setSort] = useState<Sort>({ key: "rank", dir: "asc" });

  const data = res.data;
  const withDelivery = data?.deliverables_available ?? false;
  const columns = withDelivery ? [...BASE_COLUMNS, ...DELIVERY_COLUMNS] : BASE_COLUMNS;

  const rows = useMemo(() => {
    if (!data) return [];
    const q = query.trim().toUpperCase();
    const match = FILTERS.find((f) => f.key === filter)!.match;
    const ranked: Row[] = data.stocks.map((s, i) => ({ ...s, rank: i + 1 })); // API order = volume spike rank
    return sortRows(
      ranked.filter((s) => match(s) && (!q || s.symbol.includes(q) || (s.name ?? "").toUpperCase().includes(q))),
      sort,
    );
  }, [data, filter, query, sort]);

  const onSort = (key: SortKey) =>
    setSort((s) =>
      s.key === key ? { key, dir: s.dir === "asc" ? "desc" : "asc" } : { key, dir: key === "rank" || key === "symbol" || key === "trend" ? "asc" : "desc" },
    );

  if (res.error && !data) return <ErrorState error={res.error} onRetry={() => void res.reload()} title="Smart Money scan unavailable" />;

  return (
    <div className="flex flex-col gap-5">
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <MetricCard
          label={<Term term="POCKET_PIVOT">Pocket pivots</Term>}
          value={data?.pocket_pivot_count ?? ""}
          tone={data && data.pocket_pivot_count > 0 ? "gain" : "default"}
          hint="Up on volume above recent down days"
          loading={res.loading}
        />
        <MetricCard
          label={<Term term="ACCUMULATION">Accumulation days</Term>}
          value={data?.accumulation_count ?? ""}
          tone={data && data.accumulation_count > 0 ? "gain" : "default"}
          hint="Up, ≥ 2× volume, close in upper half"
          loading={res.loading}
        />
        <MetricCard
          label={<Term term="ACTIVE_10D">Active in last 10 days</Term>}
          value={data ? `${data.active_10d_count}` : ""}
          hint={data && `of ${data.stocks.length} ${data.universe} stocks`}
          loading={res.loading}
        />
        <MetricCard
          label={<Term term="DATA_AS_OF">Data as of</Term>}
          value={data ? formatDate(data.data_as_of) : ""}
          hint={
            data &&
            (data.deliverables_available
              ? `NSE delivery data to ${formatDate(data.deliverables_as_of)}`
              : `Scanned ${formatRelative(data.scanned_at)} · no NSE delivery data`)
          }
          loading={res.loading}
        />
      </div>

      <section aria-label="Smart Money scanner" className="min-w-0 overflow-hidden rounded-lg border bg-card">
        <div className="flex flex-col gap-3 border-b px-3 pt-2 sm:flex-row sm:items-end sm:justify-between">
          <div role="tablist" aria-label="Filter by footprint" className="-mb-px flex gap-1 overflow-x-auto">
            {FILTERS.map((f) => {
              const active = f.key === filter;
              return (
                <button
                  key={f.key}
                  role="tab"
                  type="button"
                  aria-selected={active}
                  onClick={() => setFilter(f.key)}
                  className={cn(
                    "flex h-9 shrink-0 items-center gap-2 border-b-2 px-2.5 text-[13px] font-medium whitespace-nowrap outline-none transition-colors focus-visible:bg-muted",
                    active ? "border-foreground text-foreground" : "border-transparent text-muted-foreground hover:text-foreground",
                  )}
                >
                  {f.label}
                  <span className="num rounded-sm bg-muted px-1.5 py-px text-[11px] text-muted-foreground">{data ? f.count(data) : "–"}</span>
                </button>
              );
            })}
          </div>
          <div className="flex items-center gap-3 pb-2">
            <p className="num text-xs whitespace-nowrap text-muted-foreground" aria-live="polite">
              {data ? `${rows.length} of ${data.stocks.length} stocks` : "Loading…"}
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

        {res.loading ? (
          <TableSkeleton />
        ) : rows.length === 0 ? (
          <EmptyState title="No stocks in this view" description={query.trim() ? `Nothing matches “${query.trim()}”.` : "No stock shows this footprint on the latest date."} />
        ) : (
          <>
            <div className="hidden max-h-[640px] overflow-auto md:block">
              <table className="w-full text-[13px]">
                <thead className="sticky top-0 z-[1] border-b bg-surface text-left text-xs text-muted-foreground">
                  <tr>
                    {columns.map((c) => (
                      <SortHeader key={c.key} col={c} sort={sort} onSort={onSort} />
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {rows.map((s) => (
                    <tr key={s.symbol} className="border-b last:border-b-0 hover:bg-muted/50">
                      <td className="num px-3 py-2 text-right text-muted-foreground">{s.rank}</td>
                      <td className="max-w-56 px-3 py-2">
                        <Link href={stockHref(s.symbol)} className="font-medium hover:underline">{displaySymbol(s.symbol)}</Link>
                        <div className="truncate text-xs text-muted-foreground" title={s.note ?? undefined}>{s.note ?? s.name ?? "—"}</div>
                      </td>
                      <td className="num px-3 py-2 text-right font-medium">{formatPrice(s.close)}</td>
                      <td className={cn("num px-3 py-2 text-right", trendClass[trend(s.return_1d_pct)])}>{formatPercent(s.return_1d_pct)}</td>
                      <td className={cn("num px-3 py-2 text-right font-medium", s.vol_spike_ratio !== null && s.vol_spike_ratio >= 2 && "text-gain")}>
                        {ratio(s.vol_spike_ratio)}
                      </td>
                      <td className="num hidden px-3 py-2 text-right text-muted-foreground xl:table-cell">{s.clv === null ? "—" : s.clv.toFixed(2)}</td>
                      <td className="px-3 py-2"><YesNo value={s.pocket_pivot} strong /></td>
                      <td className="hidden px-3 py-2 lg:table-cell"><YesNo value={s.institutional_accumulation} strong /></td>
                      <td className="hidden px-3 py-2 lg:table-cell"><YesNo value={s.smart_money_active_10d} /></td>
                      <td className="px-3 py-2"><TrendBadge value={s.trend} /></td>
                      {withDelivery && (
                        <>
                          <td className={cn("num px-3 py-2 text-right", s.delivery_spike && "font-medium text-gain")}>{ratio(s.deliv_spike_ratio)}</td>
                          <td className="num hidden px-3 py-2 text-right text-muted-foreground xl:table-cell">{formatPercent(s.deliv_per, { signed: false, decimals: 1 })}</td>
                        </>
                      )}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <ul className="divide-y md:hidden">
              {rows.map((s) => (
                <li key={s.symbol}>
                  <Link href={stockHref(s.symbol)} className="flex items-center gap-3 px-3 py-2.5 outline-none focus-visible:bg-muted active:bg-muted">
                    <span className="num w-6 text-right text-xs text-muted-foreground">{s.rank}</span>
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2">
                        <span className="text-[13px] font-medium">{displaySymbol(s.symbol)}</span>
                        {s.pocket_pivot && <span className="rounded-sm bg-gain-soft px-1.5 py-px text-[11px] font-medium text-gain">Pivot</span>}
                        {s.institutional_accumulation && <span className="rounded-sm bg-gain-soft px-1.5 py-px text-[11px] font-medium text-gain">Accum.</span>}
                      </div>
                      <div className="truncate text-xs text-muted-foreground">{s.note ?? s.name ?? "—"}</div>
                    </div>
                    <div className="text-right">
                      <div className="num text-[13px] font-medium">{ratio(s.vol_spike_ratio)}</div>
                      <div className={cn("num text-xs", trendClass[trend(s.return_1d_pct)])}>{formatPercent(s.return_1d_pct)}</div>
                    </div>
                    <ChevronRight className="size-4 text-muted-foreground/60" aria-hidden />
                  </Link>
                </li>
              ))}
            </ul>
          </>
        )}
      </section>

      <p className="text-xs leading-relaxed text-muted-foreground">
        Ranked by volume spike on the latest stored trading day. Every value is computed in Python
        (server/src/strategy/smart_money.py) from end-of-day OHLCV
        {withDelivery ? " and NSE deliverable data" : "; NSE delivery columns appear once scripts/download_deliverables.py has run"}. A
        footprint dated D uses D&apos;s close. Research only, not investment advice.
      </p>
    </div>
  );
}

function TableSkeleton() {
  return (
    <div className="divide-y" aria-busy="true" aria-label="Loading Smart Money scan">
      {Array.from({ length: 10 }, (_, i) => (
        <div key={i} className="flex items-center gap-4 px-3 py-3">
          <Skeleton className="h-3.5 w-6" />
          <div className="flex-1 space-y-1.5">
            <Skeleton className="h-3.5 w-24" />
            <Skeleton className="h-3 w-40" />
          </div>
          <Skeleton className="h-3.5 w-20" />
          <Skeleton className="h-3.5 w-14" />
          <Skeleton className="hidden h-3.5 w-16 sm:block" />
          <Skeleton className="hidden h-5 w-24 lg:block" />
        </div>
      ))}
    </div>
  );
}
