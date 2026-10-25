// Response types for the Altrix API (server/api/schemas.py). Dates are "YYYY-MM-DD"
// market dates; *_at fields are UTC timestamps of API activity, not market dates.

export type Signal = "BUY" | "SELL" | "HOLD" | "INSUFFICIENT_DATA";
export type Crossover = "BUY" | "SELL";

export interface StrategyInfo {
  name: string;
  short_window: number;
  long_window: number;
  buy_rule: string;
  sell_rule: string;
}

export interface DataSourceInfo {
  provider: string;
  frequency: string;
  real_time: boolean;
  universe: string;
  notes: string[];
}

export interface StockScan {
  symbol: string;
  name: string | null;
  date: string;
  close: number | null;
  previous_close: number | null;
  previous_date: string | null;
  /** Percent, e.g. 1.25 = +1.25%. */
  daily_change_pct: number | null;
  sma20: number | null;
  sma50: number | null;
  sma_difference: number | null;
  signal: Signal;
  signal_date: string | null;
  last_crossover: Crossover | null;
  last_crossover_date: string | null;
  note: string | null;
}

export interface FailedSymbol {
  symbol: string;
  reason: string;
}

export interface ScannerResponse {
  data_as_of: string | null;
  scanned_at: string;
  is_stale: boolean;
  universe: string;
  universe_size: number;
  scanned_count: number;
  buy_count: number;
  sell_count: number;
  hold_count: number;
  insufficient_count: number;
  failed_symbols: FailedSymbol[];
  strategy: StrategyInfo;
  data_source: DataSourceInfo;
  stocks: StockScan[];
}

export interface HistoryPoint {
  date: string;
  open: number | null;
  high: number | null;
  low: number | null;
  close: number | null;
  volume: number | null;
  sma20: number | null;
  sma50: number | null;
  signal: Crossover | null;
}

export interface HistoryResponse {
  symbol: string;
  name: string | null;
  data_as_of: string | null;
  start: string | null;
  end: string | null;
  total_bars: number;
  stock: StockScan;
  crossovers: HistoryPoint[];
  points: HistoryPoint[];
}

export interface RecentCrossover {
  date: string;
  symbol: string;
  name: string | null;
  signal: Crossover;
  close: number | null;
  sma20: number | null;
  sma50: number | null;
}

export interface DailySignalCount {
  date: string;
  buy: number;
  sell: number;
}

export interface RecentSignalsResponse {
  data_as_of: string | null;
  trading_days: number;
  crossovers: RecentCrossover[];
  daily_counts: DailySignalCount[];
}

export interface EquityPoint {
  date: string;
  total_equity: number;
  cash: number;
  invested_value: number;
  positions: number;
  /** Fraction, always <= 0. */
  drawdown: number;
}

export interface TradeRecord {
  symbol: string;
  entry_date: string;
  entry_price: number;
  exit_date: string;
  exit_price: number;
  quantity: number;
  gross_pnl: number;
  transaction_cost: number;
  net_pnl: number;
  /** Fraction. */
  return_pct: number;
  holding_days: number;
}

export interface OpenPositionRecord {
  symbol: string;
  quantity: number;
  entry_date: string;
  entry_price: number;
  last_price: number;
  market_value: number;
  unrealized_pnl: number;
}

export interface BacktestMetrics {
  start_date: string | null;
  end_date: string | null;
  trading_days: number;
  initial_capital: number;
  final_equity: number;
  total_return: number;
  cagr: number | null;
  max_drawdown: number;
  completed_trades: number;
  winning_trades: number;
  losing_trades: number;
  win_rate: number;
  avg_trade_return: number | null;
  total_net_pnl: number;
  total_transaction_costs: number;
  avg_holding_days: number | null;
  open_positions: number;
  [key: string]: number | string | null;
}

export interface BacktestParams {
  initial_capital: number;
  transaction_cost: number;
  max_position_weight: number;
  /** Lookback in years, ending on the latest stored date. */
  years: number;
}

export interface BacktestResponse {
  config: {
    initial_capital: number;
    transaction_cost: number;
    max_position_weight: number;
    start: string | null;
    end: string | null;
  };
  data_start: string;
  data_end: string;
  symbols: number;
  metrics: BacktestMetrics;
  equity_curve: EquityPoint[];
  trades: TradeRecord[];
  open_positions: OpenPositionRecord[];
}

export interface RefreshStatus {
  state: "idle" | "running" | "succeeded" | "failed";
  kind: "rescan" | "download" | null;
  started_at: string | null;
  finished_at: string | null;
  message: string | null;
  updated: number | null;
  up_to_date: number | null;
  new_rows: number | null;
  failed: FailedSymbol[];
}

export interface HealthResponse {
  status: "ok" | "degraded";
  version: string;
  data_available: boolean;
  stored_symbols: number;
  data_updated_at: string | null;
  scan_cached: boolean;
  data_as_of: string | null;
  offline_mode: boolean;
  /** False on read-only deployments: the API rejects downloads and data arrives with each redeploy. */
  downloads_enabled: boolean;
  refresh: RefreshStatus;
}

export interface MetaResponse {
  version: string;
  strategy: StrategyInfo;
  data_source: DataSourceInfo;
  offline_mode: boolean;
  downloads_enabled: boolean;
  backtest_defaults: {
    initial_capital: number;
    transaction_cost: number;
    max_position_weight: number;
  };
}
