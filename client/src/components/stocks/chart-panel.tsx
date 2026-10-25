"use client";

import dynamic from "next/dynamic";
import { useMemo, useState } from "react";
import { parseISO, subMonths, formatISO } from "date-fns";

import { Skeleton } from "@/components/ui/skeleton";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import type { HistoryPoint } from "@/lib/types";

const PriceChart = dynamic(() => import("@/components/stocks/price-chart").then((m) => m.PriceChart), {
  ssr: false,
  loading: () => <Skeleton className="h-full w-full rounded-md" />,
});

export const TIMEFRAMES = [
  { key: "1M", months: 1 },
  { key: "3M", months: 3 },
  { key: "6M", months: 6 },
  { key: "1Y", months: 12 },
  { key: "ALL", months: null },
] as const;
export type Timeframe = (typeof TIMEFRAMES)[number]["key"];

/** Points on or after `months` before the last bar (date selection only; values are untouched). */
export function sliceTimeframe(points: HistoryPoint[], tf: Timeframe): HistoryPoint[] {
  const months = TIMEFRAMES.find((t) => t.key === tf)?.months ?? null;
  const last = points.at(-1);
  if (months === null || !last) return points;
  const cutoff = formatISO(subMonths(parseISO(last.date), months), { representation: "date" });
  return points.filter((p) => p.date >= cutoff);
}

export function TimeframeToggle({
  value,
  onChange,
}: {
  value: Timeframe;
  onChange: (tf: Timeframe) => void;
}) {
  return (
    <ToggleGroup
      type="single"
      size="sm"
      variant="outline"
      spacing={0}
      value={value}
      onValueChange={(v) => v && onChange(v as Timeframe)}
      aria-label="Chart timeframe"
    >
      {TIMEFRAMES.map((t) => (
        <ToggleGroupItem key={t.key} value={t.key} className="num h-7 px-2.5 text-xs data-[state=on]:bg-foreground data-[state=on]:text-background">
          {t.key}
        </ToggleGroupItem>
      ))}
    </ToggleGroup>
  );
}

export function ChartPanel({
  points,
  height = 420,
  initial = "1Y",
  showVolume = true,
  toolbar,
}: {
  points: HistoryPoint[];
  height?: number;
  initial?: Timeframe;
  showVolume?: boolean;
  toolbar?: React.ReactNode;
}) {
  const [tf, setTf] = useState<Timeframe>(initial);
  const shown = useMemo(() => sliceTimeframe(points, tf), [points, tf]);
  const crossovers = shown.filter((p) => p.signal).length;

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <TimeframeToggle value={tf} onChange={setTf} />
        <div className="flex items-center gap-4 text-xs text-muted-foreground">
          <span className="inline-flex items-center gap-1.5">
            <span className="text-gain" aria-hidden>▲</span> BUY crossover
          </span>
          <span className="inline-flex items-center gap-1.5">
            <span className="text-loss" aria-hidden>▼</span> SELL crossover
          </span>
          <span className="num hidden sm:inline">
            {crossovers} in view · {shown.length.toLocaleString("en-IN")} bars
          </span>
          {toolbar}
        </div>
      </div>
      <div style={{ height }}>
        <PriceChart points={shown} height={height} showVolume={showVolume} />
      </div>
    </div>
  );
}
