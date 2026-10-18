"""Market data providers.

`MarketDataProvider` is the interface the rest of Altrix depends on.
`YahooFinanceProvider` is the first (free) implementation, built on yfinance.
Swapping in another vendor later means writing one new subclass.
"""

from __future__ import annotations

import logging
import time
from abc import ABC, abstractmethod
from datetime import date

import pandas as pd

logger = logging.getLogger(__name__)

# The normalized schema every provider must return, in column order.
SCHEMA: dict[str, str] = {
    "date": "datetime64[ns]",
    "symbol": "string",
    "open": "float64",
    "high": "float64",
    "low": "float64",
    "close": "float64",
    "volume": "Int64",  # nullable int, so a missing volume stays visible instead of becoming 0
}
COLUMNS = list(SCHEMA)


class ProviderError(Exception):
    """Raised when a provider cannot return data for a symbol."""


def empty_frame() -> pd.DataFrame:
    """An empty DataFrame with the normalized schema."""
    return pd.DataFrame({col: pd.Series(dtype=dtype) for col, dtype in SCHEMA.items()})


def normalize(df: pd.DataFrame, symbol: str) -> pd.DataFrame:
    """Coerce a frame with date/open/high/low/close/volume columns into SCHEMA.

    Rows are sorted by date. Nothing is filled in: missing values stay missing
    so the validator can report them.
    """
    if df.empty:
        return empty_frame()
    # Daily bars: drop timezone and time-of-day, keep the exchange-local calendar date.
    dates = pd.to_datetime(df["date"])
    if dates.dt.tz is not None:
        dates = dates.dt.tz_localize(None)
    out = pd.DataFrame(
        {
            "date": dates.dt.normalize(),
            "symbol": symbol,
            "open": df["open"],
            "high": df["high"],
            "low": df["low"],
            "close": df["close"],
            "volume": pd.to_numeric(df["volume"]).round(),
        }
    )
    out = out.astype(SCHEMA)
    return out.sort_values("date").reset_index(drop=True)


class MarketDataProvider(ABC):
    """Interface for anything that can supply daily OHLCV bars."""

    @abstractmethod
    def get_daily_history(self, symbol: str, start: date, end: date) -> pd.DataFrame:
        """Return daily bars for `symbol` with start <= date < end, in SCHEMA format.

        `end` is exclusive. Raise ProviderError if the data cannot be fetched.
        An empty frame (with SCHEMA columns) means "no bars in that range".
        """


class YahooFinanceProvider(MarketDataProvider):
    """Daily OHLCV from Yahoo Finance via yfinance (free, unofficial)."""

    def __init__(self, retries: int = 2, pause_seconds: float = 2.0):
        self.retries = retries
        self.pause_seconds = pause_seconds

    def get_daily_history(self, symbol: str, start: date, end: date) -> pd.DataFrame:
        import yfinance as yf  # imported lazily so tests never need network access

        if start >= end:
            return empty_frame()

        last_error: Exception | None = None
        for attempt in range(self.retries + 1):
            try:
                raw = yf.Ticker(symbol).history(
                    start=start.isoformat(),
                    end=end.isoformat(),  # exclusive in yfinance
                    interval="1d",
                    auto_adjust=False,  # keep raw OHLC (split-adjusted only), see README
                    actions=False,
                )
                return self._to_schema(raw, symbol, start, end)
            except Exception as exc:  # yfinance raises a variety of exception types
                last_error = exc
                if attempt < self.retries:
                    wait = self.pause_seconds * (attempt + 1)
                    logger.warning("%s: attempt %d failed (%s), retrying in %.0fs",
                                   symbol, attempt + 1, exc, wait)
                    time.sleep(wait)
        raise ProviderError(f"{symbol}: {last_error}") from last_error

    @staticmethod
    def _to_schema(raw: pd.DataFrame, symbol: str, start: date, end: date) -> pd.DataFrame:
        if raw is None or raw.empty:
            return empty_frame()
        raw = raw.reset_index().rename(columns=str.lower)
        missing = {"date", "open", "high", "low", "close", "volume"} - set(raw.columns)
        if missing:
            raise ProviderError(f"{symbol}: response missing columns {sorted(missing)}")
        df = normalize(raw, symbol)
        # Guard against the provider returning bars outside the requested window.
        mask = (df["date"] >= pd.Timestamp(start)) & (df["date"] < pd.Timestamp(end))
        return df.loc[mask].reset_index(drop=True)
