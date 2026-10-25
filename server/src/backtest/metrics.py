"""Performance metrics computed from an equity curve and completed trades.

All functions are pure. Returns are decimal fractions (0.05 = +5%).
"""

from __future__ import annotations

import pandas as pd

from .models import Trade

DAYS_PER_YEAR = 365.25
MIN_YEARS_FOR_CAGR = 1.0  # annualising a few weeks of returns is misleading


def drawdown_series(equity: pd.Series) -> pd.Series:
    """Drawdown at each point: (equity - running peak) / running peak, always <= 0."""
    peak = equity.cummax()
    return equity / peak - 1


def max_drawdown(equity: pd.Series) -> float:
    """Most negative drawdown, e.g. -0.25 for a 25% peak-to-trough fall; 0.0 if none."""
    if equity.empty:
        return 0.0
    return float(min(drawdown_series(equity).min(), 0.0))


def cagr(
    initial: float,
    final: float,
    start: pd.Timestamp,
    end: pd.Timestamp,
    min_years: float = MIN_YEARS_FOR_CAGR,
) -> float | None:
    """Compound annual growth rate, or None if the period is shorter than `min_years`."""
    years = (pd.Timestamp(end) - pd.Timestamp(start)).days / DAYS_PER_YEAR
    if years < min_years or initial <= 0 or final <= 0:
        return None
    return float((final / initial) ** (1 / years) - 1)


def compute_metrics(
    trades: list[Trade],
    equity_curve: pd.DataFrame,
    initial_capital: float,
    open_positions: int = 0,
) -> dict:
    """Summary metrics for a backtest. Safe with zero trades or an empty curve."""
    if equity_curve.empty:
        final_equity, start, end = float(initial_capital), None, None
    else:
        final_equity = float(equity_curve["total_equity"].iloc[-1])
        start, end = equity_curve["date"].iloc[0], equity_curve["date"].iloc[-1]

    n = len(trades)
    wins = sum(t.net_pnl > 0 for t in trades)
    losses = sum(t.net_pnl < 0 for t in trades)
    total_return = final_equity / initial_capital - 1

    return {
        "start_date": None if start is None else str(pd.Timestamp(start).date()),
        "end_date": None if end is None else str(pd.Timestamp(end).date()),
        "trading_days": len(equity_curve),
        "initial_capital": float(initial_capital),
        "final_equity": final_equity,
        "total_return": total_return,
        "total_return_pct": total_return * 100,
        "cagr": None if start is None else cagr(initial_capital, final_equity, start, end),
        "max_drawdown": 0.0 if equity_curve.empty else max_drawdown(equity_curve["total_equity"]),
        "completed_trades": n,
        "winning_trades": wins,
        "losing_trades": losses,
        "win_rate": wins / n if n else 0.0,
        "avg_trade_return": sum(t.return_pct for t in trades) / n if n else None,
        "total_net_pnl": sum(t.net_pnl for t in trades),
        "total_transaction_costs": sum(t.transaction_cost for t in trades),  # completed trades only
        "avg_holding_days": sum(t.holding_days for t in trades) / n if n else None,
        "open_positions": open_positions,
    }
