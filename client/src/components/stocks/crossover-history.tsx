"use client";

import { useMemo } from "react";
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { cn } from "cn";

import { EmptyState } from "@/components/common/states";
import { CHART } from "@/lib/chart-theme";
import { formatDate, formatPrice } from "@/lib/format";
import type { HistoryPoint } from "@/lib/types";

const GAIN = CHART.gain;
const LOSS = CHART.loss;
const TICK = { ...CHART.axisTick, fontSize: 11 };

/** BUY/SELL crossovers per calendar year (counts of the strategy's own signals). */
export function CrossoversByYear({ crossovers }: { crossovers: HistoryPoint[] }) {
  const data = useMemo(() => {
    const years = new Map<string, { year: string; buy: number; sell: number }>();
    for (const c of crossovers) {
      const year = c.date.slice(0, 4);
      const row = years.get(year) ?? { year, buy: 0, sell: 0 };
      if (c.signal === "BUY") row.buy += 1;
      else row.sell += 1;
      years.set(year, row);
    }
    return [...years.values()].sort((a, b) => a.year.localeCompare(b.year));
  }, [crossovers]);

  if (data.length === 0) return <EmptyState title="No crossovers yet" description="The strategy has not signalled on this stock." />;

  return (
    <div className="h-48 w-full">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={data} margin={{ top: 4, right: 4, bottom: 0, left: -24 }} barGap={2}>
          <CartesianGrid vertical={false} stroke={CHART.grid} />
          <XAxis dataKey="year" tickLine={false} axisLine={false} tick={TICK} />
          <YAxis allowDecimals={false} tickLine={false} axisLine={false} tick={TICK} />
          <Tooltip cursor={{ fill: CHART.cursor }} contentStyle={CHART.tooltip} />
          <Bar dataKey="buy" name="BUY" fill={GAIN} radius={[2, 2, 0, 0]} maxBarSize={14} />
          <Bar dataKey="sell" name="SELL" fill={LOSS} radius={[2, 2, 0, 0]} maxBarSize={14} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

/** Every crossover, newest first. */
export function CrossoverTable({ crossovers, limit }: { crossovers: HistoryPoint[]; limit?: number }) {
  const rows = useMemo(() => [...crossovers].reverse().slice(0, limit), [crossovers, limit]);
  if (rows.length === 0) return <EmptyState title="No crossovers in the stored history" />;
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-[13px]">
        <thead className="border-b text-left text-xs text-muted-foreground">
          <tr>
            <th scope="col" className="h-8 px-3 font-medium">Date</th>
            <th scope="col" className="h-8 px-3 font-medium">Signal</th>
            <th scope="col" className="h-8 px-3 text-right font-medium">Close</th>
            <th scope="col" className="hidden h-8 px-3 text-right font-medium sm:table-cell">EMA20</th>
            <th scope="col" className="hidden h-8 px-3 text-right font-medium sm:table-cell">EMA50</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((c) => (
            <tr key={c.date} className="border-b last:border-b-0">
              <td className="num px-3 py-1.5">{formatDate(c.date)}</td>
              <td className={cn("px-3 py-1.5 text-xs font-semibold", c.signal === "BUY" ? "text-gain" : "text-loss")}>
                {c.signal === "BUY" ? "▲ BUY" : "▼ SELL"}
              </td>
              <td className="num px-3 py-1.5 text-right">{formatPrice(c.close)}</td>
              <td className="num hidden px-3 py-1.5 text-right text-muted-foreground sm:table-cell">{formatPrice(c.ema20)}</td>
              <td className="num hidden px-3 py-1.5 text-right text-muted-foreground sm:table-cell">{formatPrice(c.ema50)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
