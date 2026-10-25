"""Smart Money: institutional footprints in daily OHLCV, and an EMA 20/50 variant that waits for them.

Per stock, per trading day t (rows are that stock's own trading days; every
window looks backwards, so nothing after t is ever read):

    vol_spike_ratio            volume[t] / mean(volume[t-19 .. t])
    clv                        (close - low) / (high - low): 1 = closed at the high,
                               0 = at the low; NaN when high == low
    pocket_pivot               close[t] > close[t-1]
                               and volume[t] > the largest down-day volume in t-10 .. t-1
                                   (a down day closes below the previous close; 0 if none)
                               and close[t] >= 0.95 * ema50[t]
    institutional_accumulation close[t] > close[t-1] and vol_spike_ratio >= 2.0 and clv >= 0.5
    smart_money_active_10d     a pocket pivot or institutional accumulation on any of t-9 .. t

`generate_smart_money_signals` keeps the baseline SELL rule and filters BUYs:

    BUY  if  EMA20 crosses above EMA50 today and smart_money_active_10d
         or  EMA20 was already above EMA50 (yesterday and today), a pocket pivot
             fires today, and the close is within 5% of EMA20

Like the baseline, a signal on day t uses t's close and is executed by the
backtester at the next trading day's open.
"""

from __future__ import annotations

import pandas as pd

from .baseline import LONG_WINDOW, ema, generate_baseline_signals

VOLUME_WINDOW = 20  # days in the average volume of vol_spike_ratio
POCKET_PIVOT_LOOKBACK = 10  # prior days whose down-day volumes a pocket pivot must beat
POCKET_PIVOT_EMA50_FLOOR = 0.95  # close >= 95% of EMA50
ACCUMULATION_SPIKE = 2.0  # vol_spike_ratio
ACCUMULATION_CLV = 0.5
MEMORY_DAYS = 10  # smart_money_active_10d window, including today
PIVOT_NEAR_EMA20 = 0.05  # re-entry pocket pivot must close within 5% of EMA20

FOOTPRINT_COLUMNS = ("vol_spike_ratio", "clv", "pocket_pivot", "institutional_accumulation",
                     "smart_money_active_10d")
REQUIRED_COLUMNS = ("date", "symbol", "high", "low", "close", "volume")


def add_smart_money_footprint(df: pd.DataFrame) -> pd.DataFrame:
    """Return a copy of `df` sorted by (symbol, date) with FOOTPRINT_COLUMNS added.

    Needs date, symbol, high, low, close and volume; adds `ema50` if it is not
    already there (from `generate_baseline_signals`). Every other column is
    carried through unchanged.
    """
    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"add_smart_money_footprint: missing required column(s) {missing}; "
                         f"got {list(df.columns)}")

    out = df.sort_values(["symbol", "date"], kind="stable").reset_index(drop=True)
    by = out["symbol"]
    close = out["close"].astype("float64")
    high = out["high"].astype("float64")
    low = out["low"].astype("float64")
    volume = out["volume"].astype("float64")  # nullable Int64 -> float, so a missing volume is NaN
    prev_close = close.groupby(by, sort=False).shift(1)
    if "ema50" not in out.columns:
        out["ema50"] = close.groupby(by, sort=False).transform(lambda s: ema(s, LONG_WINDOW))

    avg_volume = volume.groupby(by, sort=False).transform(
        lambda s: s.rolling(VOLUME_WINDOW, min_periods=VOLUME_WINDOW).mean())
    out["vol_spike_ratio"] = volume / avg_volume

    day_range = high - low
    out["clv"] = ((close - low) / day_range).where(day_range > 0)

    up_day = close > prev_close  # False on a stock's first row (prev_close is NaN)
    # Volume on down days, 0 on other days; the window ends yesterday (shift(1)).
    down_volume = volume.where(close < prev_close, 0.0)
    prior_down_max = down_volume.groupby(by, sort=False).transform(
        lambda s: s.shift(1).rolling(POCKET_PIVOT_LOOKBACK, min_periods=POCKET_PIVOT_LOOKBACK).max())
    out["pocket_pivot"] = (up_day & (volume > prior_down_max)
                           & (close >= POCKET_PIVOT_EMA50_FLOOR * out["ema50"]))

    out["institutional_accumulation"] = (up_day & (out["vol_spike_ratio"] >= ACCUMULATION_SPIKE)
                                         & (out["clv"] >= ACCUMULATION_CLV))

    footprint = (out["pocket_pivot"] | out["institutional_accumulation"]).astype("float64")
    out["smart_money_active_10d"] = footprint.groupby(by, sort=False).transform(
        lambda s: s.rolling(MEMORY_DAYS, min_periods=1).max()).astype(bool)
    return out


def generate_smart_money_signals(df: pd.DataFrame) -> pd.DataFrame:
    """Baseline EMA 20/50 signals with BUYs filtered by the Smart Money footprint.

    Returns the baseline output plus FOOTPRINT_COLUMNS and `baseline_buy_signal`
    (the unfiltered crossover, for comparison). `buy_signal` is replaced by the
    filtered rule in the module docstring; `sell_signal` is the baseline's.
    """
    out = add_smart_money_footprint(generate_baseline_signals(df))
    by = out["symbol"]
    prev_ema20 = out.groupby(by, sort=False)["ema20"].shift(1)
    prev_ema50 = out.groupby(by, sort=False)["ema50"].shift(1)
    already_above = (out["ema20"] > out["ema50"]) & (prev_ema20 > prev_ema50)
    near_ema20 = (out["close"].astype("float64") / out["ema20"] - 1).abs() <= PIVOT_NEAR_EMA20

    out["baseline_buy_signal"] = out["buy_signal"]
    confirmed_crossover = out["buy_signal"] & out["smart_money_active_10d"]
    pivot_reentry = already_above & out["pocket_pivot"] & near_ema20
    out["buy_signal"] = confirmed_crossover | pivot_reentry
    return out
