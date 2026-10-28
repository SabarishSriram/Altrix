// Reads and writes the paper journal in Supabase (tables in client/supabase/schema.sql).
//
// The journal page edits a whole Journal value at a time; saveCloudJournal turns the change from
// `prev` to `next` into row inserts, updates and deletes, so adding, closing, deleting, importing,
// resetting and migrating all go through the same path.

import type { SupabaseClient } from "@supabase/supabase-js";

import { emptyJournal, type Journal, type PaperTrade, type TradeSource } from "@/lib/paper-journal";

interface TradeRow {
  user_id?: string;
  id: string;
  symbol: string;
  quantity: number;
  entry_date: string;
  entry_price: number;
  exit_date: string | null;
  exit_price: number | null;
  source: TradeSource;
  note: string;
  updated_at?: string;
}

const toRow = (t: PaperTrade, userId: string): TradeRow => ({
  user_id: userId,
  id: t.id,
  symbol: t.symbol,
  quantity: t.quantity,
  entry_date: t.entryDate,
  entry_price: t.entryPrice,
  exit_date: t.exitDate,
  exit_price: t.exitPrice,
  source: t.source,
  note: t.note,
  updated_at: new Date().toISOString(),
});

const fromRow = (r: TradeRow): PaperTrade => ({
  id: r.id,
  symbol: r.symbol,
  quantity: r.quantity,
  entryDate: r.entry_date,
  entryPrice: r.entry_price,
  exitDate: r.exit_date,
  exitPrice: r.exit_price,
  source: r.source,
  note: r.note,
});

export interface CloudJournal {
  journal: Journal;
  /** False until the user's settings row exists (a brand-new account). */
  hasSettings: boolean;
}

export async function loadCloudJournal(sb: SupabaseClient): Promise<CloudJournal> {
  const [settings, trades] = await Promise.all([
    sb.from("paper_journals").select("starting_cash, cost_rate").maybeSingle(),
    sb.from("paper_trades").select("id, symbol, quantity, entry_date, entry_price, exit_date, exit_price, source, note").order("created_at"),
  ]);
  if (settings.error) throw settings.error;
  if (trades.error) throw trades.error;
  const base = emptyJournal();
  return {
    journal: {
      version: 1,
      startingCash: settings.data?.starting_cash ?? base.startingCash,
      costRate: settings.data?.cost_rate ?? base.costRate,
      trades: (trades.data as TradeRow[]).map(fromRow),
    },
    hasSettings: settings.data !== null,
  };
}

/** Write the difference between `prev` (what the database holds) and `next`. */
export async function saveCloudJournal(
  sb: SupabaseClient,
  userId: string,
  prev: CloudJournal,
  next: Journal,
): Promise<void> {
  const before = prev.journal;
  if (!prev.hasSettings || before.startingCash !== next.startingCash || before.costRate !== next.costRate) {
    const { error } = await sb.from("paper_journals").upsert(
      { user_id: userId, starting_cash: next.startingCash, cost_rate: next.costRate, updated_at: new Date().toISOString() },
      { onConflict: "user_id" },
    );
    if (error) throw error;
  }

  const stored = new Map(before.trades.map((t) => [t.id, JSON.stringify(t)]));
  const changed = next.trades.filter((t) => stored.get(t.id) !== JSON.stringify(t));
  const keep = new Set(next.trades.map((t) => t.id));
  const removed = before.trades.filter((t) => !keep.has(t.id)).map((t) => t.id);

  if (changed.length) {
    const { error } = await sb.from("paper_trades").upsert(changed.map((t) => toRow(t, userId)), { onConflict: "user_id,id" });
    if (error) throw error;
  }
  if (removed.length) {
    const { error } = await sb.from("paper_trades").delete().in("id", removed);
    if (error) throw error;
  }
}

/** `cloud` plus every local trade it doesn't have yet; local settings win only for a new account. */
export function mergeLocalIntoCloud(cloud: CloudJournal, local: Journal): Journal {
  const have = new Set(cloud.journal.trades.map((t) => t.id));
  return {
    version: 1,
    startingCash: cloud.hasSettings ? cloud.journal.startingCash : local.startingCash,
    costRate: cloud.hasSettings ? cloud.journal.costRate : local.costRate,
    trades: [...cloud.journal.trades, ...local.trades.filter((t) => !have.has(t.id))],
  };
}
