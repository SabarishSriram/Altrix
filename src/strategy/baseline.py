"""Baseline strategy: 20-day / 50-day simple moving average (SMA) crossover.

A deliberately simple, non-AI benchmark that later ML strategies must beat.

Per stock, per trading day t:

    sma20[t] = mean(close[t-19 .. t])
    sma50[t] = mean(close[t-49 .. t])

    BUY  on t if sma20[t-1] <= sma50[t-1] and sma20[t] > sma50[t]   (crosses above)
    SELL on t if sma20[t-1] >= sma50[t-1] and sma20[t] < sma50[t]   (crosses below)
    otherwise no signal (HOLD)

Timing: both SMAs include day t's close, so a signal on day t is only known
*after* day t closes. This module only reports the signal on the day it is
generated; the backtester (a later step) must execute it at the next
trading day's open, never at day t's close.

Only past and current rows are used (rolling windows look backwards, the
"previous day" values come from shift(+1)), so there is no lookahead. Any
other columns in the input, including targets, are carried through untouched
and never read.
"""

from __future__ import annotations

import pandas as pd

REQUIRED_COLUMNS: tuple[str, ...] = ("date", "symbol", "close")

SHORT_WINDOW = 20
LONG_WINDOW = 50


def generate_baseline_signals(df: pd.DataFrame) -> pd.DataFrame:
    """Return a copy of `df` with SMA20/SMA50 crossover signals added.

    Args:
        df: Daily bars for one or more symbols (e.g. the validated OHLCV
            schema). Must contain `date`, `symbol` and `close`; every other
            column is carried through unchanged. Rows must be trading days
            only, so a 20-row window is 20 trading days.

    Returns:
        A new DataFrame sorted by (symbol, date) with four extra columns:

        - `sma20` (float64): mean of the last 20 closes, NaN until 20 rows exist.
        - `sma50` (float64): mean of the last 50 closes, NaN until 50 rows exist.
        - `buy_signal` (bool): True only on the day SMA20 crosses above SMA50.
        - `sell_signal` (bool): True only on the day SMA20 crosses below SMA50.

        A crossover needs valid SMAs on both the previous day and today, so
        the first possible signal is on a stock's 51st row.

    Raises:
        ValueError: if required columns are missing or a symbol has duplicate
            dates (which would make the moving-average windows ambiguous).
    """
    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(
            f"generate_baseline_signals: missing required column(s) {missing}; "
            f"got {list(df.columns)}"
        )

    dupes = df.duplicated(subset=["symbol", "date"])
    if dupes.any():
        first = df.loc[dupes, ["symbol", "date"]].iloc[0]
        raise ValueError(
            f"generate_baseline_signals: {int(dupes.sum())} duplicate (symbol, date) row(s), "
            f"e.g. {first['symbol']} {pd.Timestamp(first['date']).date()}"
        )

    # Sorting returns a new frame, so the caller's DataFrame is never mutated.
    out = df.sort_values(["symbol", "date"], kind="stable").reset_index(drop=True)

    # Each stock separately: no window or "previous day" ever crosses into another symbol.
    by_symbol = out["close"].astype("float64").groupby(out["symbol"], sort=False)
    out["sma20"] = by_symbol.transform(lambda s: s.rolling(SHORT_WINDOW, min_periods=SHORT_WINDOW).mean())
    out["sma50"] = by_symbol.transform(lambda s: s.rolling(LONG_WINDOW, min_periods=LONG_WINDOW).mean())

    prev_sma20 = out.groupby("symbol", sort=False)["sma20"].shift(1)
    prev_sma50 = out.groupby("symbol", sort=False)["sma50"].shift(1)

    # Any comparison with NaN is False, so rows without enough history never signal.
    out["buy_signal"] = (prev_sma20 <= prev_sma50) & (out["sma20"] > out["sma50"])
    out["sell_signal"] = (prev_sma20 >= prev_sma50) & (out["sma20"] < out["sma50"])
    return out
