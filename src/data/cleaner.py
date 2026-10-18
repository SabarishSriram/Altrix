"""Turn stored bars into a tidy frame that downstream code can trust.

Cleaning only ever *removes* rows. It never fills, interpolates or edits values.
Removed rows become gaps, and gaps are returned alongside the data so that
later steps (e.g. return calculations) can decide how to treat them.

Rows removed:
  - holiday:    bar on a date the market did not trade (Yahoo placeholder bars)
  - filler:     zero volume with open == high == low == close, i.e. no trade
                happened and the provider repeated the last price
  - invalid:    missing values, non-positive prices, negative volume, or
                low/high not bracketing open/close
  - duplicate:  repeated date (the last occurrence is kept)
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from .downloader import ParquetStore
from .provider import COLUMNS, SCHEMA
from .validator import build_trading_calendar

PRICE_COLS = ["open", "high", "low", "close"]


@dataclass
class CleanResult:
    symbol: str
    data: pd.DataFrame  # SCHEMA columns, sorted, unique dates
    removed: dict[str, int] = field(default_factory=dict)  # reason -> rows dropped
    gaps: list[pd.Timestamp] = field(default_factory=list)  # trading days with no bar after cleaning


def invalid_rows(df: pd.DataFrame) -> pd.Series:
    """Boolean mask of rows with missing or impossible OHLCV values."""
    prices = df[PRICE_COLS]
    missing = df[PRICE_COLS + ["volume"]].isna().any(axis=1)
    non_positive = (prices <= 0).any(axis=1)
    negative_volume = df["volume"].fillna(0) < 0
    bad_range = (df["high"] < prices.max(axis=1)) | (df["low"] > prices.min(axis=1))
    return missing | non_positive | negative_volume | bad_range.fillna(False)


def filler_rows(df: pd.DataFrame) -> pd.Series:
    """Zero-volume flat bars: the stock did not trade, the provider repeated a price."""
    flat = df[PRICE_COLS].nunique(axis=1) == 1
    return (df["volume"] == 0).fillna(False) & flat


def clean(df: pd.DataFrame, symbol: str, calendar: pd.DatetimeIndex) -> CleanResult:
    """Clean one symbol's bars against a trading calendar (see build_trading_calendar)."""
    df = df[COLUMNS].astype(SCHEMA).sort_values("date", kind="stable").reset_index(drop=True)
    removed: dict[str, int] = {}

    def drop(mask: pd.Series, reason: str) -> pd.DataFrame:
        n = int(mask.sum())
        if n:
            removed[reason] = removed.get(reason, 0) + n
        return df[~mask].reset_index(drop=True)

    df = drop(df["date"].duplicated(keep="last"), "duplicate")
    df = drop(~df["date"].isin(calendar), "holiday")
    df = drop(filler_rows(df), "filler")
    df = drop(invalid_rows(df), "invalid")

    gaps: list[pd.Timestamp] = []
    if not df.empty:
        lo, hi = df["date"].min(), df["date"].max()
        expected = calendar[(calendar >= lo) & (calendar <= hi)]
        gaps = list(expected.difference(pd.DatetimeIndex(df["date"])))

    return CleanResult(symbol, df, removed, gaps)


def load_clean(store: ParquetStore, symbols: list[str] | None = None) -> dict[str, CleanResult]:
    """Load and clean stored symbols.

    The trading calendar is always inferred from *every* stored symbol, so
    asking for one symbol gives the same answer as asking for all of them.
    """
    all_frames = {s: store.load(s) for s in store.symbols()}
    calendar = build_trading_calendar(list(all_frames.values()))
    wanted = symbols if symbols is not None else list(all_frames)
    missing = [s for s in wanted if s not in all_frames]
    if missing:
        raise KeyError(f"no stored data for: {', '.join(missing)}")
    return {s: clean(all_frames[s], s, calendar) for s in wanted}
