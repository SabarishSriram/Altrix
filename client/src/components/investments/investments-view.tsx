"use client";

import Link from "next/link";
import { useMemo, useRef, useState, useSyncExternalStore } from "react";
import { Cloud, Download, LogOut, Mail, Plus, RotateCcw, Upload } from "lucide-react";
import { toast } from "sonner";
import { cn } from "cn";

import { MetricCard } from "@/components/common/metric-card";
import { EmptyState } from "@/components/common/states";
import { useScanner } from "@/components/providers/scanner-provider";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { useHistory } from "@/hooks/use-history";
import { usePaperJournal, type PaperJournal } from "@/hooks/use-paper-journal";
import { useResource } from "@/hooks/use-resource";
import { api } from "@/lib/api";
import { displaySymbol, formatDate, formatFraction, formatNumber, formatPrice, trend, trendClass } from "@/lib/format";
import {
  SOURCE_LABEL,
  buyCost,
  emptyJournal,
  exportJournal,
  newTradeId,
  parseJournal,
  summarize,
  type Journal,
  type TradeSource,
} from "@/lib/paper-journal";
import { stockHref } from "@/lib/routes";
import type { SmartMoneyStock, StockScan } from "@/lib/types";

const SIZE_WEIGHT = 0.1; // "size like the backtest": 10% of the paper portfolio
const inputClass =
  "num h-8 w-full rounded-md border bg-background px-2.5 text-[13px] outline-none focus-visible:border-ring focus-visible:ring-2 focus-visible:ring-ring/30";
const localDate = (d: Date) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
const today = () => localDate(new Date());
const noSubscribe = () => () => {};
/** Today's date in the browser; "" while prerendering, so the build date never reaches the page. */
const useToday = () => useSyncExternalStore(noSubscribe, today, () => "");

interface Draft {
  symbol: string;
  quantity: string;
  entryDate: string;
  entryPrice: string;
  source: TradeSource;
  note: string;
}

const blankDraft = (): Draft => ({ symbol: "", quantity: "", entryDate: "", entryPrice: "", source: "manual", note: "" });

function Section({ title, description, actions, children }: { title: string; description?: React.ReactNode; actions?: React.ReactNode; children: React.ReactNode }) {
  return (
    <section className="min-w-0 rounded-lg border bg-card">
      <header className="flex flex-wrap items-start justify-between gap-2 border-b px-4 py-3">
        <div>
          <h2 className="text-sm font-semibold">{title}</h2>
          {description && <p className="text-xs text-muted-foreground">{description}</p>}
        </div>
        {actions}
      </header>
      {children}
    </section>
  );
}

function Field({ id, label, children, hint }: { id: string; label: string; children: React.ReactNode; hint?: React.ReactNode }) {
  return (
    <div className="space-y-1.5">
      <Label htmlFor={id} className="text-xs font-medium text-muted-foreground">{label}</Label>
      {children}
      {hint && <div className="text-[11px] text-muted-foreground">{hint}</div>}
    </div>
  );
}

function AltrixStatus({ stock, sm }: { stock?: StockScan; sm?: SmartMoneyStock }) {
  if (!stock) return <span className="text-xs text-muted-foreground">No current data</span>;
  if (stock.signal === "SELL")
    return <span className="text-xs font-medium text-loss">EMA SELL today: the strategy exits at the next open</span>;
  const up = stock.ema20 !== null && stock.ema50 !== null && stock.ema20 > stock.ema50;
  return (
    <span className="flex flex-wrap items-center gap-1.5 text-xs">
      <span className={up ? "text-gain" : "text-muted-foreground"}>{up ? "Uptrend: hold" : "Below EMA50 trend"}</span>
      {sm?.smart_money_active_10d && <span className="rounded-sm bg-gain-soft px-1.5 py-px text-[11px] font-medium text-gain">Smart Money active</span>}
    </span>
  );
}

function SyncPanel({ pj }: { pj: PaperJournal }) {
  const [email, setEmail] = useState("");
  const [sentTo, setSentTo] = useState<string | null>(null);
  const [code, setCode] = useState("");
  const [busy, setBusy] = useState(false);

  if (!pj.cloudConfigured) return null;
  if (!pj.authReady) return <Skeleton className="h-[58px] rounded-lg" />;

  const run = async (fn: () => Promise<unknown>) => {
    setBusy(true);
    try {
      await fn();
    } finally {
      setBusy(false);
    }
  };

  if (pj.email) {
    return (
      <div className="flex flex-col gap-3 rounded-lg border bg-card px-4 py-3">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <p className="flex items-center gap-2 text-[13px]">
            <Cloud className="size-4 text-gain" aria-hidden />
            <span>
              Synced to your account <span className="font-medium">{pj.email}</span>: open Altrix on any device and sign in to see it.
            </span>
          </p>
          <Button size="sm" variant="ghost" onClick={() => void pj.signOut()}>
            <LogOut className="size-3.5" aria-hidden />
            Sign out
          </Button>
        </div>
        {pj.localTrades > 0 && pj.journal && (
          <div className="flex flex-col gap-2 rounded-md border border-dashed bg-surface px-3 py-2.5 sm:flex-row sm:items-center sm:justify-between">
            <p className="text-xs">
              This browser still has <span className="font-medium">{pj.localTrades} paper trade{pj.localTrades === 1 ? "" : "s"}</span> saved
              locally from before you signed in.
            </p>
            <Button
              size="sm"
              disabled={busy}
              onClick={() =>
                void run(async () => {
                  if (await pj.migrateLocal()) toast.success("Moved to your account", { description: "The browser copy was cleared after the upload was confirmed." });
                })
              }
            >
              <Upload className="size-3.5" aria-hidden />
              Move them to my account
            </Button>
          </div>
        )}
      </div>
    );
  }

  return (
    <div className="rounded-lg border bg-card px-4 py-3">
      {sentTo === null ? (
        <form
          className="flex flex-col gap-2 sm:flex-row sm:items-center"
          onSubmit={(e) => {
            e.preventDefault();
            const address = email.trim();
            if (!address) return;
            void run(async () => {
              if (await pj.sendLink(address)) setSentTo(address);
            });
          }}
        >
          <p className="flex flex-1 items-center gap-2 text-[13px]">
            <Cloud className="size-4 text-muted-foreground" aria-hidden />
            Sign in to keep this journal in your account and use it on your phone and laptop.
          </p>
          <input
            type="email"
            required
            autoComplete="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="you@example.com"
            aria-label="Email address"
            className={cn(inputClass, "font-sans sm:w-60")}
          />
          <Button type="submit" size="sm" disabled={busy}>
            <Mail className="size-3.5" aria-hidden />
            Email me a sign-in link
          </Button>
        </form>
      ) : (
        <form
          className="flex flex-col gap-2 sm:flex-row sm:items-center"
          onSubmit={(e) => {
            e.preventDefault();
            void run(() => pj.verifyCode(sentTo, code.trim()));
          }}
        >
          <p className="flex-1 text-[13px]">
            Sent to <span className="font-medium">{sentTo}</span>. Tap the link in the email, or type the code from it here.
          </p>
          <input
            inputMode="numeric"
            autoComplete="one-time-code"
            pattern="[0-9]{6,10}"
            value={code}
            onChange={(e) => setCode(e.target.value)}
            placeholder="Code"
            aria-label="Sign-in code"
            className={cn(inputClass, "sm:w-32")}
          />
          <Button type="submit" size="sm" disabled={busy || code.trim().length < 6}>Verify</Button>
          <Button type="button" size="sm" variant="ghost" onClick={() => setSentTo(null)}>Use another email</Button>
        </form>
      )}
    </div>
  );
}

export function InvestmentsView() {
  const pj = usePaperJournal();
  const journal = useMemo(() => pj.journal ?? emptyJournal(), [pj.journal]);
  const cloud = pj.mode === "cloud";
  const { scanner } = useScanner();
  const smartMoney = useResource("smart-money", api.smartMoney);
  const [draft, setDraft] = useState<Draft>(blankDraft);
  const [formError, setFormError] = useState<string | null>(null);
  const [closing, setClosing] = useState<{ id: string; date: string; price: string } | null>(null);
  const [settings, setSettings] = useState<{ cash: string; costPct: string } | null>(null);
  const fileInput = useRef<HTMLInputElement>(null);
  const todayStr = useToday();

  const stocks = useMemo(() => scanner.data?.stocks ?? [], [scanner.data]);
  const bySymbol = useMemo(() => new Map(stocks.map((s) => [s.symbol, s])), [stocks]);
  const smBySymbol = useMemo(() => new Map((smartMoney.data?.stocks ?? []).map((s) => [s.symbol, s])), [smartMoney.data]);
  const prices = useMemo(() => new Map(stocks.map((s) => [s.symbol, { close: s.close, date: s.date }])), [stocks]);
  const summary = useMemo(() => summarize(journal, prices), [journal, prices]);
  const asOf = scanner.data?.data_as_of ?? null;
  const history = useHistory(draft.symbol || null, asOf);

  const ideas = useMemo(() => {
    const rows = new Map<string, { stock: StockScan; ema: boolean; sm: boolean }>();
    for (const s of stocks) if (s.signal === "BUY") rows.set(s.symbol, { stock: s, ema: true, sm: false });
    for (const s of smartMoney.data?.stocks ?? []) {
      if (!s.smart_money_buy) continue;
      const stock = bySymbol.get(s.symbol);
      if (stock) rows.set(s.symbol, { stock, ema: rows.get(s.symbol)?.ema ?? false, sm: true });
    }
    return [...rows.values()].sort((a, b) => Number(b.sm) - Number(a.sm) || a.stock.symbol.localeCompare(b.stock.symbol));
  }, [stocks, smartMoney.data, bySymbol]);

  const update = (next: Journal) => void pj.save(next);
  const setField = (k: keyof Draft) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => setDraft({ ...draft, [k]: e.target.value });

  const sizedQuantity = (price: number) => Math.max(0, Math.floor((SIZE_WEIGHT * summary.equity) / (price * (1 + journal.costRate))));

  const prefill = (stock: StockScan, source: TradeSource) => {
    const price = stock.close ?? 0;
    setDraft({
      symbol: stock.symbol,
      quantity: price > 0 ? String(sizedQuantity(price)) : "",
      entryDate: stock.date,
      entryPrice: price > 0 ? price.toFixed(2) : "",
      source,
      note: "",
    });
    setFormError(null);
  };

  const openOnDate = history.data?.points.find((p) => p.date === draft.entryDate)?.open ?? null;

  const addTrade = (e: React.FormEvent) => {
    e.preventDefault();
    const quantity = Number(draft.quantity);
    const price = Number(draft.entryPrice);
    if (!draft.symbol) return setFormError("Choose a stock.");
    if (!Number.isInteger(quantity) || quantity < 1) return setFormError("Quantity must be a whole number of shares (at least 1).");
    if (!Number.isFinite(price) || price <= 0) return setFormError("Entry price must be above zero.");
    if (!draft.entryDate) return setFormError("Choose the entry date.");
    if (draft.entryDate > today()) return setFormError("Entry date can't be in the future.");
    const needed = buyCost(journal, quantity, price);
    if (needed > summary.cash + 1e-6)
      return setFormError(`Not enough paper cash: this needs ${formatPrice(needed, 0)} (costs included), you have ${formatPrice(summary.cash, 0)}.`);
    update({
      ...journal,
      trades: [
        ...journal.trades,
        { id: newTradeId(), symbol: draft.symbol, quantity, entryDate: draft.entryDate, entryPrice: price, exitDate: null, exitPrice: null, source: draft.source, note: draft.note.trim() },
      ],
    });
    toast.success("Paper trade added", { description: `Bought ${quantity} × ${displaySymbol(draft.symbol)} at ${formatPrice(price)}` });
    setDraft(blankDraft());
    setFormError(null);
  };

  const confirmClose = () => {
    if (!closing) return;
    const trade = journal.trades.find((t) => t.id === closing.id);
    const price = Number(closing.price);
    if (!trade) return setClosing(null);
    if (!Number.isFinite(price) || price <= 0) return toast.error("Exit price must be above zero.");
    if (!closing.date || closing.date < trade.entryDate || closing.date > today())
      return toast.error("Exit date must be between the entry date and today.");
    update({ ...journal, trades: journal.trades.map((t) => (t.id === trade.id ? { ...t, exitDate: closing.date, exitPrice: price } : t)) });
    setClosing(null);
  };

  const removeTrade = (id: string) => {
    const t = journal.trades.find((x) => x.id === id);
    if (t && window.confirm(`Delete the paper trade in ${displaySymbol(t.symbol)}? This can't be undone.`))
      update({ ...journal, trades: journal.trades.filter((x) => x.id !== id) });
  };

  const onImport = async (file: File) => {
    const parsed = parseJournal(await file.text());
    if (!parsed) return toast.error("That file isn't an Altrix paper journal export.");
    const where = cloud ? "the journal in your account" : "the journal in this browser";
    if (window.confirm(`Replace ${where} (${journal.trades.length} trades) with the file (${parsed.trades.length} trades)?`)) {
      update(parsed);
      toast.success("Journal imported");
    }
  };

  const saveSettings = () => {
    if (!settings) return;
    const cash = Number(settings.cash);
    const cost = Number(settings.costPct) / 100;
    if (!Number.isFinite(cash) || cash <= 0) return toast.error("Starting cash must be above zero.");
    if (!Number.isFinite(cost) || cost < 0 || cost >= 0.1) return toast.error("Cost per trade must be between 0% and 10%.");
    update({ ...journal, startingCash: cash, costRate: cost });
    setSettings(null);
  };

  const selectedStock = bySymbol.get(draft.symbol);

  return (
    <div className="flex flex-col gap-5">
      <p className="max-w-3xl text-[13px] leading-relaxed text-muted-foreground">
        Practise Altrix&apos;s signals with pretend money before risking real money. Record a trade when a signal appears, close it
        when the strategy says SELL, and compare your results with the backtest.{" "}
        {cloud ? (
          <>Trades are saved <span className="font-medium text-foreground">in your account</span> and sync across your devices.</>
        ) : (
          <>Trades are saved <span className="font-medium text-foreground">only in this browser</span>; export a backup now and then.</>
        )}
      </p>
      <SyncPanel pj={pj} />
      {cloud && pj.journal === null ? (
        pj.cloudError ? (
          <div role="alert" className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-loss/40 bg-loss-soft px-4 py-3 text-[13px] text-loss">
            Couldn&apos;t load your journal: {pj.cloudError}
            <Button size="sm" variant="outline" onClick={pj.reloadCloud}>Retry</Button>
          </div>
        ) : (
          <Skeleton className="h-[420px] rounded-lg" aria-label="Loading your journal" />
        )
      ) : (
      <>
      {!cloud && !pj.persistent && (
        <p role="alert" className="rounded-md border border-loss/40 bg-loss-soft px-3 py-2 text-xs text-loss">
          This browser is blocking storage, so trades will be lost when you close the page. Export them before leaving.
        </p>
      )}

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <MetricCard
          label="Paper portfolio value"
          value={formatPrice(summary.equity, 0)}
          tone={summary.totalReturn > 0 ? "gain" : summary.totalReturn < 0 ? "loss" : "default"}
          hint={`${formatFraction(summary.totalReturn)} vs ${formatPrice(journal.startingCash, 0)} start`}
        />
        <MetricCard label="Cash" value={formatPrice(summary.cash, 0)} hint={`${summary.open.length} open position${summary.open.length === 1 ? "" : "s"}`} />
        <MetricCard
          label="Unrealized P&L"
          value={formatPrice(summary.unrealizedPnl, 0)}
          tone={summary.unrealizedPnl > 0 ? "gain" : summary.unrealizedPnl < 0 ? "loss" : "default"}
          hint={asOf ? `At the ${formatDate(asOf)} close` : "Waiting for prices"}
        />
        <MetricCard
          label="Realized P&L"
          value={formatPrice(summary.realizedPnl, 0)}
          tone={summary.realizedPnl > 0 ? "gain" : summary.realizedPnl < 0 ? "loss" : "default"}
          hint={summary.winRate === null ? "No closed trades yet" : `Win rate ${formatFraction(summary.winRate, { signed: false, decimals: 0 })} of ${summary.closed.length}`}
        />
      </div>

      <div className="grid items-start gap-5 xl:grid-cols-[minmax(0,1fr)_420px]">
        <Section
          title="Today's signals to practise"
          description={asOf ? `Fresh BUY signals on ${formatDate(asOf)}. The backtester would buy at the next trading day's open.` : "Loading signals…"}
        >
          {ideas.length === 0 ? (
            <EmptyState title="No BUY signals today" description="Nothing to practise today: no EMA crossover and no Smart Money BUY on the latest date." />
          ) : (
            <ul className="divide-y">
              {ideas.map(({ stock, ema, sm }) => (
                <li key={stock.symbol} className="flex items-center gap-3 px-4 py-2.5">
                  <div className="min-w-0 flex-1">
                    <Link href={stockHref(stock.symbol)} className="text-[13px] font-medium hover:underline">{displaySymbol(stock.symbol)}</Link>
                    <div className="truncate text-xs text-muted-foreground">{stock.name ?? "—"}</div>
                  </div>
                  <div className="flex flex-wrap justify-end gap-1">
                    {sm && <span className="rounded-sm bg-gain-soft px-1.5 py-px text-[11px] font-medium text-gain">Smart Money BUY</span>}
                    {ema && <span className="rounded-sm bg-muted px-1.5 py-px text-[11px] font-medium">EMA BUY</span>}
                  </div>
                  <span className="num w-24 text-right text-[13px]">{formatPrice(stock.close)}</span>
                  <Button size="sm" variant="outline" onClick={() => prefill(stock, sm ? "smart_money_buy" : "ema_buy")}>
                    <Plus className="size-3.5" aria-hidden />
                    Paper buy
                  </Button>
                </li>
              ))}
            </ul>
          )}
        </Section>

        <Section title="Add a paper trade" description="Prefilled from a signal, or enter any NIFTY 100 stock.">
          <form onSubmit={addTrade} className="grid grid-cols-2 gap-3 p-4">
            <div className="col-span-2">
              <Field id="pt-symbol" label="Stock">
                <select id="pt-symbol" value={draft.symbol} onChange={setField("symbol")} className={inputClass}>
                  <option value="">Choose a stock…</option>
                  {[...stocks].sort((a, b) => a.symbol.localeCompare(b.symbol)).map((s) => (
                    <option key={s.symbol} value={s.symbol}>{displaySymbol(s.symbol)}{s.name ? ` · ${s.name}` : ""}</option>
                  ))}
                </select>
              </Field>
            </div>
            <Field
              id="pt-date"
              label="Entry date"
              hint={
                openOnDate !== null ? (
                  <button type="button" className="underline underline-offset-2" onClick={() => setDraft({ ...draft, entryPrice: openOnDate.toFixed(2) })}>
                    Use that day&apos;s open {formatPrice(openOnDate)}
                  </button>
                ) : draft.symbol ? "No bar stored for this date yet" : undefined
              }
            >
              <input id="pt-date" type="date" max={todayStr || undefined} value={draft.entryDate} onChange={setField("entryDate")} className={inputClass} />
            </Field>
            <Field
              id="pt-price"
              label="Entry price (₹)"
              hint={selectedStock?.close ? (
                <button type="button" className="underline underline-offset-2" onClick={() => setDraft({ ...draft, entryPrice: selectedStock.close!.toFixed(2) })}>
                  Latest close {formatPrice(selectedStock.close)}
                </button>
              ) : undefined}
            >
              <input id="pt-price" type="number" min={0.01} step={0.01} value={draft.entryPrice} onChange={setField("entryPrice")} className={inputClass} />
            </Field>
            <Field
              id="pt-qty"
              label="Quantity (shares)"
              hint={Number(draft.entryPrice) > 0 ? (
                <button type="button" className="underline underline-offset-2" onClick={() => setDraft({ ...draft, quantity: String(sizedQuantity(Number(draft.entryPrice))) })}>
                  Size like the backtest (10%)
                </button>
              ) : undefined}
            >
              <input id="pt-qty" type="number" min={1} step={1} value={draft.quantity} onChange={setField("quantity")} className={inputClass} />
            </Field>
            <Field id="pt-source" label="Reason">
              <select id="pt-source" value={draft.source} onChange={setField("source")} className={inputClass}>
                {(Object.keys(SOURCE_LABEL) as TradeSource[]).map((k) => <option key={k} value={k}>{SOURCE_LABEL[k]}</option>)}
              </select>
            </Field>
            <div className="col-span-2">
              <Field id="pt-note" label="Note (optional)">
                <input id="pt-note" type="text" maxLength={200} value={draft.note} onChange={setField("note")} placeholder="Why this trade?" className={cn(inputClass, "font-sans")} />
              </Field>
            </div>
            <div className="col-span-2 flex flex-col gap-2 border-t pt-3 sm:flex-row sm:items-center sm:justify-between">
              <p className={cn("text-xs", formError ? "text-loss" : "text-muted-foreground")} role={formError ? "alert" : undefined}>
                {formError ??
                  (Number(draft.quantity) > 0 && Number(draft.entryPrice) > 0
                    ? `Costs ${formatPrice(buyCost(journal, Number(draft.quantity), Number(draft.entryPrice)), 0)} incl. ${formatFraction(journal.costRate, { signed: false, decimals: 2 })} cost · cash ${formatPrice(summary.cash, 0)}`
                    : `Cash available ${formatPrice(summary.cash, 0)}`)}
              </p>
              <Button type="submit" size="sm" className="shrink-0">
                <Plus className="size-3.5" aria-hidden />
                Add trade
              </Button>
            </div>
          </form>
        </Section>
      </div>

      <Section title="Open positions" description="Valued at the latest stored close. The Altrix column shows what the strategy says now.">
        {summary.open.length === 0 ? (
          <EmptyState title="No open paper positions" description="Use “Paper buy” on a signal above, or add any stock with the form." />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-[13px]">
              <thead className="border-b bg-surface text-left text-xs text-muted-foreground">
                <tr>
                  <th scope="col" className="h-8 px-3 font-medium">Stock</th>
                  <th scope="col" className="h-8 px-3 text-right font-medium">Qty</th>
                  <th scope="col" className="h-8 px-3 font-medium">Entry</th>
                  <th scope="col" className="h-8 px-3 text-right font-medium">Last close</th>
                  <th scope="col" className="h-8 px-3 text-right font-medium">Value</th>
                  <th scope="col" className="h-8 px-3 text-right font-medium">Unrealized</th>
                  <th scope="col" className="h-8 px-3 font-medium">Altrix now</th>
                  <th scope="col" className="h-8 px-3"><span className="sr-only">Actions</span></th>
                </tr>
              </thead>
              <tbody>
                {summary.open.map((o) => {
                  const t = o.trade;
                  const isClosing = closing?.id === t.id;
                  return (
                    <tr key={t.id} className="border-b align-top last:border-b-0">
                      <td className="px-3 py-2">
                        <Link href={stockHref(t.symbol)} className="font-medium hover:underline">{displaySymbol(t.symbol)}</Link>
                        <div className="text-xs text-muted-foreground">{SOURCE_LABEL[t.source]}{t.note ? ` · ${t.note}` : ""}</div>
                      </td>
                      <td className="num px-3 py-2 text-right">{formatNumber(t.quantity)}</td>
                      <td className="num px-3 py-2 text-muted-foreground">{formatPrice(t.entryPrice)}<div className="text-xs">{formatDate(t.entryDate)}</div></td>
                      <td className="num px-3 py-2 text-right">{formatPrice(o.lastPrice)}</td>
                      <td className="num px-3 py-2 text-right">{formatPrice(o.marketValue, 0)}</td>
                      <td className={cn("num px-3 py-2 text-right", trendClass[trend(o.unrealizedPnl)])}>
                        {formatPrice(o.unrealizedPnl, 0)}
                        <div className="text-xs">{formatFraction(o.unrealizedPct, { decimals: 1 })}</div>
                      </td>
                      <td className="px-3 py-2"><AltrixStatus stock={bySymbol.get(t.symbol)} sm={smBySymbol.get(t.symbol)} /></td>
                      <td className="px-3 py-2 text-right">
                        {isClosing ? (
                          <div className="flex flex-col items-end gap-1.5">
                            <div className="flex gap-1.5">
                              <input aria-label="Exit date" type="date" min={t.entryDate} max={todayStr || undefined} value={closing.date} onChange={(e) => setClosing({ ...closing, date: e.target.value })} className={cn(inputClass, "w-36")} />
                              <input aria-label="Exit price" type="number" min={0.01} step={0.01} value={closing.price} onChange={(e) => setClosing({ ...closing, price: e.target.value })} className={cn(inputClass, "w-24")} />
                            </div>
                            <div className="flex gap-1.5">
                              <Button size="sm" variant="ghost" onClick={() => setClosing(null)}>Cancel</Button>
                              <Button size="sm" onClick={confirmClose}>Sell</Button>
                            </div>
                          </div>
                        ) : (
                          <div className="flex justify-end gap-1.5">
                            <Button
                              size="sm"
                              variant="outline"
                              onClick={() => setClosing({ id: t.id, date: o.lastDate ?? today(), price: o.lastPrice ? o.lastPrice.toFixed(2) : "" })}
                            >
                              Close
                            </Button>
                            <Button size="sm" variant="ghost" onClick={() => removeTrade(t.id)} aria-label={`Delete ${displaySymbol(t.symbol)} trade`}>Delete</Button>
                          </div>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </Section>

      <Section title="Closed trades" description="Net of the cost per trade. Return = net P&L ÷ cash spent on entry, as in the backtester.">
        {summary.closed.length === 0 ? (
          <EmptyState title="No closed trades yet" description="Close an open position to see realized results here." />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-[13px]">
              <thead className="border-b bg-surface text-left text-xs text-muted-foreground">
                <tr>
                  <th scope="col" className="h-8 px-3 font-medium">Stock</th>
                  <th scope="col" className="h-8 px-3 font-medium">Entry</th>
                  <th scope="col" className="h-8 px-3 font-medium">Exit</th>
                  <th scope="col" className="h-8 px-3 text-right font-medium">Days</th>
                  <th scope="col" className="h-8 px-3 text-right font-medium">Net P&amp;L</th>
                  <th scope="col" className="h-8 px-3 text-right font-medium">Return</th>
                  <th scope="col" className="h-8 px-3"><span className="sr-only">Actions</span></th>
                </tr>
              </thead>
              <tbody>
                {summary.closed.map((c) => (
                  <tr key={c.trade.id} className="border-b last:border-b-0">
                    <td className="px-3 py-2">
                      <Link href={stockHref(c.trade.symbol)} className="font-medium hover:underline">{displaySymbol(c.trade.symbol)}</Link>
                      <div className="text-xs text-muted-foreground">{formatNumber(c.trade.quantity)} sh · {SOURCE_LABEL[c.trade.source]}</div>
                    </td>
                    <td className="num px-3 py-2 text-muted-foreground">{formatPrice(c.trade.entryPrice)}<div className="text-xs">{formatDate(c.trade.entryDate)}</div></td>
                    <td className="num px-3 py-2 text-muted-foreground">{formatPrice(c.trade.exitPrice)}<div className="text-xs">{formatDate(c.trade.exitDate)}</div></td>
                    <td className="num px-3 py-2 text-right text-muted-foreground">{c.holdingDays}</td>
                    <td className={cn("num px-3 py-2 text-right", trendClass[trend(c.netPnl)])}>{formatPrice(c.netPnl, 0)}</td>
                    <td className={cn("num px-3 py-2 text-right", trendClass[trend(c.returnPct)])}>{formatFraction(c.returnPct, { decimals: 1 })}</td>
                    <td className="px-3 py-2 text-right">
                      <Button size="sm" variant="ghost" onClick={() => removeTrade(c.trade.id)} aria-label={`Delete ${displaySymbol(c.trade.symbol)} trade`}>Delete</Button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Section>

      <Section
        title="Journal settings and backup"
        description={
          cloud
            ? "Saved in your account. Export a file any time to keep your own backup."
            : "Saved in this browser only. Export a file to keep a backup or move the journal to another device."
        }
        actions={
          <div className="flex flex-wrap gap-1.5">
            <Button size="sm" variant="outline" onClick={() => exportJournal(journal)}>
              <Download className="size-3.5" aria-hidden />
              Export
            </Button>
            <Button size="sm" variant="outline" onClick={() => fileInput.current?.click()}>
              <Upload className="size-3.5" aria-hidden />
              Import
            </Button>
            <Button
              size="sm"
              variant="ghost"
              onClick={() => {
                const where = cloud ? " from your account on every device" : "";
                if (window.confirm(`Delete every paper trade${where} and start over? Export a backup first if you might want them.`)) update(emptyJournal());
              }}
            >
              <RotateCcw className="size-3.5" aria-hidden />
              Reset
            </Button>
            <input
              ref={fileInput}
              type="file"
              accept="application/json,.json"
              className="hidden"
              onChange={(e) => {
                const f = e.target.files?.[0];
                if (f) void onImport(f);
                e.target.value = "";
              }}
            />
          </div>
        }
      >
        <div className="flex flex-col gap-3 p-4 sm:flex-row sm:items-end">
          <Field id="pt-start" label="Starting paper cash (₹)">
            <input
              id="pt-start"
              type="number"
              min={1}
              step={1000}
              value={settings?.cash ?? String(journal.startingCash)}
              onChange={(e) => setSettings({ cash: e.target.value, costPct: settings?.costPct ?? String(journal.costRate * 100) })}
              className={cn(inputClass, "sm:w-44")}
            />
          </Field>
          <Field id="pt-cost" label="Cost per BUY and SELL (%)">
            <input
              id="pt-cost"
              type="number"
              min={0}
              max={9.99}
              step={0.01}
              value={settings?.costPct ?? String(journal.costRate * 100)}
              onChange={(e) => setSettings({ cash: settings?.cash ?? String(journal.startingCash), costPct: e.target.value })}
              className={cn(inputClass, "sm:w-32")}
            />
          </Field>
          <Button size="sm" variant="outline" disabled={!settings} onClick={saveSettings}>Save settings</Button>
          <p className="text-xs text-muted-foreground sm:ml-auto">{journal.trades.length} trade{journal.trades.length === 1 ? "" : "s"} recorded</p>
        </div>
      </Section>

      </>
      )}

      <p className="text-xs leading-relaxed text-muted-foreground">
        Paper trading only: nothing here places real orders. Prices are end-of-day closes from the stored data, so values update once
        per trading day. Research only, not investment advice.
      </p>
    </div>
  );
}
