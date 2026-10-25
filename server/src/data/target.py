"""Target (label) generation for medium-term position/swing trading.

Question the target answers:
    "If I bought this stock at today's close, did it reach a meaningful
     gain at any point during the next ~2-3 months?"

V1 definition, per stock, per day t:

    future_max_return_60d = max(close[t+1], ..., close[t+60]) / close[t] - 1
    target                = 1 if future_max_return_60d >= +7% else 0

"Next 60 days" means the next 60 *rows*. Weekends and NSE holidays have no
rows, so 60 rows = 60 trading days. Today's close is not part of the window.

This module builds the *answer* the model will learn to predict, so it is
deliberately allowed to look into the future. Nothing produced here may ever
be used as a model input (feature).
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from pandas.api.indexers import FixedForwardWindowIndexer

REQUIRED_COLUMNS: tuple[str, ...] = ("date", "symbol", "close")

HORIZON_DAYS = 60  # ~3 months of NSE trading days
THRESHOLD = 0.07  # +7%, inclusive

# Floating point can put an exact +7% move just under 0.07 (e.g. 0.06999999999999995).
# NSE prices move in 0.05 ticks, so exact hits do occur. Comparing against
# threshold - EPS counts them as reached, and has no effect on any real move.
EPS = 1e-9


def _future_max_close(close: pd.Series, horizon: int) -> pd.Series:
    """For each row t: max(close[t+1 .. t+horizon]), or NaN if the window is incomplete."""
    next_close = close.shift(-1)  # excludes today's close from the window
    window = FixedForwardWindowIndexer(window_size=horizon)
    # min_periods=horizon: a window cut short by the end of the data, or containing
    # a missing close, gives NaN rather than a max over fewer days.
    return next_close.rolling(window, min_periods=horizon).max()


def add_medium_term_target(
    df: pd.DataFrame,
    horizon: int = HORIZON_DAYS,
    threshold: float = THRESHOLD,
) -> pd.DataFrame:
    """Return a copy of `df` with `future_max_return_{horizon}d` and `target` added.

    Args:
        df: Daily bars for one or more symbols. Must contain `date`, `symbol`
            and `close`; all other columns are carried through unchanged.
            Rows must be trading days only (no synthetic weekend/holiday rows).
        horizon: Number of future trading-day rows to look at (default 60).
        threshold: Target is 1 when the best future close is at least this
            much above today's close (default 0.07, i.e. +7%).

    Returns:
        A new DataFrame sorted by (symbol, date) with two extra columns:

        - `future_max_return_{horizon}d` (float64): the highest close over the
          next `horizon` trading days, relative to today's close, minus 1.
        - `target` (float64): 1.0 if that is >= `threshold`, else 0.0;
          NaN where the future window is incomplete.

        The last `horizon` rows of each symbol do not have a full future
        window, so both columns are NaN there. They are never labelled 0.

    Raises:
        ValueError: if required columns are missing, `horizon` < 1, or a symbol
            has duplicate dates (which would make "N rows ahead" ambiguous).
    """
    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(
            f"add_medium_term_target: missing required column(s) {missing}; "
            f"got {list(df.columns)}"
        )
    if horizon < 1:
        raise ValueError(f"add_medium_term_target: horizon must be >= 1, got {horizon}")

    dupes = df.duplicated(subset=["symbol", "date"])
    if dupes.any():
        first = df.loc[dupes, ["symbol", "date"]].iloc[0]
        raise ValueError(
            f"add_medium_term_target: {int(dupes.sum())} duplicate (symbol, date) row(s), "
            f"e.g. {first['symbol']} {pd.Timestamp(first['date']).date()}"
        )

    # Sorting returns a new frame, so the caller's DataFrame is never mutated.
    out = df.sort_values(["symbol", "date"], kind="stable").reset_index(drop=True)

    close = out["close"].astype("float64")
    # Each stock separately: a window never reaches into another symbol's prices.
    future_max = close.groupby(out["symbol"], sort=False).transform(
        _future_max_close, horizon=horizon
    )
    future_max_return = future_max / close - 1

    out[f"future_max_return_{horizon}d"] = future_max_return
    # NaN must stay NaN: a plain (x >= threshold) would turn it into 0.
    out["target"] = np.where(
        future_max_return.notna(),
        (future_max_return >= threshold - EPS).astype("float64"),
        np.nan,
    )
    return out
