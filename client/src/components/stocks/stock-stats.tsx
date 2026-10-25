import { cn } from "cn";

import { Term, type TermKey } from "@/components/common/term";
import { SignalBadge } from "@/components/stocks/signal-badge";
import { formatDate, formatPercent, formatPrice, trend, trendClass } from "@/lib/format";
import type { StockScan } from "@/lib/types";

function Stat({ label, term, children }: { label: string; term?: TermKey; children: React.ReactNode }) {
  return (
    <div className="min-w-0 space-y-1">
      <dt className="text-xs text-muted-foreground">{term ? <Term term={term}>{label}</Term> : label}</dt>
      <dd className="num truncate text-sm font-medium">{children}</dd>
    </div>
  );
}

/** Latest-bar facts for one stock, straight from the scan. */
export function StockStats({ stock, className }: { stock: StockScan; className?: string }) {
  return (
    <dl className={cn("grid grid-cols-2 gap-x-6 gap-y-4 sm:grid-cols-3", className)}>
      <Stat label={`Close · ${formatDate(stock.date, "dd MMM")}`}>{formatPrice(stock.close)}</Stat>
      <Stat label="Daily change" term="CHANGE">
        <span className={trendClass[trend(stock.daily_change_pct)]}>{formatPercent(stock.daily_change_pct)}</span>
      </Stat>
      <Stat label="Signal" term={stock.signal === "INSUFFICIENT_DATA" ? "INSUFFICIENT_DATA" : stock.signal}>
        <SignalBadge signal={stock.signal} />
      </Stat>
      <Stat label="EMA20" term="EMA20">{formatPrice(stock.ema20)}</Stat>
      <Stat label="EMA50" term="EMA50">{formatPrice(stock.ema50)}</Stat>
      <Stat label="Signal date" term="SIGNAL_DATE">{formatDate(stock.signal_date)}</Stat>
    </dl>
  );
}

/** "EMA20 is above EMA50 since a BUY crossover on …" — context for HOLD stocks. */
export function CrossoverContext({ stock }: { stock: StockScan }) {
  if (stock.signal === "INSUFFICIENT_DATA") return <p className="text-xs text-muted-foreground">{stock.note}</p>;
  return (
    <div className="space-y-1 text-xs text-muted-foreground">
      <p>
        {stock.last_crossover ? (
          <>
            Last crossover:{" "}
            <span className={cn("font-medium", stock.last_crossover === "BUY" ? "text-gain" : "text-loss")}>
              {stock.last_crossover}
            </span>{" "}
            on <span className="num">{formatDate(stock.last_crossover_date)}</span>
            {stock.signal === "HOLD" && " — no new crossover on the latest date."}
          </>
        ) : (
          "No crossover in the stored history."
        )}
      </p>
      {stock.note && <p>{stock.note}</p>}
    </div>
  );
}
