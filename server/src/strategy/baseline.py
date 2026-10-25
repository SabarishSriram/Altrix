"""Baseline strategy: 20-day / 50-day exponential moving average (EMA) crossover.

A deliberately simple, non-AI benchmark that later ML strategies must beat.

Per stock, per trading day t (span N = 20 or 50, alpha = 2 / (N + 1)):

    emaN[t] = alpha * close[t] + (1 - alpha) * emaN[t-1]      emaN[first row] = its close
    emaN is hidden (NaN) until the stock has N rows, while the recursion warms up.

An EMA weights recent closes more than old ones, so it turns sooner than a
simple average of the same length (pandas `ewm(span=N, adjust=False)`).

    BUY  on t if ema20[t-1] <= ema50[t-1] and ema20[t] > ema50[t]   (crosses above)
    SELL on t if ema20[t-1] >= ema50[t-1] and ema20[t] < ema50[t]   (crosses below)
    otherwise no signal (HOLD)

Timing: both EMAs include day t's close, so a signal on day t is only known
*after* day t closes. This module only reports the signal on the day it is
generated; the backtester (a later step) must execute it at the next
trading day's open, never at day t's close.

Only past and current rows are used (the EMA recursion runs forwards in time,
the "previous day" values come from shift(+1)), so there is no lookahead. Any
other columns in the input, including targets, are carried through untouched
and never read.
"""

from __future__ import annotations

import pandas as pd

REQUIRED_COLUMNS: tuple[str, ...] = ("date", "symbol", "close")

SHORT_WINDOW = 20
LONG_WINDOW = 50


def ema(close: pd.Series, span: int) -> pd.Series:
    """Exponential moving average of one stock's closes; NaN for the first `span - 1` rows."""
    return close.ewm(span=span, adjust=False, min_periods=span).mean()


def generate_baseline_signals(df: pd.DataFrame) -> pd.DataFrame:
    """Return a copy of `df` with EMA20/EMA50 crossover signals added.

    Args:
        df: Daily bars for one or more symbols (e.g. the validated OHLCV
            schema). Must contain `date`, `symbol` and `close`; every other
            column is carried through unchanged. Rows must be trading days
            only, so a 20-day EMA spans 20 trading days.

    Returns:
        A new DataFrame sorted by (symbol, date) with four extra columns:

        - `ema20` (float64): 20-day EMA of the close, NaN until 20 rows exist.
        - `ema50` (float64): 50-day EMA of the close, NaN until 50 rows exist.
        - `buy_signal` (bool): True only on the day EMA20 crosses above EMA50.
        - `sell_signal` (bool): True only on the day EMA20 crosses below EMA50.

        A crossover needs valid EMAs on both the previous day and today, so
        the first possible signal is on a stock's 51st row.

    Raises:
        ValueError: if required columns are missing or a symbol has duplicate
            dates (which would make the moving averages ambiguous).
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

    # Each stock separately: no average or "previous day" ever crosses into another symbol.
    by_symbol = out["close"].astype("float64").groupby(out["symbol"], sort=False)
    out["ema20"] = by_symbol.transform(lambda s: ema(s, SHORT_WINDOW))
    out["ema50"] = by_symbol.transform(lambda s: ema(s, LONG_WINDOW))

    prev_ema20 = out.groupby("symbol", sort=False)["ema20"].shift(1)
    prev_ema50 = out.groupby("symbol", sort=False)["ema50"].shift(1)

    # Any comparison with NaN is False, so rows without enough history never signal.
    out["buy_signal"] = (prev_ema20 <= prev_ema50) & (out["ema20"] > out["ema50"])
    out["sell_signal"] = (prev_ema20 >= prev_ema50) & (out["ema20"] < out["ema50"])
    return out
