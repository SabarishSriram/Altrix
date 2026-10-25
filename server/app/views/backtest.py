"""Backtest page: runs the existing backtester and displays its BacktestResult.

Opened from the app's navigation (app/streamlit_app.py). It can also run on its own:

    streamlit run app/views/backtest.py

A visualization layer only: no trading logic, signals or performance numbers
are computed here.
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

logger = logging.getLogger("altrix.dashboard")

PRICE_FMT = "₹ %,.2f"
MONEY_FMT = "₹ %,.0f"
TRADE_COLUMN_CONFIG = {
    "Entry Date": st.column_config.DateColumn(format="YYYY-MM-DD"),
    "Exit Date": st.column_config.DateColumn(format="YYYY-MM-DD"),
    "Entry Price": st.column_config.NumberColumn(format=PRICE_FMT),
    "Exit Price": st.column_config.NumberColumn(format=PRICE_FMT),
    "Quantity": st.column_config.NumberColumn(format="%d"),
    "Gross P&L": st.column_config.NumberColumn(format=PRICE_FMT),
    "Transaction Cost": st.column_config.NumberColumn(format=PRICE_FMT),
    "Net P&L": st.column_config.NumberColumn(format=PRICE_FMT),
    "Return %": st.column_config.NumberColumn(format="percent"),
    "Holding Days": st.column_config.NumberColumn(format="%d", help="Trading days held"),
}
POSITION_COLUMN_CONFIG = {
    "Entry Date": st.column_config.DateColumn(format="YYYY-MM-DD"),
    "Quantity": st.column_config.NumberColumn(format="%d"),
    "Entry Price": st.column_config.NumberColumn(format=PRICE_FMT),
    "Current Price": st.column_config.NumberColumn(format=PRICE_FMT, help="Last close in the backtest"),
    "Market Value": st.column_config.NumberColumn(format=MONEY_FMT),
    "Unrealized P&L": st.column_config.NumberColumn(format=PRICE_FMT, help="Net of the BUY cost"),
}


@st.cache_resource(show_spinner="Loading historical data…")
def load_data(directory: str, version: tuple[int, float]) -> pd.DataFrame:
    """Loaded once per data version; `version` changes after a new download."""
    return dash.load_market_data(Path(directory))


def metric_row(cards: list[dash.MetricCard]) -> None:
    for col, card in zip(st.columns(len(cards)), cards):
        col.metric(card.label, card.value, help=card.help, border=True)


# ---- Header --------------------------------------------------------------------------
st.title("Altrix")
st.markdown("**Algorithmic Trading Research** · Historical Backtesting Dashboard")

# ---- Data --------------------------------------------------------------------------------
data_dir = dash.processed_dir()
try:
    data = load_data(str(data_dir), dash.data_version(data_dir))
except dash.DataNotFoundError as exc:
    st.error(str(exc))
    st.stop()
except Exception as exc:  # corrupt files etc.
    logger.exception("Failed to load market data")
    st.error(f"Could not load the historical data in {data_dir}.")
    with st.expander("Error details"):
        st.exception(exc)
    st.stop()

data_start, data_end = dash.date_bounds(data)

# ---- Sidebar ----------------------------------------------------------------------------
with st.sidebar:
    st.header("Backtest settings")
    st.selectbox("Strategy", [dash.STRATEGY_NAME], disabled=True,
                 help="Only one strategy is available in this version.")
    capital = st.number_input("Initial capital (₹)", min_value=1_000, value=100_000, step=10_000, format="%d")
    cost_pct = st.number_input("Transaction cost (%)", min_value=0.0, max_value=5.0, value=0.10,
                               step=0.05, format="%.2f", help="Charged on every BUY and every SELL.")
    weight_pct = st.number_input("Maximum position weight (%)", min_value=1.0, max_value=100.0,
                                 value=10.0, step=1.0, format="%.0f",
                                 help="Largest share of portfolio equity a new position may use.")
    start = st.date_input("Start date", value=data_start.date(),
                          min_value=data_start.date(), max_value=data_end.date())
    end = st.date_input("End date", value=data_end.date(),
                        min_value=data_start.date(), max_value=data_end.date())
    run_clicked = st.button("Run Backtest", type="primary", width="stretch")
    st.caption(f"{data['symbol'].nunique()} stocks · data {data_start.date()} → {data_end.date()}. "
               "Signals use the stock's history before the start date to warm up the EMAs.")

settings = dash.BacktestSettings(
    initial_capital=float(capital),
    transaction_cost=cost_pct / 100,
    max_position_weight=weight_pct / 100,
    start=pd.Timestamp(start),
    end=pd.Timestamp(end),
)

if run_clicked:
    problems = settings.errors()
    if problems:
        for p in problems:
            st.error(p)
    else:
        try:
            with st.spinner("Running backtest…"):
                st.session_state["result"] = dash.run_dashboard_backtest(data, settings)
                st.session_state["settings"] = settings
        except ValueError as exc:  # e.g. no trading days in the selected range
            st.error(f"Cannot run this backtest: {exc}")
        except Exception as exc:
            logger.exception("Backtest failed")
            st.error("The backtest failed unexpectedly. The settings were not applied.")
            with st.expander("Error details"):
                st.exception(exc)

result = st.session_state.get("result")
if result is None:
    st.info("Run a backtest to view results.")
    st.stop()

ran_with: dash.BacktestSettings = st.session_state["settings"]
if ran_with != settings:
    st.warning("Settings have changed since this backtest. Click **Run Backtest** to update the results.")

m = result.metrics
st.caption(
    f"{dash.STRATEGY_NAME} · {m['start_date']} → {m['end_date']} ({m['trading_days']:,} trading days) · "
    f"{len(dash.stock_symbols(result))} stocks · cost {ran_with.transaction_cost:.2%} per trade · "
    f"max {ran_with.max_position_weight:.0%} per position"
)

# ---- Performance ---------------------------------------------------------------------------
st.subheader("Performance")
metric_row(dash.headline_metrics(result))
trade_cards = dash.trade_metrics(result)
metric_row(trade_cards[:3])  # two rows of three: six cards in one row truncate labels
metric_row(trade_cards[3:])
if m["completed_trades"] == 0:
    st.info("No completed trades during this period.")

st.subheader("Portfolio Equity Over Time")
st.plotly_chart(dash.equity_figure(result), width="stretch")

st.subheader("Drawdown")
st.plotly_chart(dash.drawdown_figure(result), width="stretch")

# ---- Trades -------------------------------------------------------------------------------
st.subheader("Trade Analysis")
if m["completed_trades"] == 0:
    st.info("No completed trades during this period.")
else:
    left, right = st.columns(2)
    with left:
        st.markdown("**Winning vs losing trades**")
        st.plotly_chart(dash.win_loss_figure(result), width="stretch")
    with right:
        st.markdown("**Distribution of trade returns**")
        st.plotly_chart(dash.return_distribution_figure(result), width="stretch")
    st.markdown(f"**All completed trades** ({m['completed_trades']:,}). Click a column header to sort.")
    st.dataframe(dash.trades_table(result), column_config=TRADE_COLUMN_CONFIG, hide_index=True)

# ---- Single stock ---------------------------------------------------------------------------
st.subheader("Stock Analysis")
symbols = dash.stock_symbols(result)
symbol = st.selectbox("Select Stock", symbols, index=symbols.index(dash.default_symbol(symbols)))
view = dash.stock_view(result, symbol)
metric_row([
    dash.MetricCard("Trades", f"{view.num_trades}"),
    dash.MetricCard("Win Rate", dash.format_pct(view.win_rate, signed=False, decimals=1)),
    dash.MetricCard("Realized P&L", dash.format_inr(view.realized_pnl), "Sum of net P&L of completed trades."),
    dash.MetricCard("Signals", f"{len(view.signals)}", "BUY/SELL signals in the backtest period."),
])
st.plotly_chart(dash.stock_figure(view), width="stretch")
st.caption("Markers sit on the signal day's close. Filled markers were executed at the next trading "
           "day's open; hollow markers were not traded (hover for the reason).")
if view.num_trades:
    st.dataframe(view.trades, column_config=TRADE_COLUMN_CONFIG, hide_index=True)
else:
    st.info(f"No completed trades for {symbol} during this period.")

# ---- Portfolio state -----------------------------------------------------------------------
st.subheader("Portfolio Summary")
metric_row(dash.portfolio_summary(result))
st.markdown(f"**Open positions at {m['end_date']}** ({len(result.open_positions)})")
if result.open_positions:
    st.dataframe(dash.open_positions_table(result), column_config=POSITION_COLUMN_CONFIG, hide_index=True)
else:
    st.caption("No open positions. Everything is in cash.")

# ---- Downloads -------------------------------------------------------------------------------
st.subheader("Download Results")
c1, c2, _ = st.columns([1, 1, 2])
c1.download_button("Trades CSV", dash.trades_csv(result), file_name="altrix_trades.csv",
                   mime="text/csv", width="stretch")
c2.download_button("Equity Curve CSV", dash.equity_curve_csv(result), file_name="altrix_equity_curve.csv",
                   mime="text/csv", width="stretch")
