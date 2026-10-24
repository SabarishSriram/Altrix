"use client";

import { Area, AreaChart, CartesianGrid, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { formatDate, formatFraction, formatPrice } from "@/lib/format";
import type { EquityPoint } from "@/lib/types";

const AXIS = { fontSize: 10, fill: "#737373" };
const TOOLTIP = { fontSize: 12, borderRadius: 6, border: "1px solid #e5e5e5", boxShadow: "none" };
const compactInr = new Intl.NumberFormat("en-IN", { notation: "compact", maximumFractionDigits: 1 });

export function EquityChart({ data, initial }: { data: EquityPoint[]; initial: number }) {
  return (
    <div className="h-72 w-full">
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={data} margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
          <CartesianGrid vertical={false} stroke="#f0f0f0" />
          <XAxis dataKey="date" tickLine={false} axisLine={false} tick={AXIS} minTickGap={48} tickFormatter={(d: string) => formatDate(d, "MMM yy")} />
          <YAxis width={56} tickLine={false} axisLine={false} tick={AXIS} domain={["auto", "auto"]} tickFormatter={(v: number) => `₹${compactInr.format(v)}`} />
          <Tooltip
            contentStyle={TOOLTIP}
            labelFormatter={(d) => formatDate(String(d))}
            formatter={(v) => [formatPrice(Number(v), 0), "Portfolio value"]}
          />
          <ReferenceLine y={initial} stroke="#a3a3a3" strokeDasharray="3 3" />
          <Area type="monotone" dataKey="total_equity" stroke="#171717" strokeWidth={1.5} fill="#171717" fillOpacity={0.04} dot={false} isAnimationActive={false} />
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
          <CartesianGrid vertical={false} stroke="#f0f0f0" />
          <XAxis dataKey="date" tickLine={false} axisLine={false} tick={AXIS} minTickGap={48} tickFormatter={(d: string) => formatDate(d, "MMM yy")} />
          <YAxis width={56} tickLine={false} axisLine={false} tick={AXIS} tickFormatter={(v: number) => `${Math.round(v * 100)}%`} />
          <Tooltip contentStyle={TOOLTIP} labelFormatter={(d) => formatDate(String(d))} formatter={(v) => [formatFraction(Number(v)), "Drawdown"]} />
          <Area type="monotone" dataKey="drawdown" stroke="#c8372d" strokeWidth={1} fill="#c8372d" fillOpacity={0.1} dot={false} isAnimationActive={false} />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}
