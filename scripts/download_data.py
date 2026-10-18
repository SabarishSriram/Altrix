"""Download / update daily OHLCV for the current NIFTY 100 universe.

Usage:
    python scripts/download_data.py                 # incremental (default)
    python scripts/download_data.py --full-refresh  # re-download everything
    python scripts/download_data.py --years 5 --symbols RELIANCE.NS TCS.NS
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.data import (  # noqa: E402
    Nifty100Universe,
    ParquetStore,
    YahooFinanceProvider,
    download_all,
    validate_all,
)
from src.data.downloader import default_end, default_start  # noqa: E402

RAW_DIR = ROOT / "data" / "raw"
PROCESSED_DIR = ROOT / "data" / "processed"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--years", type=int, default=10, help="history to fetch on first download (default 10)")
    parser.add_argument("--full-refresh", action="store_true", help="ignore stored files and re-download")
    parser.add_argument("--symbols", nargs="*", help="only these Yahoo tickers (default: NIFTY 100)")
    parser.add_argument("-v", "--verbose", action="store_true", help="show per-symbol progress")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
    )
    # yfinance logs its own errors loudly; our summary reports them instead.
    logging.getLogger("yfinance").setLevel(logging.CRITICAL)

    universe = Nifty100Universe(cache_path=RAW_DIR / "nifty100_constituents.csv").get_constituents()
    symbols = args.symbols or [u["symbol"] for u in universe]
    start, end = default_start(args.years), default_end()

    print(f"NIFTY 100 stocks found: {len(universe)}")
    print(f"Requesting {len(symbols)} symbol(s), {start} -> {end} (end exclusive) ...")

    store = ParquetStore(PROCESSED_DIR)
    results = download_all(symbols, YahooFinanceProvider(), store, start, end, args.full_refresh)
    reports = validate_all(symbols, store)

    failed = [r for r in results if r.status == "failed"]
    ok = [r for r in results if r.status != "failed"]
    counts = {s: sum(r.status == s for r in results) for s in ("downloaded", "updated", "up_to_date")}

    frames = [store.load(s) for s in symbols if store.path(s).exists()]
    total_rows = sum(len(f) for f in frames)
    first = min((f["date"].min() for f in frames if not f.empty), default=None)
    last = max((f["date"].max() for f in frames if not f.empty), default=None)

    print()
    print("=" * 56)
    print(f"NIFTY 100 stocks found: {len(universe)}")
    print(f"Stocks downloaded:      {len(ok)}  "
          f"(new {counts['downloaded']}, updated {counts['updated']}, up to date {counts['up_to_date']})")
    print(f"Failed:                 {len(failed)}")
    print(f"New rows this run:      {sum(r.new_rows for r in results):,}")
    print(f"Total rows:             {total_rows:,}")
    if first is not None:
        print(f"Date range:             {first.date()} -> {last.date()}")
    print(f"Stored in:              {PROCESSED_DIR}")
    print("=" * 56)

    for r in failed:
        print(f"  FAILED  {r.symbol}: {r.error}")

    # Yahoo holiday placeholder bars affect almost every symbol, so report them once.
    placeholder_dates = sorted({d for rep in reports for d in rep.non_trading_day_bars})
    stock_warnings = {
        rep.symbol: [w for w in rep.warnings if "non-trading days" not in w] for rep in reports
    }
    invalid = [rep for rep in reports if not rep.ok]
    flagged = [rep for rep in reports if rep.ok and stock_warnings[rep.symbol]]

    print(f"\nValidation: {len(reports) - len(invalid) - len(flagged)} clean, "
          f"{len(flagged)} with stock-specific warnings, {len(invalid)} with errors")
    if placeholder_dates:
        n_syms = sum(bool(rep.non_trading_day_bars) for rep in reports)
        print(f"  NOTE     Yahoo placeholder bars on {len(placeholder_dates)} market holiday(s) "
              f"in {n_syms} symbol(s): {', '.join(str(d.date()) for d in placeholder_dates)}")
    for rep in invalid:
        print(f"  ERROR    {rep.symbol}: {'; '.join(rep.errors)}")
    for rep in flagged:
        print(f"  WARNING  {rep.symbol}: {'; '.join(stock_warnings[rep.symbol])}")

    return 1 if failed or invalid else 0


if __name__ == "__main__":
    sys.exit(main())
