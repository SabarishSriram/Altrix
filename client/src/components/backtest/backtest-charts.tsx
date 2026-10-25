"use client";

import { Area, AreaChart, CartesianGrid, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { CHART } from "@/lib/chart-theme";
import { formatDate, formatFraction, formatPrice } from "@/lib/format";
import type { EquityPoint } from "@/lib/types";

const AXIS = CHART.axisTick;
const TOOLTIP = CHART.tooltip;
const compactInr = new Intl.NumberFormat("en-IN", { notation: "compact", maximumFractionDigits: 1 });

export function EquityChart({ data, initial }: { data: EquityPoint[]; initial: number }) {
  return (
    <div className="h-72 w-full">
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={data} margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
          <CartesianGrid vertical={false} stroke={CHART.grid} />
          <XAxis dataKey="date" tickLine={false} axisLine={false} tick={AXIS} minTickGap={48} tickFormatter={(d: string) => formatDate(d, "MMM yy")} />
          <YAxis width={56} tickLine={false} axisLine={false} tick={AXIS} domain={["auto", "auto"]} tickFormatter={(v: number) => `₹${compactInr.format(v)}`} />
          <Tooltip
            contentStyle={TOOLTIP}
            labelFormatter={(d) => formatDate(String(d))}
            formatter={(v) => [formatPrice(Number(v), 0), "Portfolio value"]}
          />
          <ReferenceLine y={initial} stroke={CHART.reference} strokeDasharray="3 3" />
          <Area type="monotone" dataKey="total_equity" stroke={CHART.line} strokeWidth={1.5} fill={CHART.line} fillOpacity={0.06} dot={false} isAnimationActive={false} />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}

export function DrawdownChart({ data }: { data: EquityPoint[] }) {
  return (
    <div className="h-40 w-full">
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={data} margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
          <CartesianGrid vertical={false} stroke={CHART.grid} />
          <XAxis dataKey="date" tickLine={false} axisLine={false} tick={AXIS} minTickGap={48} tickFormatter={(d: string) => formatDate(d, "MMM yy")} />
          <YAxis width={56} tickLine={false} axisLine={false} tick={AXIS} tickFormatter={(v: number) => `${Math.round(v * 100)}%`} />
          <Tooltip contentStyle={TOOLTIP} labelFormatter={(d) => formatDate(String(d))} formatter={(v) => [formatFraction(Number(v)), "Drawdown"]} />
          <Area type="monotone" dataKey="drawdown" stroke={CHART.loss} strokeWidth={1} fill={CHART.loss} fillOpacity={0.12} dot={false} isAnimationActive={false} />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}
