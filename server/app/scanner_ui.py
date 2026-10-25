"""Data shaping for the Opportunity Scanner page: no Streamlit imports, no signal logic.

Signals come from `src.scanner` (which reuses `src.strategy.baseline`). These
helpers only load inputs, select/rename columns and build charts.
"""

from __future__ import annotations

import os
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go

from app import dashboard as dash
from src.data import (
    DownloadResult,
    MarketDataProvider,
    Nifty100Universe,
    ParquetStore,
    YahooFinanceProvider,
    download_all,
    parse_nse_index_csv,
)
from src.data.downloader import default_end, default_start
from src.data.universe import UniverseError
from src.scanner import INSUFFICIENT_DATA, ScanResult

UNIVERSE_NAME = "NIFTY 100"
SNAPSHOT_NAME = "nifty100_constituents.csv"
CHART_MONTHS = 6

SIGNAL_LABELS = {
    "BUY": "BUY",
    "SELL": "SELL",
    "HOLD": "HOLD",
    INSUFFICIENT_DATA: "Insufficient historical data",
}

DISPLAY_COLUMNS = {
    "symbol": "Symbol",
    "name": "Company",
    "date": "Date",
    "close": "Close",
    "sma20": "SMA 20",
    "sma50": "SMA 50",
    "sma_difference": "SMA20 − SMA50",
    "signal": "Signal",
    "signal_date": "Signal Date",
    "last_crossover": "Last Crossover",
    "last_crossover_date": "Last Crossover Date",
    "note": "Note",
}
SIGNAL_TABLE_FIELDS = ["symbol", "name", "close", "sma20", "sma50", "signal", "signal_date"]
ALL_STOCKS_FIELDS = ["symbol", "name", "date", "close", "sma20", "sma50", "sma_difference",
                     "signal", "signal_date", "last_crossover", "last_crossover_date", "note"]


def raw_dir() -> Path:
    """Where the universe snapshot lives (override with ALTRIX_RAW_DIR)."""
    return Path(os.environ.get("ALTRIX_RAW_DIR", dash.ROOT / "data" / "raw"))


def deliverables_dir() -> Path:
    """Where optional NSE deliverable data lives (override with ALTRIX_DELIVERABLES_DIR)."""
    return Path(os.environ.get("ALTRIX_DELIVERABLES_DIR", dash.ROOT / "data" / "deliverables"))


def load_universe() -> list[dict]:
    """Current NIFTY 100 constituents via the existing universe module.

    Uses NSE's official list (falling back to the local snapshot if NSE is
    unreachable). With ALTRIX_OFFLINE=1 only the local snapshot is read.
    """
    snapshot = raw_dir() / SNAPSHOT_NAME
    if os.environ.get("ALTRIX_OFFLINE") == "1":
        if not snapshot.exists():
            raise UniverseError(f"no universe snapshot at {snapshot}; run scripts/download_data.py")
        return parse_nse_index_csv(snapshot.read_text(encoding="utf-8"))
    return Nifty100Universe(cache_path=snapshot).get_constituents()


def refresh_market_data(
    symbols: list[str],
    store: ParquetStore,
    provider: MarketDataProvider | None = None,
) -> list[DownloadResult]:
    """Fetch only bars newer than what is stored, via the existing downloader.

    Same as `python scripts/download_data.py`: incremental, appends new bars,
    never rewrites history, one failing symbol does not stop the rest.
    """
    provider = provider or YahooFinanceProvider()
    return download_all(symbols, provider, store, default_start(), default_end())


def refresh_summary(results: list[DownloadResult]) -> dict:
    return {
        "updated": sum(r.status in ("downloaded", "updated") for r in results),
        "up_to_date": sum(r.status == "up_to_date" for r in results),
        "new_rows": sum(r.new_rows for r in results),
        "failed": {r.symbol: r.error for r in results if r.status == "failed"},
    }


def format_date(value) -> str:
    """'05 Oct 2026', or '—' when there is no date."""
    if value is None or pd.isna(value):
        return "—"
    return f"{pd.Timestamp(value):%d %b %Y}"


def is_stale(as_of: pd.Timestamp | None, today: pd.Timestamp | None = None, max_weekdays: int = 2) -> bool:
    """True if more than `max_weekdays` weekdays have passed since the data's last date."""
    if as_of is None:
        return False
    today = pd.Timestamp.now(tz="Asia/Kolkata").tz_localize(None).normalize() if today is None else today
    missed = pd.bdate_range(as_of + pd.Timedelta(days=1), today - pd.Timedelta(days=1))
    return len(missed) > max_weekdays


def display_table(table: pd.DataFrame, fields: list[str]) -> pd.DataFrame:
    """Selected scan columns with display names. Values unchanged except signal labels."""
    out = table[fields].copy()
    if "signal" in out:
        out["signal"] = out["signal"].map(SIGNAL_LABELS).fillna(out["signal"])
    return out.rename(columns=DISPLAY_COLUMNS).reset_index(drop=True)


def stock_details(result: ScanResult, symbol: str) -> pd.Series:
    return result.table.set_index("symbol").loc[symbol]


def stock_options(result: ScanResult) -> list[str]:
    """BUY stocks first, then SELL, then the rest (the scan table's order)."""
    return result.table["symbol"].tolist()


def stock_chart(result: ScanResult, symbol: str, months: int = CHART_MONTHS) -> go.Figure:
    """Close, SMA20, SMA50 for the last `months` months, with the strategy's crossovers."""
    sf = result.strategy_frame
    s = sf[sf["symbol"] == symbol].sort_values("date")
    s = s[s["date"] > s["date"].max() - pd.DateOffset(months=months)]

    fig = go.Figure()
    for col, name, color, width in (("close", "Close", dash.PRICE_COLOR, 1.8),
                                    ("sma20", "SMA20", dash.SMA20_COLOR, 1.4),
                                    ("sma50", "SMA50", dash.SMA50_COLOR, 1.4)):
        fig.add_trace(go.Scatter(x=s["date"], y=s[col], mode="lines", name=name,
                                 line=dict(color=color, width=width),
                                 hovertemplate="₹%{y:,.2f}<extra>" + name + "</extra>"))
    for flag, name, shape, color in (("buy_signal", "BUY crossover", "triangle-up", dash.WIN_COLOR),
                                     ("sell_signal", "SELL crossover", "triangle-down", dash.LOSS_COLOR)):
        pts = s[s[flag]]
        if not pts.empty:
            fig.add_trace(go.Scatter(
                x=pts["date"], y=pts["close"], mode="markers", name=name,
                marker=dict(symbol=shape, size=13, color=color),
                hovertemplate=f"<b>{name}</b> %{{x|%d %b %Y}}<br>close ₹%{{y:,.2f}}<extra></extra>",
            ))
    fig.update_yaxes(tickprefix="₹", tickformat=",.0f")
    fig.update_layout(height=420, margin=dict(l=10, r=10, t=30, b=10), hovermode="x unified",
                      legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0))
    return fig

