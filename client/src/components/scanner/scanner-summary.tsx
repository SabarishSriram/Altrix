import { MetricCard } from "@/components/common/metric-card";
import { Term } from "@/components/common/term";
import { formatDate, formatRelative } from "@/lib/format";
import type { ScannerResponse } from "@/lib/types";

export function ScannerSummary({ data, loading }: { data?: ScannerResponse; loading?: boolean }) {
  const failed = data?.failed_symbols.length ?? 0;
  return (
    <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
      <MetricCard
        label="Stocks scanned"
        value={data ? `${data.scanned_count}` : ""}
        hint={data && `of ${data.universe_size} ${data.universe} constituents${failed ? ` · ${failed} unavailable` : ""}`}
        loading={loading}
      />
      <MetricCard
        label={<Term term="BUY">BUY signals</Term>}
        value={data?.buy_count ?? ""}
        tone={data && data.buy_count > 0 ? "gain" : "default"}
        hint="Fresh EMA20 ↑ EMA50 crossovers"
        loading={loading}
      />
      <MetricCard
        label={<Term term="SELL">SELL signals</Term>}
        value={data?.sell_count ?? ""}
        tone={data && data.sell_count > 0 ? "loss" : "default"}
        hint="Fresh EMA20 ↓ EMA50 crossovers"
        loading={loading}
      />
      <MetricCard
        label={<Term term="DATA_AS_OF">Data as of</Term>}
        value={data ? formatDate(data.data_as_of) : ""}
        hint={data && `Scanned ${formatRelative(data.scanned_at)}`}
        loading={loading}
      />
    </div>
  );
}
