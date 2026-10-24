"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import { ArrowDown, ArrowUp, ArrowUpDown, ChevronRight, LineChart } from "lucide-react";
import { cn } from "cn";

import { Term, type TermKey } from "@/components/common/term";
import { SignalBadge } from "@/components/stocks/signal-badge";
import { Skeleton } from "@/components/ui/skeleton";
import { displaySymbol, formatDate, formatPercent, formatPrice, trend, trendClass } from "@/lib/format";
import { stockHref } from "@/lib/routes";
import type { Signal, StockScan } from "@/lib/types";

type SortKey = "symbol" | "close" | "daily_change_pct" | "sma20" | "sma50" | "signal" | "signal_date";
type Sort = { key: SortKey; dir: "asc" | "desc" };

const SIGNAL_RANK: Record<Signal, number> = { BUY: 0, SELL: 1, HOLD: 2, INSUFFICIENT_DATA: 3 };

function compare(a: StockScan, b: StockScan, key: SortKey): number | null {
  if (key === "symbol") return a.symbol.localeCompare(b.symbol);
  if (key === "signal") return SIGNAL_RANK[a.signal] - SIGNAL_RANK[b.signal] || a.symbol.localeCompare(b.symbol);
  const av = a[key];
  const bv = b[key];
  if (av === null || bv === null) return null; // handled by caller: missing values always last
  return typeof av === "string" ? av.localeCompare(bv as string) : av - (bv as number);
}

export function sortStocks(stocks: StockScan[], sort: Sort): StockScan[] {
  const sign = sort.dir === "asc" ? 1 : -1;
  return [...stocks].sort((a, b) => {
    const c = compare(a, b, sort.key);
    if (c !== null) return c * sign || a.symbol.localeCompare(b.symbol);
    const aMissing = a[sort.key] === null;
    const bMissing = b[sort.key] === null;
    return Number(aMissing) - Number(bMissing) || a.symbol.localeCompare(b.symbol);
  });
}

const COLUMNS: { key: SortKey; label: string; term?: TermKey; align?: "right"; className?: string }[] = [
  { key: "symbol", label: "Symbol" },
  { key: "close", label: "Close", align: "right" },
  { key: "daily_change_pct", label: "Change", term: "CHANGE", align: "right" },
  { key: "sma20", label: "SMA20", term: "SMA20", align: "right", className: "hidden lg:table-cell" },
  { key: "sma50", label: "SMA50", term: "SMA50", align: "right", className: "hidden lg:table-cell" },
  { key: "signal", label: "Signal" },
  { key: "signal_date", label: "Signal date", term: "SIGNAL_DATE", className: "hidden sm:table-cell" },
];

function SortHeader({
  col,
  sort,
  onSort,
}: {
  col: (typeof COLUMNS)[number];
  sort: Sort;
  onSort: (key: SortKey) => void;
}) {
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

export function StocksTable({
  stocks,
  loading,
  selected,
  onSelect,
  empty,
}: {
  stocks: StockScan[];
  loading?: boolean;
  selected?: string | null;
  onSelect: (symbol: string) => void;
  empty?: React.ReactNode;
}) {
  const [sort, setSort] = useState<Sort>({ key: "signal", dir: "asc" });
  const rows = useMemo(() => sortStocks(stocks, sort), [stocks, sort]);

  const onSort = (key: SortKey) =>
    setSort((s) =>
      s.key === key
        ? { key, dir: s.dir === "asc" ? "desc" : "asc" }
        : { key, dir: key === "symbol" || key === "signal" ? "asc" : "desc" },
    );

  if (loading) return <TableSkeleton />;

  return (
    <>
      {/* Tablet and desktop: dense sortable table */}
      <div className="hidden overflow-x-auto md:block">
        <table className="w-full text-[13px]">
          <thead className="sticky top-0 z-[1] border-b bg-surface text-left text-xs text-muted-foreground">
            <tr>
              {COLUMNS.map((c) => (
                <SortHeader key={c.key} col={c} sort={sort} onSort={onSort} />
              ))}
              <th scope="col" className="h-9 w-10 px-3">
                <span className="sr-only">Open analysis</span>
              </th>
            </tr>
          </thead>
          <tbody>
            {rows.map((s) => {
              const isSelected = s.symbol === selected;
              const t = trend(s.daily_change_pct);
              return (
                <tr
                  key={s.symbol}
                  tabIndex={0}
                  aria-selected={isSelected}
                  onClick={() => onSelect(s.symbol)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" || e.key === " ") {
                      e.preventDefault();
                      onSelect(s.symbol);
                    }
                  }}
                  className={cn(
                    "group cursor-pointer border-b outline-none transition-colors last:border-b-0 hover:bg-muted/50 focus-visible:bg-muted/60",
                    isSelected && "bg-muted/70 shadow-[inset_2px_0_0_var(--foreground)] hover:bg-muted/70",
                  )}
                >
                  <td className="max-w-56 px-3 py-2">
                    <div className="font-medium">{displaySymbol(s.symbol)}</div>
                    <div className="truncate text-xs text-muted-foreground">{s.name ?? "—"}</div>
                  </td>
                  <td className="num px-3 py-2 text-right font-medium">{formatPrice(s.close)}</td>
                  <td className={cn("num px-3 py-2 text-right", trendClass[t])}>{formatPercent(s.daily_change_pct)}</td>
                  <td className="num hidden px-3 py-2 text-right text-muted-foreground lg:table-cell">{formatPrice(s.sma20)}</td>
                  <td className="num hidden px-3 py-2 text-right text-muted-foreground lg:table-cell">{formatPrice(s.sma50)}</td>
                  <td className="px-3 py-2">
                    <SignalBadge signal={s.signal} />
                  </td>
                  <td className="num hidden px-3 py-2 text-muted-foreground sm:table-cell">{formatDate(s.signal_date)}</td>
                  <td className="px-2 py-2 text-right">
                    <Link
                      href={stockHref(s.symbol)}
                      onClick={(e) => e.stopPropagation()}
                      aria-label={`Open ${displaySymbol(s.symbol)} analysis`}
                      className="inline-flex size-7 items-center justify-center rounded-md text-muted-foreground outline-none hover:bg-background hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring/50"
                    >
                      <LineChart className="size-3.5" aria-hidden />
                    </Link>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
        {rows.length === 0 && empty}
      </div>

      {/* Mobile: compact list, tap opens the analysis page */}
      <ul className="divide-y md:hidden">
        {rows.map((s) => {
          const t = trend(s.daily_change_pct);
          return (
            <li key={s.symbol}>
              <Link href={stockHref(s.symbol)} className="flex items-center gap-3 px-3 py-2.5 outline-none focus-visible:bg-muted active:bg-muted">
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <span className="text-[13px] font-medium">{displaySymbol(s.symbol)}</span>
                    {s.signal !== "HOLD" && <SignalBadge signal={s.signal} />}
                  </div>
                  <div className="truncate text-xs text-muted-foreground">{s.name ?? "—"}</div>
                </div>
                <div className="text-right">
                  <div className="num text-[13px] font-medium">{formatPrice(s.close)}</div>
                  <div className={cn("num text-xs", trendClass[t])}>{formatPercent(s.daily_change_pct)}</div>
                </div>
                <ChevronRight className="size-4 text-muted-foreground/60" aria-hidden />
              </Link>
            </li>
          );
        })}
        {rows.length === 0 && <li>{empty}</li>}
      </ul>
    </>
  );
}

function TableSkeleton() {
  return (
    <div className="divide-y" aria-busy="true" aria-label="Loading stocks">
      {Array.from({ length: 10 }, (_, i) => (
        <div key={i} className="flex items-center gap-4 px-3 py-3">
          <div className="flex-1 space-y-1.5">
            <Skeleton className="h-3.5 w-24" />
            <Skeleton className="h-3 w-40" />
          </div>
          <Skeleton className="h-3.5 w-20" />
          <Skeleton className="hidden h-3.5 w-14 sm:block" />
          <Skeleton className="hidden h-3.5 w-20 lg:block" />
          <Skeleton className="hidden h-3.5 w-20 lg:block" />
          <Skeleton className="h-5 w-12" />
        </div>
      ))}
    </div>
  );
}
