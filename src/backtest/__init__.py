"""Altrix backtester: simulate trading a strategy's signals on historical data."""

from .engine import run_backtest, run_backtest_on_signals
from .metrics import cagr, compute_metrics, drawdown_series, max_drawdown
from .models import BacktestConfig, BacktestResult, Execution, Position, Trade

__all__ = [
    "BacktestConfig",
    "BacktestResult",
    "Execution",
    "Position",
    "Trade",
    "cagr",
    "compute_metrics",
    "drawdown_series",
    "max_drawdown",
    "run_backtest",
    "run_backtest_on_signals",
]
