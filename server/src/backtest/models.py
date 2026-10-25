"""Data structures produced by the backtester.

Everything here is plain data so a frontend (or a CSV/JSON export) can consume
it without knowing how the simulation works. Return-type fields (`*_return`,
`return_pct`, `drawdown`) are decimal fractions: 0.05 means +5%.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field

import pandas as pd


@dataclass(frozen=True)
class BacktestConfig:
    initial_capital: float = 100_000.0
    transaction_cost: float = 0.001  # fraction of traded value, charged on BUY and on SELL
    max_position_weight: float = 0.10  # max fraction of portfolio equity per new position

    def __post_init__(self) -> None:
        if self.initial_capital <= 0:
            raise ValueError(f"initial_capital must be > 0, got {self.initial_capital}")
        if not 0 <= self.transaction_cost < 1:
            raise ValueError(f"transaction_cost must be in [0, 1), got {self.transaction_cost}")
        if not 0 < self.max_position_weight <= 1:
            raise ValueError(f"max_position_weight must be in (0, 1], got {self.max_position_weight}")


@dataclass
class Position:
    """A currently held stock."""

    symbol: str
    quantity: int
    entry_price: float
    entry_date: pd.Timestamp
    entry_cost: float  # transaction cost paid on the BUY
    entry_day_index: int  # position in the backtest's trading-day calendar
    last_price: float  # latest close it was marked to market at (the "current" price)

    @property
    def market_value(self) -> float:
        return self.quantity * self.last_price

    @property
    def unrealized_pnl(self) -> float:
        """Gain at the last close, net of the BUY cost (a SELL cost is not yet incurred)."""
        return (self.last_price - self.entry_price) * self.quantity - self.entry_cost


@dataclass(frozen=True)
class Execution:
    """One filled order (a BUY or a SELL), for trade markers and audit trails."""

    date: pd.Timestamp  # execution date (trading day after the signal)
    signal_date: pd.Timestamp
    symbol: str
    side: str  # "BUY" | "SELL"
    price: float  # the execution day's open
    quantity: int
    value: float  # price * quantity
    transaction_cost: float
    cash_after: float


@dataclass(frozen=True)
class Trade:
    """A completed round trip: BUY then SELL of the whole position."""

    symbol: str
    entry_date: pd.Timestamp
    entry_price: float
    exit_date: pd.Timestamp
    exit_price: float
    quantity: int
    gross_pnl: float  # (exit_price - entry_price) * quantity
    transaction_cost: float  # BUY cost + SELL cost
    net_pnl: float  # gross_pnl - transaction_cost
    return_pct: float  # net_pnl / total cash spent on entry (incl. cost), as a fraction
    holding_days: int  # trading days between entry and exit


@dataclass
class BacktestResult:
    """Everything a report or frontend needs.

    - trades:         completed round trips (trade table)
    - executions:     every BUY/SELL fill (chart markers)
    - signals:        every strategy signal and what happened to it
                      (executed / ignored and why)
    - equity_curve:   one row per trading day: date, cash, invested_value,
                      total_equity, positions, drawdown
    - metrics:        summary numbers (see metrics.compute_metrics)
    - open_positions: positions still held on the last day (marked to market
                      in the equity curve, not counted as completed trades)
    - strategy_frame: the exact per-stock data the backtest traded on (prices
                      plus the strategy's own columns, e.g. sma20/sma50 and
                      buy/sell signals), so reports never recompute it
    """

    config: BacktestConfig
    trades: list[Trade]
    executions: list[Execution]
    signals: pd.DataFrame
    equity_curve: pd.DataFrame
    metrics: dict
    open_positions: list[Position] = field(default_factory=list)
    strategy_frame: pd.DataFrame | None = None

    def trades_frame(self) -> pd.DataFrame:
        return _frame(self.trades, Trade)

    def executions_frame(self) -> pd.DataFrame:
        return _frame(self.executions, Execution)

    def open_positions_frame(self) -> pd.DataFrame:
        df = _frame(self.open_positions, Position)
        df["market_value"] = [p.market_value for p in self.open_positions]
        df["unrealized_pnl"] = [p.unrealized_pnl for p in self.open_positions]
        return df


def _frame(items: list, cls: type) -> pd.DataFrame:
    columns = list(cls.__dataclass_fields__)
    return pd.DataFrame([asdict(i) for i in items], columns=columns)
