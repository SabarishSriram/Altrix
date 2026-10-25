import { Info } from "lucide-react";
import { cn } from "cn";

import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";

export const TERMS = {
  EMA20: "20-day exponential moving average of the close: recent days count more, so it turns faster than a simple average. About one month of trading.",
  EMA50: "50-day exponential moving average of the close (about one quarter of trading). Slower than EMA20, so it shows the larger trend.",
  BUY: "Fresh crossover on this date: EMA20 was at or below EMA50 on the previous bar and is above it now.",
  SELL: "Fresh crossover on this date: EMA20 was at or above EMA50 on the previous bar and is below it now.",
  HOLD: "No new crossover on the latest date. EMA20 may already sit above or below EMA50 from an earlier crossover.",
  INSUFFICIENT_DATA: "Fewer than 50 daily bars are stored, so EMA50 and any signal are undefined.",
  CHANGE: "Change from the stock's previous stored daily close.",
  SIGNAL_DATE: "Date of the BUY or SELL crossover. Empty for HOLD.",
  DATA_AS_OF: "Latest completed trading day in the stored data. Signals use that day's close.",
  VOL_SPIKE: "Today's volume divided by the average volume of the last 20 trading days (including today). 2.0x = twice the usual.",
  CLV: "Close location value: where the close sits in the day's range. 1 = closed at the high (buyers in control), 0 = at the low.",
  POCKET_PIVOT: "Up day whose volume beats every down-day volume of the prior 10 trading days, closing at or above 95% of EMA50.",
  ACCUMULATION: "Institutional accumulation: up day with at least 2x average volume and a close in the upper half of the range (CLV >= 0.5).",
  ACTIVE_10D: "A pocket pivot or institutional accumulation happened on one of the last 10 trading days (including today).",
  TREND: "EMA20 above EMA50 = uptrend; at or below = downtrend. Needs 50 daily bars.",
  DELIV_SPIKE: "NSE deliverable quantity divided by its 20-day average. Flagged at 2x or more with at least 55% of traded shares delivered.",
} as const;

export type TermKey = keyof typeof TERMS;

/** A label with an accessible explanatory tooltip. */
export function Term({ term, children, className }: { term: TermKey; children: React.ReactNode; className?: string }) {
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <button
          type="button"
          className={cn(
            "inline-flex items-center gap-1 rounded-sm outline-none focus-visible:ring-2 focus-visible:ring-ring/50",
            className,
          )}
        >
          {children}
          <Info className="size-3 text-muted-foreground/70" aria-hidden />
          <span className="sr-only">: {TERMS[term]}</span>
        </button>
      </TooltipTrigger>
      <TooltipContent side="top" className="max-w-64 leading-relaxed">
        {TERMS[term]}
      </TooltipContent>
    </Tooltip>
  );
}
