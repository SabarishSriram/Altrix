import io

import numpy as np
import pandas as pd
import pytest

from app import dashboard as dash
from src.backtest import run_backtest, run_backtest_on_signals
from src.data import ParquetStore

from ..conftest import make_bars


def write_market(directory, symbols=("AAA.NS", "BBB.NS", "CCC.NS"), days=300, seed=1):
    """A small synthetic processed-data folder with trending random walks."""
    rng = np.random.default_rng(seed)
    store = ParquetStore(directory)
    for sym in symbols:
        df = make_bars(sym, start="2023-01-02", days=days)
        walk = 100 * np.exp(np.cumsum(rng.normal(0.0005, 0.02, len(df))))
        store.save(sym, df.assign(open=walk * 0.995, high=walk * 1.03, low=walk * 0.97, close=walk))
    return directory


@pytest.fixture
def market_dir(tmp_path):
    return write_market(tmp_path / "processed")


@pytest.fixture
def data(market_dir):
    return dash.load_market_data(market_dir)


@pytest.fixture
def result(data):
    return dash.run_dashboard_backtest(data, dash.BacktestSettings())


def flat_result():
    """The real strategy on flat prices: EMA20 == EMA50 forever, so no crossover, no trades."""
    df = make_bars("FLAT.NS", days=80).assign(open=100.0, high=100.0, low=100.0, close=100.0)
    return run_backtest(df)


def test_stock_chart_without_ema_columns():
    df = make_bars("X.NS", days=10).assign(buy_signal=False, sell_signal=False)
    fig = dash.stock_figure(dash.stock_view(run_backtest_on_signals(df), "X.NS"))
    assert [t.name for t in fig.data] == ["Close"]


# 1. Runs with defaults ----------------------------------------------------------------

def test_runs_existing_backtester_with_defaults(data, result):
    expected = run_backtest(data)  # the backtester called directly, default parameters
    assert result.metrics == expected.metrics
    pd.testing.assert_frame_equal(result.equity_curve, expected.equity_curve)
    assert result.config.initial_capital == 100_000
    assert result.config.transaction_cost == 0.001 and result.config.max_position_weight == 0.10
    assert result.metrics["completed_trades"] > 0


def test_date_range_is_passed_to_backtester(data):
    s = dash.BacktestSettings(start=pd.Timestamp("2023-06-01"), end=pd.Timestamp("2023-12-29"))
    r = dash.run_dashboard_backtest(data, s)
    assert r.equity_curve["date"].min() >= s.start and r.equity_curve["date"].max() <= s.end


def test_invalid_settings_rejected(data):
    bad = dash.BacktestSettings(start=pd.Timestamp("2024-01-01"), end=pd.Timestamp("2023-01-01"))
    assert bad.errors()
    with pytest.raises(ValueError, match="after end date"):
        dash.run_dashboard_backtest(data, bad)
    assert dash.BacktestSettings(max_position_weight=0).errors()
    assert dash.BacktestSettings().errors() == []


def test_missing_data_raises_clear_error(tmp_path):
    with pytest.raises(dash.DataNotFoundError, match="download_data.py"):
        dash.load_market_data(tmp_path / "empty")


# 2. Metrics correspond to the result -----------------------------------------------------

def test_metric_cards_come_from_result(result):
    m = result.metrics
    cards = {c.label: c.value for c in dash.headline_metrics(result) + dash.trade_metrics(result)}
    assert cards["Initial Capital"] == dash.format_inr(m["initial_capital"])
    assert cards["Final Value"] == dash.format_inr(m["final_equity"])
    assert cards["Total Return"] == dash.format_pct(m["total_return"])
    assert cards["Max Drawdown"] == dash.format_pct(m["max_drawdown"])
    assert cards["Number of Trades"] == str(m["completed_trades"])
    assert cards["Winning Trades"] == str(m["winning_trades"])
    assert cards["Losing Trades"] == str(m["losing_trades"])
    assert cards["Win Rate"] == dash.format_pct(m["win_rate"], signed=False, decimals=1)
    assert cards["Average Trade Return"] == dash.format_pct(m["avg_trade_return"])
    assert cards["CAGR"] == dash.format_pct(m["cagr"])


def test_portfolio_summary_is_last_equity_row(result):
    last = result.equity_curve.iloc[-1]
    cards = {c.label: c.value for c in dash.portfolio_summary(result)}
    assert cards["Final Cash"] == dash.format_inr(last["cash"])
    assert cards["Final Invested Value"] == dash.format_inr(last["invested_value"])
    assert cards["Final Portfolio Value"] == dash.format_inr(result.metrics["final_equity"])


# 3. Trade table corresponds to trades ----------------------------------------------------------

def test_trades_table_matches_trades_exactly(result):
    table = dash.trades_table(result)
    raw = result.trades_frame()
    assert list(table.columns) == list(dash.TRADE_COLUMNS.values())
    assert len(table) == len(result.trades)
    for raw_col, label in dash.TRADE_COLUMNS.items():
        assert table[label].tolist() == raw[raw_col].tolist()  # renamed, never altered


def test_open_positions_table_uses_result(result):
    table = dash.open_positions_table(result)
    assert len(table) == len(result.open_positions)
    for p, (_, row) in zip(result.open_positions, table.iterrows()):
        assert row["Symbol"] == p.symbol and row["Current Price"] == p.last_price
        assert row["Unrealized P&L"] == pytest.approx(p.unrealized_pnl)


# 4. Equity / drawdown charts use the equity curve ------------------------------------------

def test_equity_chart_plots_actual_equity_curve(result):
    fig = dash.equity_figure(result)
    trace = fig.data[0]
    assert list(trace.y) == result.equity_curve["total_equity"].tolist()
    assert list(pd.to_datetime(trace.x)) == result.equity_curve["date"].tolist()


def test_drawdown_chart_uses_backtester_drawdown(result):
    fig = dash.drawdown_figure(result)
    assert list(fig.data[0].y) == result.equity_curve["drawdown"].tolist()


def test_trade_charts_use_trade_results(result):
    bars = dash.win_loss_figure(result).data[0]
    assert list(bars.y) == [result.metrics["losing_trades"], result.metrics["winning_trades"]]
    hist = dash.return_distribution_figure(result).data[0]
    assert list(hist.x) == [t.return_pct for t in result.trades]


# 5. Selected stock --------------------------------------------------------------------------

def test_stock_view_and_chart_use_selected_symbol_only(result):
    symbols = dash.stock_symbols(result)
    assert symbols == ["AAA.NS", "BBB.NS", "CCC.NS"]
    view = dash.stock_view(result, "BBB.NS")

    assert (view.prices["symbol"] == "BBB.NS").all()
    assert (view.signals["symbol"] == "BBB.NS").all()
    assert set(view.trades["Symbol"]) <= {"BBB.NS"}
    sf = result.strategy_frame[result.strategy_frame.symbol == "BBB.NS"]
    assert view.prices["close"].tolist() == sf["close"].tolist()

    own = [t for t in result.trades if t.symbol == "BBB.NS"]
    assert view.num_trades == len(own)
    assert view.realized_pnl == pytest.approx(sum(t.net_pnl for t in own))

    fig = dash.stock_figure(view)
    lines = {t.name: t for t in fig.data if t.mode == "lines"}
    assert list(lines["Close"].y) == sf["close"].tolist()
    assert np.allclose(list(lines["EMA20"].y), sf["ema20"].tolist(), equal_nan=True)
    assert np.allclose(list(lines["EMA50"].y), sf["ema50"].tolist(), equal_nan=True)
    markers = [t for t in fig.data if t.mode == "markers"]
    marker_dates = sorted(d for t in markers for d in pd.to_datetime(t.x))
    assert marker_dates == sorted(view.signals["signal_date"].tolist())


def test_markers_are_strategy_signals(result):
    view = dash.stock_view(result, "AAA.NS")
    sf = view.prices
    strategy_buys = sf.loc[sf.buy_signal, "date"].tolist()
    assert view.signals.loc[view.signals.side == "BUY", "signal_date"].tolist() == strategy_buys


# 6. Empty / no-trade results --------------------------------------------------------------------

def test_no_trade_result_does_not_crash():
    r = flat_result()
    assert r.metrics["completed_trades"] == 0
    assert dash.win_loss_figure(r) is None and dash.return_distribution_figure(r) is None
    assert dash.trades_table(r).empty and list(dash.trades_table(r).columns) == list(dash.TRADE_COLUMNS.values())
    assert dash.open_positions_table(r).empty
    cards = {c.label: c.value for c in dash.trade_metrics(r)}
    assert cards["Win Rate"] == "0.0%" and cards["Average Trade Return"] == "n/a"
    dash.equity_figure(r), dash.drawdown_figure(r)
    view = dash.stock_view(r, "FLAT.NS")
    assert view.num_trades == 0 and view.win_rate is None
    dash.stock_figure(view)


# 7. CSV downloads ---------------------------------------------------------------------------

def test_trades_csv_columns_and_rows(result):
    df = pd.read_csv(io.BytesIO(dash.trades_csv(result)))
    assert list(df.columns) == ["symbol", "entry_date", "entry_price", "exit_date", "exit_price",
                                "quantity", "gross_pnl", "transaction_cost", "net_pnl",
                                "return_pct", "holding_days"]
    assert len(df) == len(result.trades)


def test_equity_curve_csv_columns_and_rows(result):
    df = pd.read_csv(io.BytesIO(dash.equity_curve_csv(result)))
    assert {"date", "cash", "invested_value", "total_equity", "drawdown"} <= set(df.columns)
    assert len(df) == len(result.equity_curve)


def test_csv_downloads_for_no_trades():
    r = flat_result()
    assert pd.read_csv(io.BytesIO(dash.trades_csv(r))).empty
    assert len(pd.read_csv(io.BytesIO(dash.equity_curve_csv(r)))) == 80


# Formatting ----------------------------------------------------------------------------------------

@pytest.mark.parametrize("value, decimals, expected", [
    (100_000, 0, "₹1,00,000"),
    (351_595.4, 0, "₹3,51,595"),
    (12_345_678.9, 2, "₹1,23,45,678.90"),
    (999, 0, "₹999"),
    (-2_500.5, 1, "-₹2,500.5"),
    (None, 0, "n/a"),
])
def test_format_inr_indian_grouping(value, decimals, expected):
    assert dash.format_inr(value, decimals) == expected


def test_format_pct():
    assert dash.format_pct(0.264) == "+26.40%"
    assert dash.format_pct(-0.112) == "-11.20%"
    assert dash.format_pct(0.5, signed=False, decimals=1) == "50.0%"
    assert dash.format_pct(None) == "n/a"
