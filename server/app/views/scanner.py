"""Opportunity Scanner page: which NIFTY 100 stocks have a baseline signal on the latest day?

Opened from the app's navigation (app/streamlit_app.py). It can also run on its own:

    streamlit run app/views/scanner.py

Display only: the universe comes from src.data.universe, prices from the local
store, and signals from src.scanner (which runs src.strategy.baseline).
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app import dashboard as dash  # noqa: E402
from app import scanner_ui as ui  # noqa: E402
from src.data import ParquetStore  # noqa: E402
from src.scanner import BUY, HOLD, INSUFFICIENT_DATA, SELL, ScanResult, recent_crossovers, run_universe_scan  # noqa: E402

logger = logging.getLogger("altrix.scanner")

PRICE = st.column_config.NumberColumn(format="₹ %,.2f")
DIFF = st.column_config.NumberColumn(format="₹ %,.2f", help="EMA20 minus EMA50")
DATE = st.column_config.DateColumn(format="DD MMM YYYY")
COLUMN_CONFIG = {
    "Close": PRICE, "EMA 20": PRICE, "EMA 50": PRICE, "EMA20 − EMA50": DIFF,
    "Date": DATE, "Signal Date": DATE, "Last Crossover Date": DATE,
}


@st.cache_resource(show_spinner="Loading NIFTY 100 constituents…")
def get_universe(raw_dir: str, refresh_token: int) -> list[dict]:
    """Fetched once per server run (or per Refresh Data click); `raw_dir` keys the snapshot location."""
    return ui.load_universe()


@st.cache_resource(show_spinner="Scanning NIFTY 100…")
def get_scan(directory: str, version: tuple[int, float], symbols: tuple[str, ...],
             _universe: list[dict]) -> ScanResult:
    """Re-runs only when the stored data or universe changes, not on every click."""
    return run_universe_scan(_universe, ParquetStore(Path(directory)))


def metric_row(items: list[tuple[str, str, str | None]], widths: list[float] | None = None) -> None:
    for col, (label, value, help_) in zip(st.columns(widths or len(items)), items):
        col.metric(label, value, help=help_, border=True)


def signal_table(df: pd.DataFrame, fields: list[str]) -> None:
    st.dataframe(ui.display_table(df, fields), column_config=COLUMN_CONFIG, hide_index=True)


# ---- Header -------------------------------------------------------------------------------
head, button = st.columns([5, 1], vertical_alignment="bottom")
with head:
    st.title("Altrix")
    st.markdown("**NIFTY 100 Opportunity Scanner**")
with button:
    refresh_clicked = st.button("Refresh Data", width="stretch",
                                help="Download only new daily bars (if any) from Yahoo Finance, "
                                     "then re-scan. Nothing is polled automatically.")

data_dir = dash.processed_dir()
token = st.session_state.setdefault("universe_token", 0)

try:
    universe = get_universe(str(ui.raw_dir()), token)
except Exception as exc:
    logger.exception("Universe unavailable")
    st.error("Could not load the NIFTY 100 constituent list (NSE unreachable and no local snapshot). "
             "Run `python scripts/download_data.py` once to create it.")
    with st.expander("Error details"):
        st.exception(exc)
    st.stop()

if refresh_clicked:
    try:
        with st.spinner("Fetching new daily bars from Yahoo Finance… (about a minute)"):
            results = ui.refresh_market_data([u["symbol"] for u in universe], ParquetStore(data_dir))
        st.session_state["refresh_summary"] = ui.refresh_summary(results)
    except Exception as exc:
        logger.exception("Refresh failed")
        st.session_state["refresh_summary"] = {"error": str(exc)}
    st.session_state["universe_token"] = token + 1  # re-read the constituent list too
    get_universe.clear()
    get_scan.clear()
    st.rerun()

try:
    result = get_scan(str(data_dir), dash.data_version(data_dir),
                      tuple(u["symbol"] for u in universe), universe)
except Exception as exc:
    logger.exception("Scan failed")
    st.error("The scan failed unexpectedly.")
    with st.expander("Error details"):
        st.exception(exc)
    st.stop()

summary = st.session_state.pop("refresh_summary", None)
if summary:
    if "error" in summary:
        st.error(f"Refresh failed: {summary['error']}. Showing the data already stored.")
    else:
        msg = (f"Refresh complete: {summary['updated']} stocks received new bars "
               f"(+{summary['new_rows']} rows), {summary['up_to_date']} already up to date.")
        (st.warning if summary["failed"] else st.success)(
            msg + (f" Failed: {', '.join(summary['failed'])}." if summary["failed"] else ""))

if result.as_of is None:
    st.error(f"No usable price data for the NIFTY 100 in {data_dir}. "
             "Download it first with `python scripts/download_data.py`.")
    st.stop()

# ---- Summary -----------------------------------------------------------------------------
metric_row([
    ("Data as of", ui.format_date(result.as_of), "Latest completed trading day in the stored data."),
    ("Universe", ui.UNIVERSE_NAME, f"{len(result.table)} of {result.universe_size} constituents scanned."),
    ("Strategy", dash.STRATEGY_NAME, "EMA20 crossing EMA50, from src/strategy/baseline.py."),
], widths=[1, 1, 1.5])  # wider strategy card so the name is not truncated
st.caption(
    f"End-of-day prices (Yahoo Finance, stored locally); not real-time. Signals dated "
    f"{ui.format_date(result.as_of)} use that day's closing price, so they are known only after the "
    "close. The Altrix backtester would act on them at the next trading day's open. These are "
    "research signals from a simple baseline strategy, not investment advice."
)
if ui.is_stale(result.as_of):
    st.warning(f"The stored data ends on {ui.format_date(result.as_of)}. Click **Refresh Data** to fetch newer bars.")
if result.failed:
    st.warning(f"{len(result.failed)} symbol(s) could not be scanned: "
               + "; ".join(f"{s} ({why})" for s, why in result.failed.items()))

counts = result.counts()
metric_row([
    ("BUY signals", str(counts[BUY]), None),
    ("SELL signals", str(counts[SELL]), None),
    ("No new signal (HOLD)", str(counts[HOLD]), "No EMA20/EMA50 crossover on the latest day."),
    ("Insufficient history", str(counts[INSUFFICIENT_DATA]), "Fewer than 50 trading days of data."),
])

# ---- Current signals -------------------------------------------------------------------------
as_of_txt = ui.format_date(result.as_of)
st.subheader("Current BUY Signals")
st.caption(f"Stocks meeting the baseline strategy's BUY condition: EMA20 crossed above EMA50 on {as_of_txt}.")
buys = result.with_signal(BUY)
if buys.empty:
    st.info("No new BUY signals detected in the current NIFTY 100 universe.")
else:
    signal_table(buys, ui.SIGNAL_TABLE_FIELDS)

st.subheader("Current SELL Signals")
st.caption(f"Stocks where EMA20 crossed below EMA50 on {as_of_txt}: the strategy's exit condition for existing positions.")
sells = result.with_signal(SELL)
if sells.empty:
    st.info("No new SELL signals detected in the current NIFTY 100 universe.")
else:
    signal_table(sells, ui.SIGNAL_TABLE_FIELDS)

with st.expander("Recent crossovers (last 10 trading days)"):
    st.caption("Past signals for context. Only signals on the latest trading day are current.")
    recent = recent_crossovers(result.strategy_frame, trading_days=10)
    if recent.empty:
        st.write("No crossovers in the last 10 trading days.")
    else:
        st.dataframe(recent.rename(columns={"date": "Signal Date", "symbol": "Symbol", "signal": "Signal",
                                            "close": "Close", "ema20": "EMA 20", "ema50": "EMA 50"}),
                     column_config=COLUMN_CONFIG, hide_index=True)

with st.expander(f"All {ui.UNIVERSE_NAME} Stocks ({len(result.table)})"):
    st.caption("HOLD means no new crossover on the latest day; EMA20 may be above or below EMA50 "
               "(see EMA20 − EMA50 and Last Crossover). Click a column header to sort.")
    signal_table(result.table, ui.ALL_STOCKS_FIELDS)

# ---- Stock details ---------------------------------------------------------------------------
st.subheader("Stock Details")
options = ui.stock_options(result)
names = dict(zip(result.table["symbol"], result.table["name"]))
symbol = st.selectbox("Select Stock", options, format_func=lambda s: f"{s} · {names.get(s, '')}")
d = ui.stock_details(result, symbol)
metric_row([
    ("Current Price", dash.format_inr(d["close"], 2), f"Close on {ui.format_date(d['date'])}."),
    ("EMA20", dash.format_inr(d["ema20"], 2), None),
    ("EMA50", dash.format_inr(d["ema50"], 2), None),
    ("Current Signal", ui.SIGNAL_LABELS.get(d["signal"], d["signal"]), "Signal on the latest trading day."),
    ("Signal Date", ui.format_date(d["signal_date"]), "Only set when there is a BUY/SELL on the latest day."),
])
last = (f"Last crossover: **{d['last_crossover']}** on {ui.format_date(d['last_crossover_date'])}."
        if d["last_crossover"] else "No crossover in the stored history.")
st.markdown(last + (f"  \n{d['note']}" if d["note"] else ""))
st.plotly_chart(ui.stock_chart(result, symbol), width="stretch")
st.caption(f"Last {ui.CHART_MONTHS} months. Markers show the strategy's crossover days (signal on that "
           "day's close).")
