"""Smart Money scanner: each stock's institutional footprint on the latest trading day.

    strategy frame (cleaned bars + EMA20/EMA50) -> add_smart_money_footprint -> latest row per stock
    + optional NSE deliverables (add_delivery_signals), matched on the same date

Ranked by vol_spike_ratio, highest first (missing last, then by symbol). All
footprint values come from `src.strategy.smart_money`; this module only selects
the latest row. A stock with no bar on the scan date keeps its row with a note
and no footprint values, so a stale spike is never ranked as today's.
"""

from __future__ import annotations

import pandas as pd

from src.data.deliverables import add_delivery_signals
from src.strategy.smart_money import add_smart_money_footprint

UPTREND = "UPTREND"  # EMA20 above EMA50
DOWNTREND = "DOWNTREND"  # EMA20 at or below EMA50
NO_TREND = "INSUFFICIENT_DATA"  # fewer than 50 bars

SMART_MONEY_COLUMNS = [
    "symbol", "name", "date", "close", "prev_close", "return_1d_pct", "volume",
    "vol_spike_ratio", "clv", "pocket_pivot", "institutional_accumulation", "smart_money_active_10d",
    "ema20", "ema50", "trend",
    "deliv_qty", "deliv_per", "deliv_spike_ratio", "delivery_spike",
    "note",
]
_DAY_VALUES = ["return_1d_pct", "vol_spike_ratio", "clv"]
_DAY_FLAGS = ["pocket_pivot", "institutional_accumulation", "smart_money_active_10d", "delivery_spike"]


def scan_smart_money(
    strategy_frame: pd.DataFrame,
    as_of: pd.Timestamp | None = None,
    deliverables: pd.DataFrame | None = None,
    names: dict[str, str] | None = None,
) -> pd.DataFrame:
    """One row per stock (SMART_MONEY_COLUMNS), ranked by vol_spike_ratio.

    Args:
        strategy_frame: `generate_baseline_signals` output with high, low and volume.
        as_of: scan date; defaults to the latest date in the frame.
        deliverables: optional `DeliverableStore.load()` rows (date, symbol, deliv_qty, deliv_per).
        names: optional symbol -> company name.
    """
    if strategy_frame.empty:
        return pd.DataFrame(columns=SMART_MONEY_COLUMNS)
    fp = add_smart_money_footprint(strategy_frame)
    fp["prev_close"] = fp.groupby("symbol", sort=False)["close"].shift(1)
    fp["return_1d_pct"] = (fp["close"] / fp["prev_close"] - 1) * 100
    as_of = fp["date"].max() if as_of is None else pd.Timestamp(as_of)
    fp = fp[fp["date"] <= as_of]

    latest = fp.groupby("symbol", sort=False).tail(1).reset_index(drop=True)
    latest["trend"] = NO_TREND
    known = latest["ema20"].notna() & latest["ema50"].notna()
    latest.loc[known, "trend"] = (latest.loc[known, "ema20"] > latest.loc[known, "ema50"]).map(
        {True: UPTREND, False: DOWNTREND})

    for col in ("deliv_qty", "deliv_per", "deliv_spike_ratio"):
        latest[col] = float("nan")
    latest["delivery_spike"] = False
    if deliverables is not None and not deliverables.empty:
        d = add_delivery_signals(deliverables)
        d = d[["symbol", "date", "deliv_qty", "deliv_per", "deliv_spike_ratio", "delivery_spike"]]
        latest = latest.drop(columns=["deliv_qty", "deliv_per", "deliv_spike_ratio", "delivery_spike"])
        latest = latest.merge(d, on=["symbol", "date"], how="left")
        latest["delivery_spike"] = latest["delivery_spike"].eq(True)  # no deliverables row that day -> False

    stale = latest["date"] != as_of
    latest["note"] = ""
    latest.loc[stale, "note"] = [f"No bar on {as_of.date()}; last bar {d.date()}" for d in latest.loc[stale, "date"]]
    latest.loc[stale, _DAY_VALUES] = float("nan")
    for col in _DAY_FLAGS:
        latest[col] = latest[col].astype(bool) & ~stale

    latest["name"] = latest["symbol"].map(names or {}).fillna("")
    latest = latest.assign(_missing=latest["vol_spike_ratio"].isna(),
                           _spike=-latest["vol_spike_ratio"].fillna(0.0))
    latest = latest.sort_values(["_missing", "_spike", "symbol"]).reset_index(drop=True)
    return latest[SMART_MONEY_COLUMNS]
