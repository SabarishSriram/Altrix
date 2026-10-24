"use client";

import { cn } from "cn";

import { useScanner } from "@/components/providers/scanner-provider";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { formatDate, formatTimestamp } from "@/lib/format";

type Status = { label: string; tone: "ok" | "warn" | "down" | "pending"; detail: string };

function useStatus(): Status {
  const { health, scanner } = useScanner();
  if (health.error) return { label: "API offline", tone: "down", detail: health.error.message };
  if (!health.data) return { label: "Connecting…", tone: "pending", detail: "Checking the Altrix API." };
  if (!health.data.data_available) {
    return { label: "No market data", tone: "down", detail: "Run python scripts/download_data.py to download it." };
  }
  if (scanner.data?.is_stale) {
    return {
      label: "Data may be stale",
      tone: "warn",
      detail: `Stored data ends on ${formatDate(scanner.data.data_as_of)}. Use Refresh → Download new bars.`,
    };
  }
  const asOf = scanner.data?.data_as_of ?? health.data.data_as_of;
  return {
    label: "Data available",
    tone: "ok",
    detail: `${health.data.stored_symbols} symbols stored${asOf ? `, through ${formatDate(asOf)}` : ""}. Files last changed ${formatTimestamp(health.data.data_updated_at)}.`,
  };
}

const DOT = { ok: "bg-foreground", warn: "bg-amber-500", down: "bg-loss", pending: "bg-muted-foreground/40 animate-pulse" };

/** Market-data status: availability of stored end-of-day data. Never a "live" indicator. */
export function DataStatus({ compact }: { compact?: boolean }) {
  const s = useStatus();
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <button
          type="button"
          className="flex items-center gap-2 rounded-sm text-xs text-muted-foreground outline-none focus-visible:ring-2 focus-visible:ring-ring/50"
        >
          <span className={cn("size-1.5 shrink-0 rounded-full", DOT[s.tone])} aria-hidden />
          <span className={cn(compact && "sr-only sm:not-sr-only")}>{s.label}</span>
        </button>
      </TooltipTrigger>
      <TooltipContent side="top" className="max-w-72 leading-relaxed">
        {s.detail}
      </TooltipContent>
    </Tooltip>
  );
}
