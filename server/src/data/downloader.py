"""Download daily bars for a universe and keep them in per-symbol Parquet files.

Incremental by default: if data/processed/<SYMBOL>.parquet exists, only bars
after its last stored date are requested and appended.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

from .provider import COLUMNS, MarketDataProvider, ProviderError, SCHEMA, empty_frame
from .validator import ValidationReport, build_trading_calendar, validate

logger = logging.getLogger(__name__)

MARKET_TZ = "Asia/Kolkata"
MARKET_CLOSE_BUFFER_HOUR = 16  # NSE closes 15:30 IST; treat today's bar as final after 16:00


def default_end() -> date:
    """Exclusive end date: today if the session may still be running, else tomorrow.

    This prevents storing a partial intraday bar as if it were a final daily bar,
    and never requests dates in the future.
    """
    now = pd.Timestamp.now(tz=MARKET_TZ)
    today = now.date()
    return today + timedelta(days=1) if now.hour >= MARKET_CLOSE_BUFFER_HOUR else today


def default_start(years: int = 10) -> date:
    today = pd.Timestamp.now(tz=MARKET_TZ).date()
    return today.replace(year=today.year - years)


class ParquetStore:
    """One Parquet file per symbol: <root>/<SYMBOL>.parquet."""

    def __init__(self, root: Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def path(self, symbol: str) -> Path:
        return self.root / f"{symbol}.parquet"

    def load(self, symbol: str) -> pd.DataFrame:
        p = self.path(symbol)
        if not p.exists():
            return empty_frame()
        return pd.read_parquet(p).astype(SCHEMA)[COLUMNS]

    def save(self, symbol: str, df: pd.DataFrame) -> None:
        # Write to a temp file first so an interrupted run never leaves a corrupt file.
        tmp = self.path(symbol).with_suffix(".parquet.tmp")
        df[COLUMNS].astype(SCHEMA).to_parquet(tmp, index=False, engine="pyarrow")
        tmp.replace(self.path(symbol))

    def symbols(self) -> list[str]:
        return sorted(p.name.removesuffix(".parquet") for p in self.root.glob("*.parquet"))


@dataclass
class DownloadResult:
    symbol: str
    status: str  # "downloaded" | "updated" | "up_to_date" | "failed"
    new_rows: int = 0
    total_rows: int = 0
    error: str | None = None


def update_symbol(
    symbol: str,
    provider: MarketDataProvider,
    store: ParquetStore,
    start: date,
    end: date,
    full_refresh: bool = False,
) -> DownloadResult:
    """Fetch only what is missing for one symbol and save the merged result."""
    existing = empty_frame() if full_refresh else store.load(symbol)

    fetch_start = start
    if not existing.empty:
        fetch_start = existing["date"].max().date() + timedelta(days=1)
        # Nothing to do if the gap contains no weekdays (e.g. run on a Sunday).
        if len(pd.bdate_range(fetch_start, end - timedelta(days=1))) == 0:
            return DownloadResult(symbol, "up_to_date", 0, len(existing))

    try:
        new = provider.get_daily_history(symbol, fetch_start, end)
    except ProviderError as exc:
        return DownloadResult(symbol, "failed", 0, len(existing), str(exc))

    if new.empty:
        if existing.empty:
            return DownloadResult(symbol, "failed", 0, 0, "provider returned no data")
        return DownloadResult(symbol, "up_to_date", 0, len(existing))

    combined = pd.concat([existing, new], ignore_index=True) if not existing.empty else new
    combined = (
        combined.drop_duplicates(subset="date", keep="last")
        .sort_values("date")
        .reset_index(drop=True)
    )
    store.save(symbol, combined)
    status = "downloaded" if existing.empty else "updated"
    return DownloadResult(symbol, status, len(combined) - len(existing), len(combined))


def download_all(
    symbols: list[str],
    provider: MarketDataProvider,
    store: ParquetStore,
    start: date,
    end: date,
    full_refresh: bool = False,
) -> list[DownloadResult]:
    """Update every symbol. One symbol failing never stops the others."""
    results = []
    for i, symbol in enumerate(symbols, 1):
        try:
            result = update_symbol(symbol, provider, store, start, end, full_refresh)
        except Exception as exc:  # unexpected bug or I/O error: record it and keep going
            logger.exception("%s: unexpected error", symbol)
            result = DownloadResult(symbol, "failed", error=f"{type(exc).__name__}: {exc}")
        logger.info("[%d/%d] %-15s %-10s +%d rows (total %d)%s", i, len(symbols), symbol,
                    result.status, result.new_rows, result.total_rows,
                    f" ERROR: {result.error}" if result.error else "")
        results.append(result)
    return results


def validate_all(symbols: list[str], store: ParquetStore) -> list[ValidationReport]:
    """Validate the given stored symbols.

    The trading calendar is always inferred from *every* stored symbol, not just
    the requested ones: a symbol on its own cannot reveal its own gaps, because
    any day it is missing would look like a day nobody traded.
    """
    all_frames = {s: store.load(s) for s in store.symbols()}
    calendar = build_trading_calendar(list(all_frames.values()))
    return [validate(all_frames[s], s, calendar) for s in symbols if s in all_frames]
