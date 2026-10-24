import { ArrowDownRight, ArrowUpRight, Minus } from "lucide-react";
import { cn } from "cn";

import type { Signal } from "@/lib/types";

const STYLES: Record<Signal, { label: string; className: string; icon: typeof Minus | null }> = {
  BUY: { label: "BUY", className: "border-gain/25 bg-gain-soft text-gain", icon: ArrowUpRight },
  SELL: { label: "SELL", className: "border-loss/25 bg-loss-soft text-loss", icon: ArrowDownRight },
  HOLD: { label: "HOLD", className: "border-border bg-surface text-muted-foreground", icon: Minus },
  INSUFFICIENT_DATA: { label: "Insufficient data", className: "border-dashed border-border text-muted-foreground", icon: null },
};

export function SignalBadge({ signal, className }: { signal: Signal; className?: string }) {
  const s = STYLES[signal];
  const Icon = s.icon;
  return (
    <span
      className={cn(
        "inline-flex h-5 items-center gap-1 rounded-sm border px-1.5 text-[11px] font-semibold tracking-wide whitespace-nowrap",
        s.className,
        className,
      )}
    >
      {Icon && <Icon className="size-3" aria-hidden />}
      {s.label}
    </span>
  );
}
