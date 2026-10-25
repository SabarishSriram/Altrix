"""Download NSE deliverable volume (sec_bhavdata_full) for the NIFTY 100. Optional.

Usage:
    python scripts/download_deliverables.py              # last 45 calendar days, only days not stored yet
    python scripts/download_deliverables.py --days 90

One request per missing weekday; weekends are skipped and exchange holidays
return no file. Stores data/deliverables/deliverables.parquet (override with
ALTRIX_DELIVERABLES_DIR). The Smart Money tab shows delivery columns when this
file exists. deliv_spike_ratio needs 20 stored trading days per stock.
"""

from __future__ import annotations

import argparse
import sys
from datetime import timedelta
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.scanner_ui import SNAPSHOT_NAME, deliverables_dir, raw_dir  # noqa: E402
from src.data.deliverables import DeliverableStore, download_deliverables  # noqa: E402
from src.data.universe import parse_nse_index_csv  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--days", type=int, default=45, help="calendar days to look back (default 45)")
    args = parser.parse_args()

    snapshot = raw_dir() / SNAPSHOT_NAME
    if not snapshot.exists():
        print(f"No constituent snapshot at {snapshot}. Run: python scripts/download_data.py")
        return 1
    symbols = {u["symbol"] for u in parse_nse_index_csv(snapshot.read_text(encoding="utf-8"))}

    today = pd.Timestamp.now(tz="Asia/Kolkata").date()
    start = today - timedelta(days=args.days)
    store = DeliverableStore(deliverables_dir())
    print(f"Fetching NSE deliverables for {len(symbols)} symbols, {start} -> {today} (missing days only) ...")
    result = download_deliverables(store, start, today, symbols)

    stored = store.load()
    print(f"Fetched {len(result['fetched'])} day(s); no file for {len(result['no_file'])} "
          f"(holiday, or not published yet); failed {len(result['failed'])}")
    for day, reason in result["failed"].items():
        print(f"  FAILED  {day}: {reason}")
    if not stored.empty:
        print(f"Stored {stored['date'].nunique()} trading day(s), {stored['date'].min().date()} -> "
              f"{stored['date'].max().date()}, in {store.path}")
    return 1 if result["failed"] else 0


if __name__ == "__main__":
    sys.exit(main())
