"use client";

import { ErrorState } from "@/components/common/states";
import { useScanner } from "@/components/providers/scanner-provider";
import { Skeleton } from "@/components/ui/skeleton";
import { useResource } from "@/hooks/use-resource";
import { API_BASE_URL, api } from "@/lib/api";
import { formatDate, formatFraction, formatPrice, formatTimestamp } from "@/lib/format";

function Section({ title, description, children }: { title: string; description?: string; children: React.ReactNode }) {
  return (
    <section className="rounded-lg border bg-card">
      <header className="border-b px-4 py-3">
        <h2 className="text-sm font-semibold">{title}</h2>
        {description && <p className="text-xs text-muted-foreground">{description}</p>}
      </header>
      <dl className="divide-y">{children}</dl>
    </section>
  );
}

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="grid gap-1 px-4 py-2.5 sm:grid-cols-[220px_1fr] sm:gap-4">
      <dt className="text-xs text-muted-foreground sm:pt-0.5">{label}</dt>
      <dd className="text-[13px] break-words">{children}</dd>
    </div>
  );
}

const code = "rounded bg-muted px-1 py-0.5 font-mono text-xs";

/** Read-only view of the configuration that actually exists (env vars and strategy constants). */
export function SettingsView() {
  const meta = useResource("meta", api.meta);
  const { health } = useScanner();

  if (meta.error) return <ErrorState error={meta.error} onRetry={() => void meta.reload()} />;
  const m = meta.data;
  const h = health.data;

  return (
    <div className="flex max-w-4xl flex-col gap-5">
      <Section title="API connection" description="Set in client/.env.local and read at build/start time.">
        <Row label="NEXT_PUBLIC_API_BASE_URL"><code className={code}>{API_BASE_URL}</code></Row>
        <Row label="Status">{health.error ? <span className="text-loss">Unreachable</span> : h ? `${h.status === "ok" ? "Online" : "Degraded"} · API v${h.version}` : <Skeleton className="h-4 w-32" />}</Row>
        <Row label="API documentation">
          <a href={`${API_BASE_URL}/docs`} target="_blank" rel="noreferrer" className="underline underline-offset-2">
            {API_BASE_URL}/docs
          </a>
        </Row>
      </Section>

      <Section title="Market data" description="Stored locally; configured on the API with ALTRIX_DATA_DIR, ALTRIX_RAW_DIR and ALTRIX_OFFLINE.">
        <Row label="Source">{m ? m.data_source.provider : <Skeleton className="h-4 w-56" />}</Row>
        <Row label="Frequency">{m ? `${m.data_source.frequency}, ${m.data_source.real_time ? "real-time" : "not real-time"}` : <Skeleton className="h-4 w-32" />}</Row>
        <Row label="Universe">{m?.data_source.universe ?? <Skeleton className="h-4 w-24" />}</Row>
        <Row label="Stored symbols">{h ? h.stored_symbols : <Skeleton className="h-4 w-10" />}</Row>
        <Row label="Data as of (market date)">{h?.data_as_of ? formatDate(h.data_as_of) : "—"}</Row>
        <Row label="Files last changed">{h ? formatTimestamp(h.data_updated_at) : "—"}</Row>
        <Row label="Offline mode">
          {m ? (m.offline_mode ? "On — the constituent list is read only from the local snapshot" : "Off — the constituent list is fetched from NSE (local snapshot as fallback)") : <Skeleton className="h-4 w-40" />}
        </Row>
        <Row label="Notes">
          {m ? (
            <ul className="list-disc space-y-0.5 pl-4 text-muted-foreground">
              {m.data_source.notes.map((n) => <li key={n}>{n}</li>)}
            </ul>
          ) : (
            <Skeleton className="h-4 w-64" />
          )}
        </Row>
      </Section>

      <Section title="Strategy" description="Defined in server/src/strategy/baseline.py. Not configurable from the UI.">
        <Row label="Name">{m?.strategy.name ?? <Skeleton className="h-4 w-40" />}</Row>
        <Row label="Windows">{m ? `SMA${m.strategy.short_window} / SMA${m.strategy.long_window} of daily closes` : <Skeleton className="h-4 w-40" />}</Row>
        <Row label="BUY">{m?.strategy.buy_rule ?? "—"}</Row>
        <Row label="SELL">{m?.strategy.sell_rule ?? "—"}</Row>
      </Section>

      <Section title="Backtest defaults" description="From the backtester's configuration; change them per run on the Backtesting page.">
        <Row label="Initial capital">{m ? formatPrice(m.backtest_defaults.initial_capital, 0) : "—"}</Row>
        <Row label="Transaction cost">{m ? `${formatFraction(m.backtest_defaults.transaction_cost, { signed: false })} per BUY and per SELL` : "—"}</Row>
        <Row label="Max position weight">{m ? formatFraction(m.backtest_defaults.max_position_weight, { signed: false, decimals: 0 }) : "—"}</Row>
      </Section>

      {m && !m.downloads_enabled ? (
        <Section title="Updating data" description="This deployment is read-only (ALTRIX_DISABLE_DOWNLOAD=1).">
          <Row label="From the app">Disabled. Refresh → Rescan stored data still works.</Row>
          <Row label="New data">Arrives with each redeploy of the API (see Deployment in the repository README).</Row>
        </Section>
      ) : (
        <Section title="Updating data" description="Nothing downloads automatically.">
          <Row label="From the app">Refresh → Download new bars (incremental, end-of-day only).</Row>
          <Row label="From the command line"><code className={code}>python scripts/download_data.py</code> in <code className={code}>server/</code></Row>
        </Section>
      )}
    </div>
  );
}
