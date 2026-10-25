"""Cached access to the existing scanner, strategy output and backtester.

`AltrixService` owns the in-memory caches; it never computes signals itself:

    universe  -> app.scanner_ui.load_universe (NSE list, local snapshot fallback)
    scan      -> src.scanner.run_universe_scan (runs src.strategy.baseline)
    backtest  -> app.dashboard.run_dashboard_backtest (runs src.backtest.run_backtest)
    download  -> app.scanner_ui.refresh_market_data (the incremental downloader)

The scan and the loaded market data are cached under the data fingerprint
`app.dashboard.data_version` (file count, newest mtime), so a download - from
the API, the CLI or the Streamlit app - invalidates them automatically, and
nothing is recomputed on every request.
"""

from __future__ import annotations

import logging
import math
import os
import threading
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from app import dashboard as dash
from app import scanner_ui as ui
from src.backtest import BacktestResult
from src.data import ParquetStore
from src.scanner import BUY, HOLD, INSUFFICIENT_DATA, SELL, ScanResult, recent_crossovers, run_universe_scan
from src.strategy.baseline import LONG_WINDOW, SHORT_WINDOW

logger = logging.getLogger("altrix.api")

STRATEGY = {
    "name": dash.STRATEGY_NAME,
    "short_window": SHORT_WINDOW,
    "long_window": LONG_WINDOW,
    "buy_rule": "SMA20 crosses above SMA50: previous SMA20 <= SMA50 and current SMA20 > SMA50",
    "sell_rule": "SMA20 crosses below SMA50: previous SMA20 >= SMA50 and current SMA20 < SMA50",
}
DATA_SOURCE = {
    "provider": "Yahoo Finance (yfinance), stored locally as Parquet",
    "frequency": "daily",
    "real_time": False,
    "universe": ui.UNIVERSE_NAME,
    "notes": [
        "End-of-day data, not real-time.",
        "A signal dated D uses D's close; the backtester acts on it at the next trading day's open.",
        "Prices are split-adjusted, not dividend-adjusted.",
        "The universe is today's NIFTY 100, so history has survivorship bias.",
    ],
}
BACKTEST_CACHE_SIZE = 8


class NotFoundError(Exception):
    """A requested symbol is not part of the scanned universe."""


class DataUnavailableError(Exception):
    """The universe or the stored market data could not be loaded."""


def offline_mode() -> bool:
    return os.environ.get("ALTRIX_OFFLINE") == "1"


def downloads_enabled() -> bool:
    """False on read-only deployments (ALTRIX_DISABLE_DOWNLOAD=1), where new data arrives by redeploying."""
    return os.environ.get("ALTRIX_DISABLE_DOWNLOAD") != "1"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def iso_date(value) -> str | None:
    if value is None or (not isinstance(value, str) and pd.isna(value)):
        return None
    return pd.Timestamp(value).date().isoformat()


def num(value) -> float | None:
    """JSON-safe float: NaN/inf/None -> None."""
    if value is None or pd.isna(value):
        return None
    f = float(value)
    return f if math.isfinite(f) else None


def safe_reason(reason: str) -> str:
    """Failure reasons without local filesystem paths or raw exception text."""
    if reason.startswith("could not read stored data"):
        return "could not read stored data"
    return reason


@dataclass
class RefreshJob:
    state: str = "idle"  # idle | running | succeeded | failed
    kind: str | None = None  # rescan | download
    started_at: str | None = None
    finished_at: str | None = None
    message: str | None = None
    updated: int | None = None
    up_to_date: int | None = None
    new_rows: int | None = None
    failed: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict:
        d = {k: v for k, v in self.__dict__.items() if k != "failed"}
        d["failed"] = [{"symbol": s, "reason": safe_reason(r or "")} for s, r in self.failed.items()]
        return d


@dataclass
class CachedScan:
    key: tuple
    result: ScanResult
    scanned_at: str
    previous: pd.DataFrame  # symbol -> previous stored bar (close, date)


class AltrixService:
    def __init__(
        self,
        data_dir: Path | None = None,
        universe_loader: Callable[[], list[dict]] = ui.load_universe,
        refresher: Callable[[list[str], ParquetStore], list] = ui.refresh_market_data,
    ):
        self.data_dir = Path(data_dir) if data_dir is not None else dash.processed_dir()
        self._load_universe = universe_loader
        self._refresher = refresher
        self._universe: list[dict] | None = None
        self._scan: CachedScan | None = None
        self._market: tuple[tuple, pd.DataFrame] | None = None
        self._backtests: OrderedDict[tuple, BacktestResult] = OrderedDict()
        self._lock = threading.RLock()  # guards universe + scan
        self._bt_lock = threading.Lock()  # guards market data + backtest cache
        self.job = RefreshJob()

    # ---- inputs -----------------------------------------------------------------------

    def version(self) -> tuple[int, float]:
        return dash.data_version(self.data_dir)

    def universe(self) -> list[dict]:
        with self._lock:
            if self._universe is None:
                try:
                    self._universe = self._load_universe()
                except Exception as exc:
                    logger.exception("Universe unavailable")
                    raise DataUnavailableError(
                        "Could not load the NIFTY 100 constituent list (NSE unreachable and no local "
                        "snapshot). Run `python scripts/download_data.py` once to create it."
                    ) from exc
            return self._universe

    # ---- scan -----------------------------------------------------------------------------

    def scan(self, force: bool = False) -> CachedScan:
        """The latest scan, recomputed only when the stored data or universe changed."""
        with self._lock:
            universe = self.universe()
            key = (self.version(), tuple(u["symbol"] for u in universe))
            if force or self._scan is None or self._scan.key != key:
                logger.info("Scanning %d symbols", len(universe))
                result = run_universe_scan(universe, ParquetStore(self.data_dir))
                self._scan = CachedScan(key, result, utc_now(), _previous_bars(result.strategy_frame))
            return self._scan

    def scan_cached(self) -> CachedScan | None:
        return self._scan

    def stock_record(self, cached: CachedScan, row: pd.Series) -> dict:
        prev = cached.previous.loc[row["symbol"]] if row["symbol"] in cached.previous.index else None
        prev_close = None if prev is None else num(prev["close"])
        close = num(row["close"])
        change = (close / prev_close - 1) * 100 if close is not None and prev_close else None
        return {
            "symbol": row["symbol"],
            "name": row["name"] or None,
            "date": iso_date(row["date"]),
            "close": close,
            "previous_close": prev_close,
            "previous_date": None if prev is None else iso_date(prev["date"]),
            "daily_change_pct": change,
            "sma20": num(row["sma20"]),
            "sma50": num(row["sma50"]),
            "sma_difference": num(row["sma_difference"]),
            "signal": row["signal"],
            "signal_date": iso_date(row["signal_date"]),
            "last_crossover": row["last_crossover"] or None,
            "last_crossover_date": iso_date(row["last_crossover_date"]),
            "note": row["note"] or None,
        }

    def scanner(self, force: bool = False) -> dict:
        cached = self.scan(force)
        r = cached.result
        counts = r.counts() if not r.table.empty else {s: 0 for s in (BUY, SELL, HOLD, INSUFFICIENT_DATA)}
        return {
            "data_as_of": iso_date(r.as_of),
            "scanned_at": cached.scanned_at,
            "is_stale": ui.is_stale(r.as_of),
            "universe": ui.UNIVERSE_NAME,
            "universe_size": r.universe_size,
            "scanned_count": len(r.table),
            "buy_count": counts[BUY],
            "sell_count": counts[SELL],
            "hold_count": counts[HOLD],
            "insufficient_count": counts[INSUFFICIENT_DATA],
            "failed_symbols": [{"symbol": s, "reason": safe_reason(why)} for s, why in r.failed.items()],
            "strategy": STRATEGY,
            "data_source": DATA_SOURCE,
            "stocks": [self.stock_record(cached, row) for _, row in r.table.iterrows()],
        }

    def history(self, symbol: str, start: pd.Timestamp | None = None, end: pd.Timestamp | None = None) -> dict:
        cached = self.scan()
        r = cached.result
        table = r.table.set_index("symbol", drop=False)
        if symbol not in table.index:
            if symbol in r.failed:
                raise NotFoundError(f"{symbol} could not be scanned: {safe_reason(r.failed[symbol])}")
            raise NotFoundError(f"{symbol} is not in the {ui.UNIVERSE_NAME} universe")

        sf = r.strategy_frame
        s = sf[sf["symbol"] == symbol].sort_values("date")
        total = len(s)
        if start is not None:
            s = s[s["date"] >= start]
        if end is not None:
            s = s[s["date"] <= end]

        points = [_point(row) for row in s.itertuples(index=False)]
        row = table.loc[symbol]
        return {
            "symbol": symbol,
            "name": row["name"] or None,
            "data_as_of": iso_date(r.as_of),
            "start": points[0]["date"] if points else None,
            "end": points[-1]["date"] if points else None,
            "total_bars": total,
            "stock": self.stock_record(cached, row),
            "crossovers": [p for p in points if p["signal"]],
            "points": points,
        }

    def recent_signals(self, trading_days: int) -> dict:
        cached = self.scan()
        r = cached.result
        names = dict(zip(r.table["symbol"], r.table["name"]))
        sf = r.strategy_frame
        if sf.empty:
            return {"data_as_of": None, "trading_days": trading_days, "crossovers": [], "daily_counts": []}

        recent = recent_crossovers(sf, trading_days=trading_days)
        dates = sf["date"].drop_duplicates().nlargest(trading_days)
        window = sf[sf["date"].isin(dates)]
        daily = window.groupby("date")[["buy_signal", "sell_signal"]].sum().sort_index()
        return {
            "data_as_of": iso_date(r.as_of),
            "trading_days": trading_days,
            "crossovers": [{
                "date": iso_date(c["date"]), "symbol": c["symbol"], "name": names.get(c["symbol"]) or None,
                "signal": c["signal"], "close": num(c["close"]), "sma20": num(c["sma20"]), "sma50": num(c["sma50"]),
            } for _, c in recent.iterrows()],
            "daily_counts": [{"date": iso_date(d), "buy": int(v["buy_signal"]), "sell": int(v["sell_signal"])}
                             for d, v in daily.iterrows()],
        }

    # ---- backtest ---------------------------------------------------------------------------

    def market_data(self) -> pd.DataFrame:
        """All stored symbols cleaned with load_clean, as the Streamlit Backtest page uses."""
        with self._bt_lock:
            version = self.version()
            if self._market is None or self._market[0] != version:
                try:
                    self._market = (version, dash.load_market_data(self.data_dir))
                except dash.DataNotFoundError as exc:
                    raise DataUnavailableError(
                        "No processed market data found. Download it first with: python scripts/download_data.py"
                    ) from exc
                self._backtests.clear()
            return self._market[1]

    def backtest(self, settings: dash.BacktestSettings) -> tuple[BacktestResult, pd.DataFrame]:
        """Run (or reuse) the existing backtester. Raises ValueError for invalid settings."""
        data = self.market_data()
        key = (self.version(), settings)
        with self._bt_lock:
            if key in self._backtests:
                self._backtests.move_to_end(key)
                return self._backtests[key], data
        result = dash.run_dashboard_backtest(data, settings)
        with self._bt_lock:
            self._backtests[key] = result
            while len(self._backtests) > BACKTEST_CACHE_SIZE:
                self._backtests.popitem(last=False)
        return result, data

    # ---- refresh ----------------------------------------------------------------------------

    def rescan(self) -> dict:
        """Re-read the stored data and recompute the scan now (no download)."""
        self.job = RefreshJob("running", "rescan", utc_now())
        try:
            self.scan(force=True)
        except Exception as exc:
            self.job = RefreshJob("failed", "rescan", self.job.started_at, utc_now(), "Rescan failed")
            raise exc
        self.job = RefreshJob("succeeded", "rescan", self.job.started_at, utc_now(), "Rescanned stored data")
        return self.job.to_dict()

    def start_download(self) -> tuple[dict, bool]:
        """Start the incremental downloader in a background thread. Returns (status, started)."""
        with self._lock:
            if self.job.state == "running":
                return self.job.to_dict(), False
            self.job = RefreshJob("running", "download", utc_now(),
                                  message="Fetching new daily bars from Yahoo Finance")
        threading.Thread(target=self._download, name="altrix-download", daemon=True).start()
        return self.job.to_dict(), True

    def _download(self) -> None:
        started = self.job.started_at
        try:
            with self._lock:
                self._universe = None  # re-read the constituent list too
            symbols = [u["symbol"] for u in self.universe()]
            results = self._refresher(symbols, ParquetStore(self.data_dir))
            summary = ui.refresh_summary(results)
            self.scan(force=True)
            failed = summary["failed"]
            self.job = RefreshJob(
                "succeeded", "download", started, utc_now(),
                f"{summary['updated']} stocks received new bars (+{summary['new_rows']} rows), "
                f"{summary['up_to_date']} already up to date" + (f", {len(failed)} failed" if failed else ""),
                summary["updated"], summary["up_to_date"], summary["new_rows"], failed,
            )
        except Exception:
            logger.exception("Download failed")
            self.job = RefreshJob("failed", "download", started, utc_now(),
                                  "Download failed; the data already stored is unchanged")

    # ---- health -----------------------------------------------------------------------------

    def health(self) -> dict:
        count, mtime = self.version()
        cached = self._scan
        return {
            "status": "ok" if count else "degraded",
            "data_available": count > 0,
            "stored_symbols": count,
            "data_updated_at": (datetime.fromtimestamp(mtime, timezone.utc).isoformat(timespec="seconds")
                                if count else None),
            "scan_cached": cached is not None,
            "data_as_of": None if cached is None else iso_date(cached.result.as_of),
            "offline_mode": offline_mode(),
            "downloads_enabled": downloads_enabled(),
            "refresh": self.job.to_dict(),
        }


def _previous_bars(strategy_frame: pd.DataFrame) -> pd.DataFrame:
    """Each symbol's second-to-last stored bar (close, date), indexed by symbol."""
    if strategy_frame.empty:
        return pd.DataFrame(columns=["close", "date"])
    sf = strategy_frame.sort_values(["symbol", "date"])
    prev = sf.groupby("symbol").nth(-2)
    return prev.set_index("symbol")[["close", "date"]]


def _point(row) -> dict:
    signal = BUY if row.buy_signal else SELL if row.sell_signal else None
    return {
        "date": iso_date(row.date),
        "open": num(row.open),
        "high": num(row.high),
        "low": num(row.low),
        "close": num(row.close),
        "volume": None if pd.isna(row.volume) else int(row.volume),
        "sma20": num(row.sma20),
        "sma50": num(row.sma50),
        "signal": signal,
    }
