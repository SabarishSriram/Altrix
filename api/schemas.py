"""Response models. Dates are ISO strings (YYYY-MM-DD, IST calendar dates); prices in INR.

Fraction vs percent: `daily_change_pct` is in percent (1.25 = +1.25%). Backtest
returns keep the backtester's convention of decimal fractions (0.05 = +5%).
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

Signal = Literal["BUY", "SELL", "HOLD", "INSUFFICIENT_DATA"]
Crossover = Literal["BUY", "SELL"]


class StrategyInfo(BaseModel):
    name: str
    short_window: int
    long_window: int
    buy_rule: str
    sell_rule: str


class DataSourceInfo(BaseModel):
    provider: str
    frequency: str
    real_time: bool
    universe: str
    notes: list[str]


class StockScan(BaseModel):
    symbol: str
    name: str | None
    date: str  # the stock's latest bar
    close: float | None
    previous_close: float | None  # the stock's previous stored bar (after cleaning)
    previous_date: str | None
    daily_change_pct: float | None
    sma20: float | None
    sma50: float | None
    sma_difference: float | None  # sma20 - sma50
    signal: Signal
    signal_date: str | None  # set only for BUY/SELL on the scan date
    last_crossover: Crossover | None
    last_crossover_date: str | None
    note: str | None


class FailedSymbol(BaseModel):
    symbol: str
    reason: str


class ScannerResponse(BaseModel):
    data_as_of: str | None
    scanned_at: str  # when the API computed this scan (UTC ISO timestamp), not a market date
    is_stale: bool
    universe: str
    universe_size: int
    scanned_count: int
    buy_count: int
    sell_count: int
    hold_count: int
    insufficient_count: int
    failed_symbols: list[FailedSymbol]
    strategy: StrategyInfo
    data_source: DataSourceInfo
    stocks: list[StockScan]


class HistoryPoint(BaseModel):
    date: str
    open: float | None
    high: float | None
    low: float | None
    close: float | None
    volume: int | None
    sma20: float | None
    sma50: float | None
    signal: Crossover | None  # the strategy's crossover on this day, if any


class HistoryResponse(BaseModel):
    symbol: str
    name: str | None
    data_as_of: str | None
    start: str | None
    end: str | None
    total_bars: int  # bars in the stock's full stored history
    stock: StockScan
    crossovers: list[HistoryPoint]  # every BUY/SELL in the returned range, oldest first
    points: list[HistoryPoint]


class RecentCrossover(BaseModel):
    date: str
    symbol: str
    name: str | None
    signal: Crossover
    close: float | None
    sma20: float | None
    sma50: float | None


class DailySignalCount(BaseModel):
    date: str
    buy: int
    sell: int


class RecentSignalsResponse(BaseModel):
    data_as_of: str | None
    trading_days: int
    crossovers: list[RecentCrossover]  # newest first
    daily_counts: list[DailySignalCount]  # oldest first, one row per trading day


class EquityPoint(BaseModel):
    date: str
    total_equity: float
    cash: float
    invested_value: float
    positions: int
    drawdown: float


class TradeRecord(BaseModel):
    symbol: str
    entry_date: str
    entry_price: float
    exit_date: str
    exit_price: float
    quantity: int
    gross_pnl: float
    transaction_cost: float
    net_pnl: float
    return_pct: float  # fraction
    holding_days: int


class OpenPositionRecord(BaseModel):
    symbol: str
    quantity: int
    entry_date: str
    entry_price: float
    last_price: float
    market_value: float
    unrealized_pnl: float


class BacktestConfigOut(BaseModel):
    initial_capital: float
    transaction_cost: float
    max_position_weight: float
    start: str | None
    end: str | None


class BacktestResponse(BaseModel):
    config: BacktestConfigOut
    data_start: str
    data_end: str
    symbols: int
    metrics: dict[str, float | int | str | None]
    equity_curve: list[EquityPoint]
    trades: list[TradeRecord]
    open_positions: list[OpenPositionRecord]


class RefreshStatus(BaseModel):
    state: Literal["idle", "running", "succeeded", "failed"]
    kind: Literal["rescan", "download"] | None
    started_at: str | None
    finished_at: str | None
    message: str | None
    updated: int | None = None
    up_to_date: int | None = None
    new_rows: int | None = None
    failed: list[FailedSymbol] = []


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    version: str
    data_available: bool
    stored_symbols: int
    data_updated_at: str | None  # last time a Parquet file changed (UTC), not a market date
    scan_cached: bool
    data_as_of: str | None
    offline_mode: bool
    refresh: RefreshStatus


class BacktestDefaults(BaseModel):
    initial_capital: float
    transaction_cost: float
    max_position_weight: float


class MetaResponse(BaseModel):
    version: str
    strategy: StrategyInfo
    data_source: DataSourceInfo
    offline_mode: bool
    backtest_defaults: BacktestDefaults
