import math

import numpy as np
import pandas as pd
import pytest

from src.backtest import run_backtest, run_backtest_on_signals
from src.strategy import generate_baseline_signals

from ..conftest import make_bars

DATES = pd.bdate_range("2024-01-01", periods=10)


def market(symbol, opens, closes=None, buys=(), sells=(), dates=None) -> pd.DataFrame:
    """Bars with explicit signals. `buys`/`sells` are row indices where the signal fires."""
    closes = closes if closes is not None else opens
    dates = DATES[: len(opens)] if dates is None else pd.to_datetime(dates)
    n = len(opens)
    return pd.DataFrame({
        "date": dates,
        "symbol": symbol,
        "open": [float(x) for x in opens],
        "close": [float(x) for x in closes],
        "buy_signal": [i in buys for i in range(n)],
        "sell_signal": [i in sells for i in range(n)],
    })


def bt(*frames, **kwargs):
    return run_backtest_on_signals(pd.concat(frames, ignore_index=True), **kwargs)


# Test 1 - basic BUY and SELL ------------------------------------------------

def test_basic_round_trip_exact_numbers():
    df = market("A", opens=[100, 101, 103, 104, 104], closes=[100, 102, 105, 104, 106],
                buys=[0], sells=[2])
    r = bt(df)

    qty = math.floor(10_000 / (101 * 1.001))                 # 10% of 100k, costs included
    buy_cost, sell_cost = qty * 101 * 0.001, qty * 104 * 0.001
    final_cash = 100_000 - qty * 101 - buy_cost + qty * 104 - sell_cost

    [t] = r.trades
    assert (t.entry_date, t.entry_price) == (DATES[1], 101.0)
    assert (t.exit_date, t.exit_price) == (DATES[3], 104.0)
    assert t.quantity == qty == 98
    assert t.gross_pnl == pytest.approx(3 * qty)
    assert t.transaction_cost == pytest.approx(buy_cost + sell_cost)
    assert t.net_pnl == pytest.approx(3 * qty - buy_cost - sell_cost)
    assert t.return_pct == pytest.approx(t.net_pnl / (qty * 101 + buy_cost))
    assert t.holding_days == 2

    last = r.equity_curve.iloc[-1]
    assert last["cash"] == pytest.approx(final_cash)
    assert last["invested_value"] == 0 and last["total_equity"] == pytest.approx(final_cash)
    assert r.metrics["final_equity"] == pytest.approx(final_cash)
    assert r.metrics["completed_trades"] == 1 and r.open_positions == []


# Test 2 - next-day open execution -----------------------------------------

def test_signal_executes_at_next_day_open_not_signal_close():
    df = market("A", opens=[100, 150, 160, 170, 180], closes=[110, 155, 165, 175, 185],
                buys=[0], sells=[2])
    r = bt(df)
    buy, sell = r.executions
    assert buy.signal_date == DATES[0] and buy.date == DATES[1]
    assert buy.signal_date != buy.date
    assert buy.price == 150.0   # day 1 open, not day 0 close (110) or day 0 open (100)
    assert sell.signal_date == DATES[2] and sell.date == DATES[3]
    assert sell.price == 170.0  # day 3 open, not day 2 close (165)


def test_real_strategy_always_fills_at_next_row_open():
    df = make_bars("A", days=260)
    rng = np.random.default_rng(3)
    walk = 100 * np.exp(np.cumsum(rng.normal(0, 0.02, len(df))))
    df = df.assign(open=walk * 0.995, high=walk * 1.02, low=walk * 0.98, close=walk)

    r = run_backtest(df)
    assert len(r.executions) >= 2
    rows = df.set_index("date")
    for e in r.executions:
        nxt = rows.index[rows.index.get_loc(e.signal_date) + 1]
        assert e.date == nxt and e.price == rows.loc[nxt, "open"]


def test_order_waits_for_the_stocks_own_next_trading_row():
    # B has no bar on day 2 (e.g. a data gap), so its day-1 BUY fills on day 3.
    a = market("A", opens=[100] * 5)
    b = market("B", opens=[50, 51, 53, 54], buys=[1], dates=DATES[[0, 1, 3, 4]])
    r = bt(a, b)
    [e] = r.executions
    assert e.signal_date == DATES[1] and e.date == DATES[3] and e.price == 53.0


# Test 3 - transaction costs -------------------------------------------------

def test_costs_charged_on_buy_and_sell():
    df = market("A", opens=[100, 100, 100, 110, 110], buys=[0], sells=[2])
    r = bt(df, transaction_cost=0.01, max_position_weight=1.0)
    buy, sell = r.executions
    qty = math.floor(100_000 / (100 * 1.01))
    assert buy.transaction_cost == pytest.approx(qty * 100 * 0.01)
    assert buy.cash_after == pytest.approx(100_000 - qty * 100 * 1.01)
    assert sell.transaction_cost == pytest.approx(qty * 110 * 0.01)
    assert sell.cash_after == pytest.approx(buy.cash_after + qty * 110 * 0.99)
    assert r.trades[0].transaction_cost == pytest.approx(buy.transaction_cost + sell.transaction_cost)


def test_spec_cost_example_10k_trade_costs_10():
    df = market("A", opens=[100, 100, 100, 100, 100], buys=[0], sells=[2])
    r = bt(df, max_position_weight=0.10011)  # budget just fits 100 shares + 0.1% cost
    buy, sell = r.executions
    assert buy.quantity == 100 and buy.value == 10_000
    assert buy.transaction_cost == pytest.approx(10)
    assert 100_000 - buy.cash_after == pytest.approx(10_010)
    assert sell.cash_after - buy.cash_after == pytest.approx(9_990)


def test_zero_cost():
    df = market("A", opens=[100, 100, 100, 120, 120], buys=[0], sells=[2])
    r = bt(df, transaction_cost=0.0)
    assert r.trades[0].quantity == 100 and r.trades[0].net_pnl == pytest.approx(2_000)


# Tests 4-6 - multiple stocks, shared capital, position limit ------------------

def test_several_stocks_held_at_once():
    a = market("A", opens=[100] * 6, buys=[0], sells=[3])
    b = market("B", opens=[50] * 6, buys=[1])
    r = bt(a, b)
    assert r.equity_curve["positions"].tolist() == [0, 1, 2, 2, 1, 1]
    assert [p.symbol for p in r.open_positions] == ["B"]


def test_same_day_buys_share_one_portfolio():
    stocks = [market(s, opens=[100] * 4, buys=[0]) for s in ("A", "B", "C")]
    r = bt(*stocks, max_position_weight=0.4, transaction_cost=0.0)
    # Filled one after another from the same cash: 40k, 40k, then the 20k left (still >= 5% of equity).
    assert [(e.symbol, e.quantity) for e in r.executions] == [("A", 400), ("B", 400), ("C", 200)]
    assert r.equity_curve["cash"].iloc[-1] == pytest.approx(0)
    assert r.equity_curve["cash"].min() >= 0


def momentum(symbol, start, end, buy_at=21, n=25, jump_on_fill=None) -> pd.DataFrame:
    """Closes rising linearly from `start` (row 0) to `end` (row buy_at), flat after; BUY at `buy_at`.

    roc20 at the signal = end / close[buy_at - 20] - 1. Opens equal closes.
    """
    closes = list(np.linspace(start, end, buy_at + 1)) + [end] * (n - buy_at - 1)
    if jump_on_fill is not None:  # the fill day's close changes; roc20 must not see it
        closes[buy_at + 1] = jump_on_fill
    return market(symbol, opens=closes, closes=closes, buys=[buy_at], dates=pd.bdate_range("2024-01-01", periods=n))


def test_same_day_buys_ranked_by_20_day_rate_of_change():
    low, high, mid = momentum("A", 100, 105), momentum("B", 100, 130), momentum("C", 100, 115)
    r = bt(low, high, mid, max_position_weight=0.5, transaction_cost=0.0)
    # Only two 50% positions fit: strongest momentum first (B, then C), not alphabetical (A, B).
    assert [e.symbol for e in r.executions] == ["B", "C"]
    status = dict(zip(r.signals["symbol"], r.signals["status"]))
    assert status == {"A": "below_min_position", "B": "executed", "C": "executed"}


def test_ranking_uses_only_the_signal_days_close():
    # At the signal close A has the higher roc20; B's close jumps on the fill day, which must not count.
    a = momentum("A", 100, 120)
    b = momentum("B", 100, 110, jump_on_fill=200)
    r = bt(a, b, max_position_weight=1.0, transaction_cost=0.0)
    assert [e.symbol for e in r.executions] == ["A"]


def test_missing_roc_ranks_last_then_symbol_order():
    short = market("A", opens=[100] * 25, buys=[21], dates=pd.bdate_range("2024-01-01", periods=25))
    short.loc[:5, "open"] = short.loc[:5, "close"] = np.nan  # no close 20 rows before the signal
    ranked = momentum("Z", 100, 101)  # +1%: weak, but known
    r = bt(short, ranked, max_position_weight=1.0, transaction_cost=0.0)
    assert [e.symbol for e in r.executions] == ["Z"]


def test_cash_dust_buy_is_skipped():
    a = market("A", opens=[100] * 6, buys=[0])
    b = market("B", opens=[100] * 6, buys=[2])
    r = bt(a, b, max_position_weight=0.97, transaction_cost=0.0)
    # After A, 3k is left: below 5% of ~100k equity, so B is not bought for a token amount.
    assert [e.symbol for e in r.executions] == ["A"]
    assert r.signals.set_index("symbol").loc["B", "status"] == "below_min_position"

    old_rule = bt(a, b, max_position_weight=0.97, transaction_cost=0.0, min_position_weight=0.0)
    assert [(e.symbol, e.quantity) for e in old_rule.executions] == [("A", 970), ("B", 30)]


def test_min_position_weight_must_fit_under_max():
    df = market("A", opens=[100] * 4, buys=[0])
    with pytest.raises(ValueError, match="min_position_weight"):
        bt(df, max_position_weight=0.04)  # default minimum is 5%
    with pytest.raises(ValueError, match="min_position_weight"):
        bt(df, min_position_weight=-0.01)


def test_later_buy_limited_by_remaining_cash():
    a = market("A", opens=[100] * 6, buys=[0])
    b = market("B", opens=[100] * 6, buys=[2])
    r = bt(a, b, max_position_weight=0.6, transaction_cost=0.0)
    qa, qb = (e.quantity for e in r.executions)
    assert qa == 600            # 60% of 100k
    assert qb == 400            # wanted 60% of equity, only 40k cash left
    assert r.equity_curve["cash"].iloc[-1] == pytest.approx(0)


def test_sells_fill_before_buys_and_free_cash():
    a = market("A", opens=[100, 100, 100, 100, 100], buys=[0], sells=[2])
    b = market("B", opens=[100, 100, 100, 100, 100], buys=[2])
    r = bt(a, b, max_position_weight=1.0, transaction_cost=0.0)
    sell_a, buy_b = r.executions[1], r.executions[2]
    assert sell_a.side == "SELL" and buy_b.side == "BUY" and sell_a.date == buy_b.date
    assert buy_b.quantity == 1000  # used A's sale proceeds the same morning


@pytest.mark.parametrize("weight", [0.05, 0.10, 0.25])
def test_position_never_exceeds_max_weight(weight):
    df = market("A", opens=[37.3] * 4, buys=[0])
    r = bt(df, max_position_weight=weight)
    [buy] = r.executions
    assert buy.value + buy.transaction_cost <= weight * 100_000
    assert buy.quantity == math.floor(weight * 100_000 / (37.3 * 1.001))


def test_weight_uses_current_equity_not_initial_capital():
    a = market("A", opens=[100, 100, 300, 300, 300, 300], buys=[0])  # A triples
    b = market("B", opens=[10] * 6, buys=[3])
    r = bt(a, b, max_position_weight=0.5, transaction_cost=0.0)
    # Equity at day-3 close = 50k cash + 500 * 300 = 200k -> 50% = 100k, but cash is 50k.
    assert r.executions[1].quantity == 5_000


# Test 7-9 - ignored signals ---------------------------------------------------

def test_repeated_buy_does_not_duplicate_position():
    df = market("A", opens=[100] * 6, buys=[0, 2, 3])
    r = bt(df)
    assert len(r.executions) == 1 and len(r.open_positions) == 1
    assert r.signals["status"].tolist() == ["executed", "ignored_already_held", "ignored_already_held"]


def test_sell_without_position_is_ignored():
    df = market("A", opens=[100] * 5, sells=[1])
    r = bt(df)
    assert r.executions == [] and r.trades == []
    assert r.signals["status"].tolist() == ["ignored_not_held"]
    assert (r.equity_curve["total_equity"] == 100_000).all()


def test_final_day_signal_is_not_executed():
    df = market("A", opens=[100] * 5, buys=[4])
    r = bt(df)
    assert r.executions == []
    assert r.signals.loc[0, "status"] == "no_next_day"
    assert pd.isna(r.signals.loc[0, "execution_date"])


def test_final_day_sell_leaves_position_open():
    df = market("A", opens=[100, 100, 100, 100, 120], buys=[0], sells=[4])
    r = bt(df)
    assert r.trades == [] and len(r.open_positions) == 1
    assert r.metrics["open_positions"] == 1
    assert r.equity_curve["invested_value"].iloc[-1] == pytest.approx(r.open_positions[0].quantity * 120)


@pytest.mark.parametrize("bad_open", [np.nan, 0.0, -5.0])
def test_invalid_open_is_not_traded(bad_open):
    df = market("A", opens=[100, bad_open, 100, 100], closes=[100] * 4, buys=[0])
    r = bt(df)
    assert r.executions == []
    assert r.signals.loc[0, "status"] == "invalid_open"


def test_budget_below_one_share_is_skipped():
    df = market("A", opens=[200_000] * 4, buys=[0])
    r = bt(df)
    assert r.executions == [] and r.signals.loc[0, "status"] == "insufficient_cash"


# Test 10 - equity curve ---------------------------------------------------------

def test_equity_curve_daily_values():
    df = market("A", opens=[100, 100, 104, 108, 103], closes=[100, 102, 106, 101, 110],
                buys=[0], sells=[3])
    r = bt(df, transaction_cost=0.0)
    ec = r.equity_curve
    qty = 100  # 10k / 100
    cash_held = 100_000 - qty * 100

    assert ec["date"].tolist() == list(DATES[:5])  # one row per trading day
    assert ec["cash"].tolist() == pytest.approx([100_000, cash_held, cash_held, cash_held, cash_held + qty * 103])
    assert ec["invested_value"].tolist() == pytest.approx([0, qty * 102, qty * 106, qty * 101, 0])
    assert (ec["total_equity"] == ec["cash"] + ec["invested_value"]).all()
    assert ec["drawdown"].tolist() == pytest.approx(
        [0, 0, 0, (100_100 - 100_600) / 100_600, (100_300 - 100_600) / 100_600], abs=1e-12
    )


def test_held_stock_without_bar_keeps_last_close():
    a = market("A", opens=[100, 100, 100, 100], closes=[100, 110, 120, 130], buys=[0],
                dates=DATES[[0, 1, 2, 4]])     # no bar on day 3
    b = market("B", opens=[50] * 5)
    r = bt(a, b, transaction_cost=0.0)
    ec = r.equity_curve.set_index("date")
    assert ec.loc[DATES[3], "invested_value"] == pytest.approx(100 * 120)


# Test 12 - no trades ---------------------------------------------------------------

def test_no_signals_gives_valid_empty_result():
    r = bt(market("A", opens=[100, 101, 99, 102, 98]))
    m = r.metrics
    assert r.trades == [] and r.executions == [] and r.signals.empty
    assert len(r.equity_curve) == 5
    assert m["initial_capital"] == m["final_equity"] == 100_000
    assert m["total_return"] == 0 and m["completed_trades"] == 0
    assert m["win_rate"] == 0.0 and m["max_drawdown"] == 0.0
    assert r.trades_frame().empty and "net_pnl" in r.trades_frame().columns


def test_real_strategy_with_too_little_history():
    r = run_backtest(make_bars("A", days=30))
    assert r.trades == [] and r.metrics["final_equity"] == 100_000


# Test 13 - no mutation, lookahead ---------------------------------------------------

def test_inputs_not_mutated():
    df = market("A", opens=[100, 101, 103, 104, 104], buys=[0], sells=[2])
    before = df.copy(deep=True)
    bt_input = df.copy()
    run_backtest_on_signals(bt_input)
    pd.testing.assert_frame_equal(bt_input, before)

    bars = make_bars("A", days=120)
    bars_before = bars.copy(deep=True)
    run_backtest(bars)
    pd.testing.assert_frame_equal(bars, bars_before)


def test_future_prices_never_change_the_past():
    rng = np.random.default_rng(42)
    frames = []
    for sym in ("A", "B", "C"):
        df = make_bars(sym, days=400)
        walk = 100 * np.exp(np.cumsum(rng.normal(0, 0.02, len(df))))
        frames.append(df.assign(open=walk * 0.99, high=walk * 1.03, low=walk * 0.97, close=walk))
    full_df = pd.concat(frames, ignore_index=True)
    full = run_backtest(full_df)
    assert len(full.trades) > 3

    cut = full_df["date"].sort_values().unique()[250]
    # Wildly change every price after the cut: nothing up to the cut may change.
    tampered = full_df.copy()
    later = tampered["date"] > cut
    tampered.loc[later, ["open", "high", "low", "close"]] *= 3
    alt = run_backtest(tampered)

    upto = lambda ec: ec[ec["date"] <= cut].reset_index(drop=True)
    pd.testing.assert_frame_equal(upto(full.equity_curve), upto(alt.equity_curve))
    assert [e for e in full.executions if e.date <= cut] == [e for e in alt.executions if e.date <= cut]


def test_signals_identical_to_strategy_module():
    df = make_bars("A", days=200)
    r = run_backtest(df)
    sig = generate_baseline_signals(df)
    expected = sig[sig.buy_signal | sig.sell_signal]
    assert r.signals["signal_date"].tolist() == expected["date"].tolist()


# Validation and extras --------------------------------------------------------------

@pytest.mark.parametrize("col", ["date", "symbol", "open", "close", "buy_signal", "sell_signal"])
def test_missing_columns_raise(col):
    with pytest.raises(ValueError, match=f"missing required column.*'{col}'"):
        run_backtest_on_signals(market("A", opens=[100] * 3).drop(columns=col))


def test_buy_and_sell_on_same_row_raises():
    df = market("A", opens=[100] * 3, buys=[1], sells=[1])
    with pytest.raises(ValueError, match="same row"):
        bt(df)


@pytest.mark.parametrize("kwargs", [{"initial_capital": 0}, {"transaction_cost": -0.1},
                                    {"max_position_weight": 0}, {"max_position_weight": 1.5}])
def test_invalid_config_raises(kwargs):
    with pytest.raises(ValueError):
        bt(market("A", opens=[100] * 3), **kwargs)


def test_optional_benchmark_buy_and_hold():
    df = market("A", opens=[100] * 5)
    bench = pd.Series([1000.0, 1100.0, 1050.0, 1200.0, 900.0], index=DATES[:5])
    r = bt(df, benchmark=bench)
    assert r.equity_curve["benchmark_equity"].tolist() == pytest.approx(
        [100_000, 110_000, 105_000, 120_000, 90_000])
    assert r.metrics["benchmark_total_return"] == pytest.approx(-0.10)
    assert r.metrics["benchmark_max_drawdown"] == pytest.approx(-0.25)


# Date range, open-position valuation, strategy frame (used by the dashboard) ----------

def _walk_market(days=400, seed=42, symbols=("A", "B", "C")) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    frames = []
    for sym in symbols:
        df = make_bars(sym, days=days)
        walk = 100 * np.exp(np.cumsum(rng.normal(0, 0.02, len(df))))
        frames.append(df.assign(open=walk * 0.99, high=walk * 1.03, low=walk * 0.97, close=walk))
    return pd.concat(frames, ignore_index=True)


def test_date_range_keeps_sma_warmup_from_earlier_history():
    df = _walk_market()
    dates = df["date"].sort_values().unique()
    start, end = dates[100], dates[300]
    r = run_backtest(df, start=start, end=end)

    assert r.equity_curve["date"].iloc[0] == start and r.equity_curve["date"].iloc[-1] == end
    sf = r.strategy_frame
    assert sf["sma50"].notna().all()  # warmed up on pre-start history
    full = generate_baseline_signals(df)
    in_range = full[(full.date >= start) & (full.date <= end)]
    assert r.signals["signal_date"].tolist() == sorted(
        in_range.loc[in_range.buy_signal | in_range.sell_signal, "date"].tolist())


def test_data_after_end_date_is_never_used():
    df = _walk_market()
    end = df["date"].sort_values().unique()[250]
    tampered = df.copy()
    tampered.loc[tampered.date > end, ["open", "close"]] *= 5
    a, b = run_backtest(df, end=end), run_backtest(tampered, end=end)
    pd.testing.assert_frame_equal(a.equity_curve, b.equity_curve)
    assert a.metrics == b.metrics


def test_invalid_and_empty_date_ranges_raise():
    df = _walk_market(days=60)
    with pytest.raises(ValueError, match="after end"):
        run_backtest(df, start="2024-03-01", end="2024-01-01")
    with pytest.raises(ValueError, match="no data"):
        run_backtest(df, start="2030-01-01")


def test_open_positions_frame_has_current_value_and_unrealized_pnl():
    df = market("A", opens=[100, 100, 100, 100], closes=[100, 105, 110, 120], buys=[0])
    r = bt(df)
    [p] = r.open_positions
    assert p.last_price == 120.0
    op = r.open_positions_frame()
    row = op.iloc[0]
    assert row["market_value"] == pytest.approx(p.quantity * 120)
    assert row["unrealized_pnl"] == pytest.approx((120 - 100) * p.quantity - p.entry_cost)
    assert r.equity_curve["invested_value"].iloc[-1] == pytest.approx(op["market_value"].sum())


def test_strategy_frame_is_the_strategy_output():
    df = make_bars("A", days=120)
    r = run_backtest(df)
    pd.testing.assert_frame_equal(r.strategy_frame, generate_baseline_signals(df))
