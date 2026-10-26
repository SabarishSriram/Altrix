// Paper trading journal: pretend trades kept in this browser's localStorage.
//
// Nothing here touches the API or the strategy: prices come from the scanner the
// page already loads, and P&L uses the backtester's conventions (flat cost on every
// BUY and SELL, return = net P&L / cash spent on entry).

import { useSyncExternalStore } from "react";

export type TradeSource = "ema_buy" | "smart_money_buy" | "manual";

export interface PaperTrade {
  id: string;
  symbol: string;
  quantity: number;
  entryDate: string; // YYYY-MM-DD
  entryPrice: number;
  exitDate: string | null;
  exitPrice: number | null;
  source: TradeSource;
  note: string;
}

export interface Journal {
  version: 1;
  startingCash: number;
  /** Fraction per BUY and per SELL, like the backtester (0.001 = 0.1%). */
  costRate: number;
  trades: PaperTrade[];
}

export const SOURCE_LABEL: Record<TradeSource, string> = {
  ema_buy: "EMA BUY",
  smart_money_buy: "Smart Money BUY",
  manual: "Manual",
};

const KEY = "altrix.paper-journal.v1";
const CHANGE_EVENT = "altrix:paper-journal";
const EMPTY: Journal = { version: 1, startingCash: 100_000, costRate: 0.001, trades: [] };

// ---- storage -------------------------------------------------------------------------

let memory: string | null = null; // used when localStorage is blocked (private mode, disabled site data)
let storageWorks = true;
let cachedRaw: string | null | undefined;
let cached: Journal = EMPTY;

function readRaw(): string | null {
  try {
    return window.localStorage.getItem(KEY);
  } catch {
    storageWorks = false;
    return memory;
  }
}

function snapshot(): Journal {
  const raw = readRaw();
  if (raw !== cachedRaw) {
    cachedRaw = raw;
    cached = raw ? (parseJournal(raw) ?? EMPTY) : EMPTY;
  }
  return cached;
}

function subscribe(onChange: () => void): () => void {
  window.addEventListener("storage", onChange); // other tabs
  window.addEventListener(CHANGE_EVENT, onChange); // this tab
  return () => {
    window.removeEventListener("storage", onChange);
    window.removeEventListener(CHANGE_EVENT, onChange);
  };
}

export function saveJournal(journal: Journal): void {
  const raw = JSON.stringify(journal);
  try {
    window.localStorage.setItem(KEY, raw);
  } catch {
    storageWorks = false;
    memory = raw;
  }
  window.dispatchEvent(new Event(CHANGE_EVENT));
}

/** The journal, re-rendering on every change (also from other tabs). Empty during server rendering. */
export function useJournal(): Journal {
  return useSyncExternalStore(subscribe, snapshot, () => EMPTY);
}

/** False when the browser refuses localStorage: trades then last only until the page is closed. */
export function journalIsPersistent(): boolean {
  return storageWorks;
}

// ---- import / export -------------------------------------------------------------------

const isNum = (v: unknown): v is number => typeof v === "number" && Number.isFinite(v);
const isDate = (v: unknown): v is string => typeof v === "string" && /^\d{4}-\d{2}-\d{2}$/.test(v);

/** A valid journal from JSON text, or null. Used for storage and for imported backups. */
export function parseJournal(text: string): Journal | null {
  try {
    const j = JSON.parse(text) as Partial<Journal>;
    if (j.version !== 1 || !isNum(j.startingCash) || !isNum(j.costRate) || !Array.isArray(j.trades)) return null;
    const ok = j.trades.every(
      (t: Partial<PaperTrade>) =>
        typeof t.id === "string" &&
        typeof t.symbol === "string" &&
        isNum(t.quantity) &&
        t.quantity > 0 &&
        isDate(t.entryDate) &&
        isNum(t.entryPrice) &&
        t.entryPrice > 0 &&
        (t.exitDate === null || isDate(t.exitDate)) &&
        (t.exitPrice === null || (isNum(t.exitPrice) && t.exitPrice > 0)) &&
        (t.source === "ema_buy" || t.source === "smart_money_buy" || t.source === "manual"),
    );
    return ok ? (j as Journal) : null;
  } catch {
    return null;
  }
}

export function exportJournal(journal: Journal): void {
  const blob = new Blob([JSON.stringify(journal, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `altrix-paper-journal-${new Date().toISOString().slice(0, 10)}.json`;
  a.click();
  URL.revokeObjectURL(url);
}

export const emptyJournal = (): Journal => ({ ...EMPTY, trades: [] });

// ---- calculations ----------------------------------------------------------------------

export interface OpenPosition {
  trade: PaperTrade;
  lastPrice: number | null;
  lastDate: string | null;
  marketValue: number | null;
  unrealizedPnl: number | null;
  unrealizedPct: number | null;
}

export interface ClosedTrade {
  trade: PaperTrade;
  netPnl: number;
  returnPct: number;
  holdingDays: number;
}

export interface JournalSummary {
  cash: number;
  equity: number; // cash + open positions at their last close (entry price if unknown)
  totalReturn: number; // fraction vs starting cash
  open: OpenPosition[];
  closed: ClosedTrade[];
  realizedPnl: number;
  unrealizedPnl: number;
  winRate: number | null;
  wins: number;
}

const entrySpend = (t: PaperTrade, cost: number) => t.quantity * t.entryPrice * (1 + cost);
const days = (a: string, b: string) => Math.round((Date.parse(b) - Date.parse(a)) / 86_400_000);

export function summarize(journal: Journal, prices: Map<string, { close: number | null; date: string }>): JournalSummary {
  const cost = journal.costRate;
  let cash = journal.startingCash;
  const open: OpenPosition[] = [];
  const closed: ClosedTrade[] = [];

  for (const t of journal.trades) {
    cash -= entrySpend(t, cost);
    if (t.exitPrice !== null && t.exitDate !== null) {
      const proceeds = t.quantity * t.exitPrice * (1 - cost);
      cash += proceeds;
      const netPnl = proceeds - entrySpend(t, cost);
      closed.push({ trade: t, netPnl, returnPct: netPnl / entrySpend(t, cost), holdingDays: days(t.entryDate, t.exitDate) });
    } else {
      const p = prices.get(t.symbol);
      const last = p?.close ?? null;
      const value = last === null ? null : t.quantity * last;
      const pnl = value === null ? null : value - entrySpend(t, cost);
      open.push({
        trade: t,
        lastPrice: last,
        lastDate: p?.date ?? null,
        marketValue: value,
        unrealizedPnl: pnl,
        unrealizedPct: pnl === null ? null : pnl / entrySpend(t, cost),
      });
    }
  }

  const invested = open.reduce((s, o) => s + (o.marketValue ?? o.trade.quantity * o.trade.entryPrice), 0);
  const equity = cash + invested;
  const wins = closed.filter((c) => c.netPnl > 0).length;
  return {
    cash,
    equity,
    totalReturn: equity / journal.startingCash - 1,
    open: open.sort((a, b) => b.trade.entryDate.localeCompare(a.trade.entryDate)),
    closed: closed.sort((a, b) => (b.trade.exitDate ?? "").localeCompare(a.trade.exitDate ?? "")),
    realizedPnl: closed.reduce((s, c) => s + c.netPnl, 0),
    unrealizedPnl: open.reduce((s, o) => s + (o.unrealizedPnl ?? 0), 0),
    winRate: closed.length ? wins / closed.length : null,
    wins,
  };
}

/** Cash a BUY of `quantity` at `price` needs, costs included. */
export const buyCost = (journal: Journal, quantity: number, price: number) => quantity * price * (1 + journal.costRate);

export function newTradeId(): string {
  return typeof crypto !== "undefined" && "randomUUID" in crypto
    ? crypto.randomUUID()
    : `${Date.now()}-${Math.random().toString(36).slice(2)}`;
}
