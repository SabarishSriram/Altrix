import pandas as pd
import pytest

from src.backtest.metrics import cagr, compute_metrics, drawdown_series, max_drawdown
from src.backtest.models import Trade

D = pd.Timestamp


def trade(net: float, ret: float, days: int = 10) -> Trade:
    return Trade("A", D("2024-01-01"), 100.0, D("2024-02-01"), 100.0, 10,
                 gross_pnl=net + 2, transaction_cost=2.0, net_pnl=net,
                 return_pct=ret, holding_days=days)


def curve(values, start="2024-01-01") -> pd.DataFrame:
    return pd.DataFrame({"date": pd.bdate_range(start, periods=len(values)),
                         "total_equity": [float(v) for v in values]})


# Test 11 - maximum drawdown ---------------------------------------------------

def test_max_drawdown_deterministic():
    eq = pd.Series([100.0, 120.0, 90.0, 130.0, 104.0])
    # 120 -> 90 is -25%; 130 -> 104 is only -20%
    assert max_drawdown(eq) == pytest.approx(-0.25)
    assert drawdown_series(eq).tolist() == pytest.approx([0, 0, -0.25, 0, -0.20])


def test_max_drawdown_rising_flat_and_empty():
    assert max_drawdown(pd.Series([100.0, 101.0, 105.0])) == 0.0
    assert max_drawdown(pd.Series([100.0] * 5)) == 0.0
    assert max_drawdown(pd.Series([], dtype=float)) == 0.0


def test_drawdown_measured_from_running_peak_not_start():
    assert max_drawdown(pd.Series([100.0, 200.0, 150.0])) == pytest.approx(-0.25)


# CAGR ---------------------------------------------------------------------------

def test_cagr_two_years():
    assert cagr(100, 121, D("2020-01-01"), D("2022-01-01")) == pytest.approx(0.10, abs=1e-3)


def test_cagr_none_for_short_periods():
    assert cagr(100, 150, D("2024-01-01"), D("2024-06-01")) is None


# compute_metrics ------------------------------------------------------------------

def test_trade_statistics():
    trades = [trade(500, 0.05), trade(-200, -0.02), trade(300, 0.03), trade(0, 0.0)]
    m = compute_metrics(trades, curve([100_000, 100_600]), 100_000)
    assert m["completed_trades"] == 4
    assert m["winning_trades"] == 2 and m["losing_trades"] == 1  # break-even is neither
    assert m["win_rate"] == pytest.approx(0.5)
    assert m["avg_trade_return"] == pytest.approx(0.015)
    assert m["total_net_pnl"] == pytest.approx(600)
    assert m["total_transaction_costs"] == pytest.approx(8)


def test_returns_and_dates():
    m = compute_metrics([], curve([100_000, 90_000, 110_000]), 100_000)
    assert m["final_equity"] == 110_000
    assert m["total_return"] == pytest.approx(0.10) and m["total_return_pct"] == pytest.approx(10)
    assert m["max_drawdown"] == pytest.approx(-0.10)
    assert m["start_date"] == "2024-01-01" and m["end_date"] == "2024-01-03"
    assert m["cagr"] is None  # 3 days: not annualised


def test_zero_trades_and_empty_curve_are_safe():
    m = compute_metrics([], curve([]), 100_000)
    assert m["final_equity"] == 100_000 and m["total_return"] == 0
    assert m["win_rate"] == 0.0 and m["avg_trade_return"] is None
    assert m["max_drawdown"] == 0.0 and m["cagr"] is None
