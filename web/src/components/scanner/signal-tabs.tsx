"use client";

import { cn } from "cn";

import type { ScannerResponse, Signal } from "@/lib/types";

export type SignalFilter = "ALL" | "BUY" | "SELL" | "HOLD";

export const SIGNAL_FILTERS: { key: SignalFilter; label: string }[] = [
  { key: "ALL", label: "All stocks" },
  { key: "BUY", label: "BUY signals" },
  { key: "SELL", label: "SELL signals" },
  { key: "HOLD", label: "HOLD / no new signal" },
];

/** "HOLD / no new signal" also covers stocks with too little history to signal. */
export function matchesFilter(signal: Signal, filter: SignalFilter): boolean {
  if (filter === "ALL") return true;
  if (filter === "HOLD") return signal === "HOLD" || signal === "INSUFFICIENT_DATA";
  return signal === filter;
}

export function filterCount(data: ScannerResponse | undefined, filter: SignalFilter): number | undefined {
  if (!data) return undefined;
  return {
    ALL: data.scanned_count,
    BUY: data.buy_count,
    SELL: data.sell_count,
    HOLD: data.hold_count + data.insufficient_count,
  }[filter];
}

export function SignalTabs({
  value,
  onChange,
  data,
}: {
  value: SignalFilter;
  onChange: (f: SignalFilter) => void;
  data?: ScannerResponse;
}) {
  const onKeyDown = (e: React.KeyboardEvent, i: number) => {
    const dir = e.key === "ArrowRight" ? 1 : e.key === "ArrowLeft" ? -1 : 0;
    if (!dir) return;
    e.preventDefault();
    const next = SIGNAL_FILTERS[(i + dir + SIGNAL_FILTERS.length) % SIGNAL_FILTERS.length];
    onChange(next.key);
    document.getElementById(`signal-tab-${next.key}`)?.focus();
  };

  return (
    <div role="tablist" aria-label="Filter by signal" className="-mb-px flex gap-1 overflow-x-auto">
      {SIGNAL_FILTERS.map((f, i) => {
        const active = f.key === value;
        const count = filterCount(data, f.key);
        return (
          <button
            key={f.key}
            id={`signal-tab-${f.key}`}
            role="tab"
            type="button"
            aria-selected={active}
            tabIndex={active ? 0 : -1}
            onClick={() => onChange(f.key)}
            onKeyDown={(e) => onKeyDown(e, i)}
            className={cn(
              "flex h-9 shrink-0 items-center gap-2 border-b-2 px-2.5 text-[13px] font-medium whitespace-nowrap outline-none transition-colors focus-visible:bg-muted",
              active ? "border-foreground text-foreground" : "border-transparent text-muted-foreground hover:text-foreground",
            )}
          >
            {f.label}
            <span
              className={cn(
                "num rounded-sm px-1.5 py-px text-[11px]",
                f.key === "BUY" && count ? "bg-gain-soft text-gain" : f.key === "SELL" && count ? "bg-loss-soft text-loss" : "bg-muted text-muted-foreground",
              )}
            >
              {count ?? "–"}
            </span>
          </button>
        );
      })}
    </div>
  );
}
