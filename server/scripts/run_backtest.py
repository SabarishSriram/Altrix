"""Backtest the EMA20/EMA50 baseline strategy on the locally stored NIFTY 100 data.

Usage:
    python scripts/run_backtest.py
    python scripts/run_backtest.py --capital 500000 --cost 0.002 --weight 0.05
    python scripts/run_backtest.py --symbols RELIANCE.NS TCS.NS INFY.NS

Reads data/processed/ (run scripts/download_data.py first), never downloads.
Results are written to data/results/<name>/ as CSV + JSON for later use by a frontend.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.backtest import run_backtest  # noqa: E402
from src.data import ParquetStore, load_clean  # noqa: E402

PROCESSED_DIR = ROOT / "data" / "processed"
RESULTS_DIR = ROOT / "data" / "results"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--capital", type=float, default=100_000, help="initial capital in INR (default 100000)")
    parser.add_argument("--cost", type=float, default=0.001, help="transaction cost per trade (default 0.001 = 0.1%%)")
    parser.add_argument("--weight", type=float, default=0.10, help="max portfolio weight per position (default 0.10)")
    parser.add_argument("--symbols", nargs="*", help="only these tickers (default: all stored)")
    parser.add_argument("--name", default="baseline_sma", help="results folder name (default baseline_sma)")
    args = parser.parse_args()

    store = ParquetStore(PROCESSED_DIR)
    if not store.symbols():
        print(f"No data in {PROCESSED_DIR}. Run: python scripts/download_data.py")
        return 1

    # Clean data: Yahoo holiday placeholders and filler bars removed, never filled.
    cleaned = load_clean(store, args.symbols)
    df = pd.concat([r.data for r in cleaned.values()], ignore_index=True)

    result = run_backtest(df, initial_capital=args.capital, transaction_cost=args.cost,
                          max_position_weight=args.weight)
    m = result.metrics

    pct = lambda x: "n/a" if x is None else f"{x:+.2%}"
    print("=" * 56)
    print(f"Baseline EMA20/EMA50 backtest  ({len(cleaned)} stocks)")
    print("=" * 56)
    print(f"Period:               {m['start_date']} -> {m['end_date']} ({m['trading_days']} trading days)")
    print(f"Initial capital:      Rs {m['initial_capital']:,.0f}")
    print(f"Final equity:         Rs {m['final_equity']:,.0f}")
    print(f"Total return:         {pct(m['total_return'])}")
    print(f"CAGR:                 {pct(m['cagr'])}")
    print(f"Max drawdown:         {pct(m['max_drawdown'])}")
    print(f"Completed trades:     {m['completed_trades']}  "
          f"(won {m['winning_trades']}, lost {m['losing_trades']})")
    print(f"Win rate:             {m['win_rate']:.1%}")
    print(f"Avg trade return:     {pct(m['avg_trade_return'])}")
    avg_hold = m["avg_holding_days"]
    print(f"Avg holding period:   {'n/a' if avg_hold is None else f'{avg_hold:.0f} trading days'}")
    print(f"Transaction costs:    Rs {m['total_transaction_costs']:,.0f} (completed trades)")
    print(f"Open positions:       {m['open_positions']}")
    status = result.signals["status"].value_counts()
    print(f"Signals:              {m['signals']}  " + ", ".join(f"{k} {v}" for k, v in status.items()))

    out = RESULTS_DIR / args.name
    out.mkdir(parents=True, exist_ok=True)
    result.trades_frame().to_csv(out / "trades.csv", index=False)
    result.executions_frame().to_csv(out / "executions.csv", index=False)
    result.signals.to_csv(out / "signals.csv", index=False)
    result.equity_curve.to_csv(out / "equity_curve.csv", index=False)
    result.open_positions_frame().to_csv(out / "open_positions.csv", index=False)
    config = {"initial_capital": args.capital, "transaction_cost": args.cost,
              "max_position_weight": args.weight, "symbols": sorted(cleaned)}
    (out / "metrics.json").write_text(json.dumps({"config": config, "metrics": m}, indent=2))
    print(f"\nResults saved to {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
