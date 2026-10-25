// Display formatting only. Values are never recomputed here.

import { format, formatDistanceToNowStrict, parseISO } from "date-fns";

const inr2 = new Intl.NumberFormat("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const inr0 = new Intl.NumberFormat("en-IN", { maximumFractionDigits: 0 });
const compact = new Intl.NumberFormat("en-IN", { notation: "compact", maximumFractionDigits: 1 });
const int = new Intl.NumberFormat("en-IN");

export const DASH = "—";

const isNum = (v: number | null | undefined): v is number => typeof v === "number" && Number.isFinite(v);

/** ₹ with Indian digit grouping: 351595.2 -> "₹3,51,595.20". */
export function formatPrice(v: number | null | undefined, decimals: 0 | 2 = 2): string {
  if (!isNum(v)) return DASH;
  return `${v < 0 ? "−" : ""}₹${(decimals === 2 ? inr2 : inr0).format(Math.abs(v))}`;
}

export function formatNumber(v: number | null | undefined): string {
  return isNum(v) ? int.format(v) : DASH;
}

export function formatCompact(v: number | null | undefined): string {
  return isNum(v) ? compact.format(v) : DASH;
}

/** Value already in percent: 1.234 -> "+1.23%". */
export function formatPercent(v: number | null | undefined, { signed = true, decimals = 2 } = {}): string {
  if (!isNum(v)) return DASH;
  const sign = v > 0 && signed ? "+" : v < 0 ? "−" : "";
  return `${sign}${Math.abs(v).toFixed(decimals)}%`;
}

/** Fraction: 0.0525 -> "+5.25%". */
export function formatFraction(v: number | null | undefined, opts?: { signed?: boolean; decimals?: number }): string {
  return isNum(v) ? formatPercent(v * 100, opts) : DASH;
}

/** "2026-10-16" -> "16 Oct 2026". */
export function formatDate(iso: string | null | undefined, pattern = "dd MMM yyyy"): string {
  if (!iso) return DASH;
  return format(parseISO(iso), pattern);
}

/** UTC timestamp -> "3 minutes ago". */
export function formatRelative(iso: string | null | undefined): string {
  if (!iso) return DASH;
  return `${formatDistanceToNowStrict(parseISO(iso))} ago`;
}

/** UTC timestamp -> local "16 Oct 2026, 21:05". */
export function formatTimestamp(iso: string | null | undefined): string {
  if (!iso) return DASH;
  return format(parseISO(iso), "dd MMM yyyy, HH:mm");
}

/** "RELIANCE.NS" -> "RELIANCE". */
export function displaySymbol(symbol: string): string {
  return symbol.replace(/\.NS$/, "");
}

/** Sign for colouring: gains green, losses red, zero/unknown neutral. */
export function trend(v: number | null | undefined): "up" | "down" | "flat" {
  if (!isNum(v) || v === 0) return "flat";
  return v > 0 ? "up" : "down";
}

export const trendClass = {
  up: "text-gain",
  down: "text-loss",
  flat: "text-muted-foreground",
} as const;
