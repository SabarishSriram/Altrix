"""Daily, long-only, multi-stock portfolio backtester.

Timeline for every trading day D, in this order:

    1. OPEN    Fill orders created at the previous close, at D's open:
               a. SELLs first (whole position), releasing cash
               b. then BUYs, sized by the position-sizing rule
    2. CLOSE   Mark all positions to market at D's close -> one equity-curve row
    3. CLOSE   Read the strategy's signals for D (computed from D's close) and
               turn them into orders for the stock's *next* trading day

So a signal on day T always fills at the open of that stock's next trading
row, never at T's close. Signals are read only after the day is fully
processed, and orders only ever see the open of the day they fill on; no
step reads a price from a day the simulation has not reached yet.

Position sizing (V1, deterministic):
    budget per BUY = min(max_position_weight * equity at previous close,
                         cash after today's SELLs / number of BUYs filling today)
    quantity       = floor(budget / (open * (1 + transaction_cost)))   # whole shares
Transaction costs come out of the budget, so cash never goes negative. Unspent
money stays as cash. BUYs on the same day share cash equally; ties are processed
in symbol order.

Ignored signals (recorded in `result.signals` with a reason, never traded):
    BUY for a stock already held, SELL for a stock not held, no next trading
    day (signal on a stock's last row), missing/zero/negative open, or a budget
    too small for one share.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import pandas as pd

from src.strategy.baseline import generate_baseline_signals

from .metrics import compute_metrics, drawdown_series, max_drawdown
from .models import BacktestConfig, BacktestResult, Execution, Position, Trade

REQUIRED_COLUMNS: tuple[str, ...] = ("date", "symbol", "open", "close", "buy_signal", "sell_signal")

# Signal statuses, as they appear in result.signals["status"]
EXECUTED = "executed"
IGNORED_ALREADY_HELD = "ignored_already_held"
IGNORED_NOT_HELD = "ignored_not_held"
NO_NEXT_DAY = "no_next_day"
INVALID_OPEN = "invalid_open"
INSUFFICIENT_CASH = "insufficient_cash"


@dataclass
class _Order:
    signal_id: int
    symbol: str
    side: str  # "BUY" | "SELL"
    signal_date: pd.Timestamp


def run_backtest(
    df: pd.DataFrame,
    initial_capital: float = 100_000,
    transaction_cost: float = 0.001,
    max_position_weight: float = 0.10,
    benchmark: pd.Series | None = None,
    start: str | pd.Timestamp | None = None,
    end: str | pd.Timestamp | None = None,
) -> BacktestResult:
    """Backtest the SMA20/SMA50 baseline strategy on daily OHLCV data.

    Args:
        df: Daily bars (at least date, symbol, open, close) for one or more
            stocks, ideally from `src.data.load_clean`. Not modified.
        initial_capital: Starting cash in INR.
        transaction_cost: Fraction of traded value charged on every BUY and SELL.
        max_position_weight: Max fraction of portfolio equity for a new position.
        benchmark: Optional close prices indexed by date (e.g. an index) for a
            buy-and-hold comparison. Never downloaded here.
        start: First trading date of the backtest (inclusive). History before
            it is still used to warm up the SMAs, so signals on `start` are the
            same as in a full-history run. The portfolio starts in cash.
        end: Last trading date (inclusive). Data after it is removed before the
            strategy runs, so nothing after `end` can influence the result.

    Raises:
        ValueError: if `start` is after `end`, or no data falls in the range.
    """
    start = None if start is None else pd.Timestamp(start)
    end = None if end is None else pd.Timestamp(end)
    if start is not None and end is not None and start > end:
        raise ValueError(f"start date {start.date()} is after end date {end.date()}")

    dates = pd.to_datetime(df["date"]) if "date" in df.columns else None
    if end is not None and dates is not None:
        df = df[dates <= end]
    signals = generate_baseline_signals(df)
    if start is not None:
        signals = signals[signals["date"] >= start].reset_index(drop=True)
    if signals.empty:
        raise ValueError("no data in the selected date range")

    return run_backtest_on_signals(
        signals,
        initial_capital=initial_capital,
        transaction_cost=transaction_cost,
        max_position_weight=max_position_weight,
        benchmark=benchmark,
    )


def run_backtest_on_signals(
    df: pd.DataFrame,
    initial_capital: float = 100_000,
    transaction_cost: float = 0.001,
    max_position_weight: float = 0.10,
    benchmark: pd.Series | None = None,
) -> BacktestResult:
    """Backtest any strategy that provides boolean `buy_signal` / `sell_signal` columns.

    A signal on row (symbol, T) means "decided after T's close"; it is filled
    at the open of the same symbol's next row. See the module docstring for
    the full daily timeline and sizing rule.
    """
    config = BacktestConfig(initial_capital, transaction_cost, max_position_weight)
    data = _prepare(df)
    tc = config.transaction_cost

    calendar = list(data["date"].drop_duplicates().sort_values())
    rows_by_day = {d: g for d, g in data.groupby("date", sort=True)}

    cash = float(config.initial_capital)
    positions: dict[str, Position] = {}
    pending: dict[str, _Order] = {}  # at most one open order per symbol
    last_close: dict[str, float] = {}  # latest valid close seen so far, per symbol
    prev_equity = cash

    trades: list[Trade] = []
    executions: list[Execution] = []
    signal_log: list[dict] = []
    curve: list[dict] = []

    def resolve(order: _Order, status: str, day=None, price=None, qty=None) -> None:
        signal_log[order.signal_id].update(
            status=status, execution_date=day, execution_price=price, quantity=qty
        )

    for day_index, day in enumerate(calendar):
        today = rows_by_day[day]
        opens = dict(zip(today["symbol"], today["open"]))

        # ---- 1. OPEN: fill orders for stocks that trade today -----------------
        due = [pending.pop(s) for s in sorted(pending) if s in opens]
        sells = [o for o in due if o.side == "SELL"]
        buys = [o for o in due if o.side == "BUY"]

        # 1a. SELLs first, so released cash is available to today's BUYs.
        for order in sells:
            price = opens[order.symbol]
            if order.symbol not in positions:
                resolve(order, IGNORED_NOT_HELD)
                continue
            if not _valid_price(price):
                resolve(order, INVALID_OPEN, day)
                continue
            pos = positions.pop(order.symbol)
            value = pos.quantity * price
            cost = value * tc
            cash += value - cost
            executions.append(Execution(day, order.signal_date, pos.symbol, "SELL",
                                        price, pos.quantity, value, cost, cash))
            trades.append(_close_trade(pos, day, day_index, price, cost))
            resolve(order, EXECUTED, day, price, pos.quantity)

        # 1b. BUYs, sharing cash equally.
        eligible = []
        for order in buys:
            if order.symbol in positions:
                resolve(order, IGNORED_ALREADY_HELD)
            elif not _valid_price(opens[order.symbol]):
                resolve(order, INVALID_OPEN, day)
            else:
                eligible.append(order)

        if eligible:
            # Fixed before any of today's BUYs, so order of processing doesn't matter.
            budget = min(config.max_position_weight * prev_equity, cash / len(eligible))
            for order in eligible:
                price = opens[order.symbol]
                qty = math.floor(budget / (price * (1 + tc)))  # whole shares only
                if qty < 1:
                    resolve(order, INSUFFICIENT_CASH, day, price)
                    continue
                value = qty * price
                cost = value * tc
                cash -= value + cost
                positions[order.symbol] = Position(order.symbol, qty, price, day, cost, day_index,
                                                   last_price=price)
                executions.append(Execution(day, order.signal_date, order.symbol, "BUY",
                                            price, qty, value, cost, cash))
                resolve(order, EXECUTED, day, price, qty)

        # ---- 2. CLOSE: mark to market ----------------------------------------
        for sym, close in zip(today["symbol"], today["close"]):
            if _valid_price(close):
                last_close[sym] = float(close)
        # A held stock with no bar today (rare gap) keeps its last known close.
        for sym, pos in positions.items():
            pos.last_price = last_close.get(sym, pos.last_price)
        invested = sum(p.market_value for p in positions.values())
        prev_equity = cash + invested
        curve.append({"date": day, "cash": cash, "invested_value": invested,
                      "total_equity": prev_equity, "positions": len(positions)})

        # ---- 3. CLOSE: today's signals become orders for the next trading day --
        for sym, buy, sell in zip(today["symbol"], today["buy_signal"], today["sell_signal"]):
            if buy or sell:
                side = "BUY" if buy else "SELL"
                signal_log.append({"signal_date": day, "symbol": sym, "side": side,
                                   "status": None, "execution_date": None,
                                   "execution_price": None, "quantity": None})
                pending[sym] = _Order(len(signal_log) - 1, sym, side, day)

    for order in pending.values():  # signals on a stock's last available row
        resolve(order, NO_NEXT_DAY)

    equity_curve = pd.DataFrame(
        curve, columns=["date", "cash", "invested_value", "total_equity", "positions"]
    )
    equity_curve["drawdown"] = drawdown_series(equity_curve["total_equity"])

    signals = pd.DataFrame(signal_log, columns=["signal_date", "symbol", "side", "status",
                                                "execution_date", "execution_price", "quantity"])
    metrics = compute_metrics(trades, equity_curve, config.initial_capital, len(positions))
    metrics["signals"] = len(signals)
    metrics["signals_executed"] = int((signals["status"] == EXECUTED).sum())

    if benchmark is not None and not equity_curve.empty:
        _add_benchmark(equity_curve, metrics, benchmark, config.initial_capital)

    return BacktestResult(
        config=config,
        trades=trades,
        executions=executions,
        signals=signals,
        equity_curve=equity_curve,
        metrics=metrics,
        open_positions=list(positions.values()),
        strategy_frame=df.sort_values(["symbol", "date"], kind="stable").reset_index(drop=True),
    )


def _prepare(df: pd.DataFrame) -> pd.DataFrame:
    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"backtest: missing required column(s) {missing}; got {list(df.columns)}")

    dupes = df.duplicated(subset=["symbol", "date"])
    if dupes.any():
        first = df.loc[dupes, ["symbol", "date"]].iloc[0]
        raise ValueError(
            f"backtest: {int(dupes.sum())} duplicate (symbol, date) row(s), "
            f"e.g. {first['symbol']} {pd.Timestamp(first['date']).date()}"
        )

    # Only the columns the engine needs; this is a new frame, so the input is never mutated.
    data = df[list(REQUIRED_COLUMNS)].copy()
    data["date"] = pd.to_datetime(data["date"])
    data["buy_signal"] = data["buy_signal"].fillna(False).astype(bool)
    data["sell_signal"] = data["sell_signal"].fillna(False).astype(bool)

    both = data["buy_signal"] & data["sell_signal"]
    if both.any():
        row = data.loc[both].iloc[0]
        raise ValueError(f"backtest: BUY and SELL on the same row, e.g. {row['symbol']} "
                         f"{row['date'].date()}")
    return data.sort_values(["date", "symbol"], kind="stable").reset_index(drop=True)


def _valid_price(price) -> bool:
    return price is not None and not pd.isna(price) and math.isfinite(price) and price > 0


def _close_trade(pos: Position, day: pd.Timestamp, day_index: int,
                 exit_price: float, exit_cost: float) -> Trade:
    gross = (exit_price - pos.entry_price) * pos.quantity
    costs = pos.entry_cost + exit_cost
    net = gross - costs
    spent = pos.entry_price * pos.quantity + pos.entry_cost
    return Trade(
        symbol=pos.symbol,
        entry_date=pos.entry_date,
        entry_price=pos.entry_price,
        exit_date=day,
        exit_price=exit_price,
        quantity=pos.quantity,
        gross_pnl=gross,
        transaction_cost=costs,
        net_pnl=net,
        return_pct=net / spent,
        holding_days=day_index - pos.entry_day_index,
    )


def _add_benchmark(curve: pd.DataFrame, metrics: dict, benchmark: pd.Series,
                   initial_capital: float) -> None:
    """Buy-and-hold of the given price series, from the first backtest day's close."""
    prices = benchmark.copy()
    prices.index = pd.to_datetime(prices.index)
    # Last known price on or before each backtest day (forward-fill only looks backwards).
    aligned = prices.sort_index().reindex(curve["date"], method="ffill").to_numpy()
    first = aligned[0]
    if not _valid_price(first):
        return
    curve["benchmark_equity"] = initial_capital * aligned / first
    metrics["benchmark_total_return"] = float(curve["benchmark_equity"].iloc[-1] / initial_capital - 1)
    metrics["benchmark_max_drawdown"] = max_drawdown(curve["benchmark_equity"])
