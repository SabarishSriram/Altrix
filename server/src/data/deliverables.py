"""Optional NSE deliverable volume from the daily "full bhavcopy" (sec_bhavdata_full_DDMMYYYY.csv).

DELIV_QTY is the number of shares actually delivered (taken home, not squared
off intraday); DELIV_PER is that as a percentage of traded quantity. A delivery
surge on a high delivery share is a classic sign of institutional buying.

    parse_bhavdata      one day's CSV text -> date, symbol (.NS), deliv_qty, deliv_per (EQ series only)
    fetch_bhavdata      download one day (None on 404: weekends and exchange holidays)
    DeliverableStore    all fetched days in one Parquet file
    download_deliverables  fetch the weekdays in a range that are not stored yet
    add_delivery_signals   deliv_spike_ratio = deliv_qty / mean(deliv_qty over the stock's last 20 rows)
                           delivery_spike    = deliv_spike_ratio >= 2.0 and deliv_per >= 55

Entirely optional: nothing else in Altrix needs this data. NSE blocks some
cloud IPs and occasionally changes these archives.
"""

from __future__ import annotations

import io
import logging
import urllib.error
import urllib.request
from collections.abc import Callable
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

logger = logging.getLogger(__name__)

BHAVDATA_URL = "https://nsearchives.nseindia.com/products/content/sec_bhavdata_full_{day:%d%m%Y}.csv"
# NSE rejects requests without a browser-like User-Agent.
_HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

DELIVERY_WINDOW = 20
DELIVERY_SPIKE = 2.0
DELIVERY_MIN_PER = 55.0  # DELIV_PER is already a percentage
COLUMNS = ["date", "symbol", "deliv_qty", "deliv_per"]


class DeliverableError(Exception):
    """A bhavdata file could not be downloaded or parsed."""


def bhavdata_url(day: date) -> str:
    return BHAVDATA_URL.format(day=day)


def parse_bhavdata(text: str, suffix: str = ".NS") -> pd.DataFrame:
    """Parse one sec_bhavdata_full CSV. Keeps SERIES == "EQ"; "-" becomes NaN."""
    try:
        df = pd.read_csv(io.StringIO(text), skipinitialspace=True, dtype=str)
    except Exception as exc:
        raise DeliverableError(f"could not parse bhavdata CSV: {exc}") from exc
    df.columns = [c.strip() for c in df.columns]
    needed = {"SYMBOL", "SERIES", "DATE1", "DELIV_QTY", "DELIV_PER"}
    if not needed <= set(df.columns):
        raise DeliverableError(f"unexpected bhavdata columns: {list(df.columns)}")

    df = df[df["SERIES"].str.strip() == "EQ"]
    out = pd.DataFrame({
        "date": pd.to_datetime(df["DATE1"].str.strip(), format="%d-%b-%Y"),
        "symbol": df["SYMBOL"].str.strip().str.upper() + suffix,
        "deliv_qty": pd.to_numeric(df["DELIV_QTY"].str.strip(), errors="coerce"),
        "deliv_per": pd.to_numeric(df["DELIV_PER"].str.strip(), errors="coerce"),
    })
    return out.reset_index(drop=True)


def fetch_bhavdata(day: date, opener: Callable = urllib.request.urlopen, timeout: int = 20) -> pd.DataFrame | None:
    """One day's EQ deliverables, or None if NSE has no file for that date (404)."""
    req = urllib.request.Request(bhavdata_url(day), headers=_HEADERS)
    try:
        with opener(req, timeout=timeout) as resp:
            text = resp.read().decode("utf-8-sig")
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return None
        raise DeliverableError(f"{day}: HTTP {exc.code}") from exc
    except urllib.error.URLError as exc:
        raise DeliverableError(f"{day}: {exc.reason}") from exc
    return parse_bhavdata(text)


class DeliverableStore:
    """Every fetched day in one Parquet file (about 500 KB per year for NIFTY 100)."""

    FILENAME = "deliverables.parquet"

    def __init__(self, directory: Path):
        self.directory = Path(directory)
        self.path = self.directory / self.FILENAME

    def load(self) -> pd.DataFrame:
        if not self.path.exists():
            return pd.DataFrame({c: pd.Series(dtype=t) for c, t in
                                 zip(COLUMNS, ["datetime64[ns]", "object", "float64", "float64"])})
        return pd.read_parquet(self.path)

    def append(self, frame: pd.DataFrame) -> int:
        """Merge `frame` in (a re-fetched day replaces the stored one). Returns the new row count."""
        merged = pd.concat([self.load(), frame[COLUMNS]], ignore_index=True)
        merged = merged.drop_duplicates(["symbol", "date"], keep="last").sort_values(["symbol", "date"])
        self.directory.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".parquet.tmp")
        merged.to_parquet(tmp, index=False)
        tmp.replace(self.path)
        return len(merged)

    def dates(self) -> set[pd.Timestamp]:
        return set(self.load()["date"].unique())


def download_deliverables(
    store: DeliverableStore,
    start: date,
    end: date,
    symbols: set[str] | None = None,
    fetch: Callable[[date], pd.DataFrame | None] = fetch_bhavdata,
) -> dict:
    """Fetch every weekday in [start, end] that is not stored yet.

    `symbols` limits what is kept (e.g. the NIFTY 100). A failed day is
    reported and skipped; it never stops the others. Returns counts.
    """
    have = {pd.Timestamp(d).date() for d in store.dates()}
    fetched, holidays, failed = [], [], {}
    day = start
    while day <= end:
        if day.weekday() < 5 and day not in have:
            try:
                frame = fetch(day)
            except DeliverableError as exc:
                failed[day.isoformat()] = str(exc)
            else:
                # On some holidays NSE serves the previous session's file under the holiday's name.
                if frame is None or (frame["date"] != pd.Timestamp(day)).all():
                    holidays.append(day.isoformat())
                else:
                    if symbols is not None:
                        frame = frame[frame["symbol"].isin(symbols)]
                    store.append(frame)
                    fetched.append(day.isoformat())
        day += timedelta(days=1)
    return {"fetched": fetched, "no_file": holidays, "failed": failed}


def add_delivery_signals(df: pd.DataFrame) -> pd.DataFrame:
    """Add deliv_spike_ratio and delivery_spike per symbol (the stock's own rows, looking back)."""
    out = df.sort_values(["symbol", "date"], kind="stable").reset_index(drop=True)
    qty = out["deliv_qty"].astype("float64")
    avg = qty.groupby(out["symbol"], sort=False).transform(
        lambda s: s.rolling(DELIVERY_WINDOW, min_periods=DELIVERY_WINDOW).mean())
    out["deliv_spike_ratio"] = qty / avg
    out["delivery_spike"] = (out["deliv_spike_ratio"] >= DELIVERY_SPIKE) & (out["deliv_per"] >= DELIVERY_MIN_PER)
    return out
