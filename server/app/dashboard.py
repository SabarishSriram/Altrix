"""Data shaping for the Streamlit dashboard: no Streamlit imports, no trading logic.

Every number shown comes from a `BacktestResult` produced by `src.backtest`.
These functions only select, rename, format and plot it. They never recompute
signals, trades or performance. Keeping them here (rather than in the
Streamlit script) makes them unit-testable.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go

from src.backtest import BacktestResult, run_backtest
from src.data import ParquetStore, load_clean
from src.strategy import generate_baseline_signals, generate_smart_money_signals

ROOT = Path(__file__).resolve().parents[1]
STRATEGY_NAME = "20 / 50 EMA Crossover"
BASELINE = "baseline"
SMART_MONEY = "smart_money"
# key -> (display name, signal generator); the generators live in src/strategy.
STRATEGIES = {
    BASELINE: (STRATEGY_NAME, generate_baseline_signals),
    SMART_MONEY: ("20 / 50 EMA + 10-Day Smart Money Confirmation", generate_smart_money_signals),
}

# Muted palette: one accent per meaning, nothing decorative.
EQUITY_COLOR = "#2563eb"
DRAWDOWN_COLOR = "#dc2626"
WIN_COLOR = "#16a34a"
LOSS_COLOR = "#dc2626"
NEUTRAL_COLOR = "#64748b"
PRICE_COLOR = "#334155"
EMA20_COLOR = "#2563eb"
EMA50_COLOR = "#f59e0b"


class DataNotFoundError(Exception):
    """No processed market data is available to backtest."""


# ---- Formatting ----------------------------------------------------------------

def format_inr(value: float | None, decimals: int = 0) -> str:
    """Rupees with Indian digit grouping: 351595.2 -> '₹3,51,595'."""
    if value is None or pd.isna(value):
        return "n/a"
    sign = "-" if value < 0 else ""
    whole, _, frac = f"{abs(value):.{decimals}f}".partition(".")
    if len(whole) > 3:
        head, tail = whole[:-3], whole[-3:]
        groups = []
        while len(head) > 2:
            groups.insert(0, head[-2:])
            head = head[:-2]
        if head:
            groups.insert(0, head)
        whole = ",".join(groups) + "," + tail
    return f"{sign}₹{whole}" + (f".{frac}" if frac else "")


def format_pct(value: float | None, signed: bool = True, decimals: int = 2) -> str:
    """Fraction to percent: 0.264 -> '+26.40%'."""
    if value is None or pd.isna(value):
        return "n/a"
    return f"{value:{'+' if signed else ''}.{decimals}%}"


# ---- Data loading and running ----------------------------------------------------

def processed_dir() -> Path:
    """Where processed Parquet files live (override with ALTRIX_DATA_DIR)."""
    return Path(os.environ.get("ALTRIX_DATA_DIR", ROOT / "data" / "processed"))


def data_version(directory: Path) -> tuple[int, float]:
    """Cheap fingerprint (file count, newest mtime) so caches refresh after a download."""
    files = list(Path(directory).glob("*.parquet"))
    return len(files), max((f.stat().st_mtime for f in files), default=0.0)


def load_market_data(directory: Path) -> pd.DataFrame:
    """All stored symbols, cleaned with `load_clean` (holiday/filler bars removed)."""
    directory = Path(directory)
    store = ParquetStore(directory)
    if not store.symbols():
        raise DataNotFoundError(
            f"No processed market data found in {directory}. "
            "Download it first with:  python scripts/download_data.py"
        )
    cleaned = load_clean(store)
    return pd.concat([r.data for r in cleaned.values()], ignore_index=True)


def date_bounds(df: pd.DataFrame) -> tuple[pd.Timestamp, pd.Timestamp]:
    return df["date"].min(), df["date"].max()


@dataclass(frozen=True)
class BacktestSettings:
    initial_capital: float = 100_000.0
    transaction_cost: float = 0.001
    max_position_weight: float = 0.10
    start: pd.Timestamp | None = None
    end: pd.Timestamp | None = None
    strategy: str = BASELINE
    min_position_weight: float = 0.05

    def errors(self) -> list[str]:
        """Human-readable problems with the settings (empty if valid)."""
        problems = []
        if self.initial_capital <= 0:
            problems.append("Initial capital must be greater than zero.")
        if not 0 <= self.transaction_cost < 1:
            problems.append("Transaction cost must be between 0% and 100%.")
        if not 0 < self.max_position_weight <= 1:
            problems.append("Maximum position weight must be above 0% and at most 100%.")
        if not 0 <= self.min_position_weight <= self.max_position_weight:
            problems.append("Minimum position size must be between 0% and the maximum position weight.")
        if self.strategy not in STRATEGIES:
            problems.append(f"Unknown strategy {self.strategy!r}; choose one of {', '.join(STRATEGIES)}.")
        if self.start is not None and self.end is not None and self.start > self.end:
            problems.append(f"Start date {self.start.date()} is after end date {self.end.date()}.")
        return problems


def run_dashboard_backtest(df: pd.DataFrame, settings: BacktestSettings) -> BacktestResult:
    """Run the existing backtester. Raises ValueError for invalid settings/ranges."""
    problems = settings.errors()
    if problems:
        raise ValueError(" ".join(problems))
    return run_backtest(
        df,
        initial_capital=settings.initial_capital,
        transaction_cost=settings.transaction_cost,
        max_position_weight=settings.max_position_weight,
        start=settings.start,
        end=settings.end,
        min_position_weight=settings.min_position_weight,
        strategy=STRATEGIES[settings.strategy][1],
    )


# ---- Metrics ------------------------------------------------------------------------

@dataclass(frozen=True)
class MetricCard:
    label: str
    value: str
    help: str | None = None


def headline_metrics(result: BacktestResult) -> list[MetricCard]:
    m = result.metrics
    return [
        MetricCard("Initial Capital", format_inr(m["initial_capital"])),
        MetricCard("Final Value", format_inr(m["final_equity"]),
                   "Cash + open positions at the last close."),
        MetricCard("Total Return", format_pct(m["total_return"])),
        MetricCard("Max Drawdown", format_pct(m["max_drawdown"]),
                   "Largest fall from a previous equity peak."),
    ]


def trade_metrics(result: BacktestResult) -> list[MetricCard]:
    m = result.metrics
    return [
        MetricCard("Number of Trades", f"{m['completed_trades']:,}", "Completed BUY → SELL round trips."),
        MetricCard("Win Rate", format_pct(m["win_rate"], signed=False, decimals=1)),
        MetricCard("Winning Trades", f"{m['winning_trades']:,}"),
        MetricCard("Losing Trades", f"{m['losing_trades']:,}"),
        MetricCard("Average Trade Return", format_pct(m["avg_trade_return"])),
        MetricCard("CAGR", format_pct(m["cagr"]),
                   "Annualised return. Shown only for periods of at least one year."),
    ]


def portfolio_summary(result: BacktestResult) -> list[MetricCard]:
    last = result.equity_curve.iloc[-1]
    return [
        MetricCard("Final Cash", format_inr(last["cash"])),
        MetricCard("Final Invested Value", format_inr(last["invested_value"]),
                   "Open positions valued at the last close."),
        MetricCard("Final Portfolio Value", format_inr(last["total_equity"])),
    ]


# ---- Tables --------------------------------------------------------------------------

TRADE_COLUMNS = {
    "symbol": "Symbol",
    "entry_date": "Entry Date",
    "entry_price": "Entry Price",
    "exit_date": "Exit Date",
    "exit_price": "Exit Price",
    "quantity": "Quantity",
    "gross_pnl": "Gross P&L",
    "transaction_cost": "Transaction Cost",
    "net_pnl": "Net P&L",
    "return_pct": "Return %",
    "holding_days": "Holding Days",
}

OPEN_POSITION_COLUMNS = {
    "symbol": "Symbol",
    "quantity": "Quantity",
    "entry_date": "Entry Date",
    "entry_price": "Entry Price",
    "last_price": "Current Price",
    "market_value": "Market Value",
    "unrealized_pnl": "Unrealized P&L",
}


def trades_table(result: BacktestResult, symbol: str | None = None) -> pd.DataFrame:
    """Completed trades with display column names. Values are not changed."""
    df = result.trades_frame()
    if symbol is not None:
        df = df[df["symbol"] == symbol]
    return df[list(TRADE_COLUMNS)].rename(columns=TRADE_COLUMNS).reset_index(drop=True)


def open_positions_table(result: BacktestResult) -> pd.DataFrame:
    df = result.open_positions_frame()
    return df[list(OPEN_POSITION_COLUMNS)].rename(columns=OPEN_POSITION_COLUMNS)


def to_csv_bytes(df: pd.DataFrame) -> bytes:
    return df.to_csv(index=False).encode("utf-8")


def trades_csv(result: BacktestResult) -> bytes:
    """Raw trade records (original field names) for download."""
    return to_csv_bytes(result.trades_frame())


def equity_curve_csv(result: BacktestResult) -> bytes:
    return to_csv_bytes(result.equity_curve)


# ---- Portfolio charts --------------------------------------------------------------

def _layout(fig: go.Figure, y_title: str, height: int = 380) -> go.Figure:
    fig.update_layout(
        height=height,
        margin=dict(l=10, r=10, t=30, b=10),
        hovermode="x unified",
        yaxis_title=y_title,
        xaxis_title=None,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
    )
    return fig


def equity_figure(result: BacktestResult) -> go.Figure:
    ec = result.equity_curve
    fig = go.Figure(go.Scatter(
        x=ec["date"], y=ec["total_equity"], mode="lines", name="Portfolio equity",
        line=dict(color=EQUITY_COLOR, width=2),
        customdata=[format_inr(v) for v in ec["total_equity"]],
        hovertemplate="%{customdata}<extra>Equity</extra>",
    ))
    fig.add_hline(y=result.config.initial_capital, line_dash="dot", line_color=NEUTRAL_COLOR,
                  annotation_text="Initial capital", annotation_position="bottom right")
    fig.update_yaxes(tickprefix="₹", tickformat=",.0f")
    return _layout(fig, "Portfolio value")


def drawdown_figure(result: BacktestResult) -> go.Figure:
    ec = result.equity_curve
    fig = go.Figure(go.Scatter(
        x=ec["date"], y=ec["drawdown"], mode="lines", name="Drawdown", fill="tozeroy",
        line=dict(color=DRAWDOWN_COLOR, width=1),
        hovertemplate="%{y:.2%}<extra>Drawdown</extra>",
    ))
    fig.update_yaxes(tickformat=".0%", rangemode="tozero")
    return _layout(fig, "Drawdown from peak", height=260)


def win_loss_figure(result: BacktestResult) -> go.Figure | None:
    """Bar chart of winning vs losing trades; None if there are no trades."""
    m = result.metrics
    if m["completed_trades"] == 0:
        return None
    fig = go.Figure(go.Bar(
        x=["Losing", "Winning"], y=[m["losing_trades"], m["winning_trades"]],
        marker_color=[LOSS_COLOR, WIN_COLOR],
        text=[m["losing_trades"], m["winning_trades"]], textposition="outside",
        hovertemplate="%{x}: %{y} trades<extra></extra>",
    ))
    fig.update_layout(hovermode="closest")
    return _layout(fig, "Trades", height=320)


def return_distribution_figure(result: BacktestResult) -> go.Figure | None:
    """Histogram of per-trade returns; None if there are no trades."""
    if not result.trades:
        return None
    returns = [t.return_pct for t in result.trades]
    fig = go.Figure(go.Histogram(
        x=returns, nbinsx=40, marker_color=NEUTRAL_COLOR, name="Trades",
        hovertemplate="Return %{x:.1%}<br>%{y} trades<extra></extra>",
    ))
    fig.add_vline(x=0, line_color=PRICE_COLOR, line_width=1)
    fig.update_xaxes(tickformat=".0%", title="Trade return (net of costs)")
    fig.update_layout(hovermode="closest", bargap=0.05)
    return _layout(fig, "Number of trades", height=320)


# ---- Single stock ----------------------------------------------------------------

def stock_symbols(result: BacktestResult) -> list[str]:
    if result.strategy_frame is None:
        return []
    return sorted(result.strategy_frame["symbol"].unique())


def default_symbol(symbols: list[str]) -> str | None:
    if not symbols:
        return None
    return "RELIANCE.NS" if "RELIANCE.NS" in symbols else symbols[0]


@dataclass
class StockView:
    symbol: str
    prices: pd.DataFrame  # date, close, ema20, ema50, ... from the strategy frame
    signals: pd.DataFrame  # this stock's signals with status, plus close on signal day
    trades: pd.DataFrame  # display trades table for this stock
    realized_pnl: float
    num_trades: int
    win_rate: float | None


def stock_view(result: BacktestResult, symbol: str) -> StockView:
    sf = result.strategy_frame
    prices = sf[sf["symbol"] == symbol].sort_values("date").reset_index(drop=True)
    sig = result.signals[result.signals["symbol"] == symbol]
    sig = sig.merge(prices[["date", "close"]], left_on="signal_date", right_on="date", how="left")

    stock_trades = [t for t in result.trades if t.symbol == symbol]
    n = len(stock_trades)
    return StockView(
        symbol=symbol,
        prices=prices,
        signals=sig.drop(columns="date").reset_index(drop=True),
        trades=trades_table(result, symbol),
        realized_pnl=sum(t.net_pnl for t in stock_trades),
        num_trades=n,
        win_rate=sum(t.net_pnl > 0 for t in stock_trades) / n if n else None,
    )


def stock_figure(view: StockView) -> go.Figure:
    p = view.prices
    fig = go.Figure()
    for col, name, color, width in (("close", "Close", PRICE_COLOR, 1.5),
                                    ("ema20", "EMA20", EMA20_COLOR, 1.2),
                                    ("ema50", "EMA50", EMA50_COLOR, 1.2)):
        if col not in p.columns:  # a strategy without EMAs still gets a price chart
            continue
        fig.add_trace(go.Scatter(
            x=p["date"], y=p[col], mode="lines", name=name, line=dict(color=color, width=width),
            hovertemplate="₹%{y:,.2f}<extra>" + name + "</extra>",
        ))

    # Signals sit on the signal day's close. Filled = executed next open; hollow = not traded.
    for side, symbol_shape, color in (("BUY", "triangle-up", WIN_COLOR), ("SELL", "triangle-down", LOSS_COLOR)):
        for executed in (True, False):
            s = view.signals[(view.signals["side"] == side) & ((view.signals["status"] == "executed") == executed)]
            if s.empty:
                continue
            fill = "" if executed else "-open"
            fig.add_trace(go.Scatter(
                x=s["signal_date"], y=s["close"], mode="markers",
                name=f"{side} signal" + ("" if executed else " (not traded)"),
                marker=dict(symbol=symbol_shape + fill, size=11, color=color,
                            line=dict(width=1.5, color=color)),
                customdata=s[["status"]].assign(
                    fill=s["execution_price"].map(lambda v: "" if pd.isna(v) else f"filled at ₹{v:,.2f} next open")
                ).to_numpy(),
                hovertemplate=f"<b>{side}</b> %{{x|%d %b %Y}}<br>close ₹%{{y:,.2f}}<br>"
                              "%{customdata[0]} %{customdata[1]}<extra></extra>",
            ))
    fig.update_yaxes(tickprefix="₹", tickformat=",.0f")
    return _layout(fig, "Price", height=460)
