"""Data-quality checks for normalized OHLCV frames.

The validator only *reports* problems. It never fixes or fills data.

Missing dates: NSE has no free, official holiday API, so the trading calendar
is inferred from the data itself. A date on which most of the universe
traded (volume > 0) is a trading day. A trading day missing for one stock is
suspicious. A weekday on which almost nobody traded is an exchange holiday,
and any bar on such a day is reported (Yahoo emits zero-volume placeholder
bars on some holidays).
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from .provider import SCHEMA


@dataclass
class ValidationReport:
    symbol: str
    rows: int = 0
    errors: list[str] = field(default_factory=list)  # data is wrong
    warnings: list[str] = field(default_factory=list)  # data may be incomplete or odd
    
    suspicious_missing_dates: list[pd.Timestamp] = field(default_factory=list)
    holidays_skipped: int = 0  # weekdays absent from the calendar: normal, not an issue
    non_trading_day_bars: list[pd.Timestamp] = field(default_factory=list)  # bars the market didn't trade

    @property
    def ok(self) -> bool:
        return not self.errors


def build_trading_calendar(frames: list[pd.DataFrame], min_fraction: float = 0.5) -> pd.DatetimeIndex:
    """Dates on which at least `min_fraction` of the symbols that existed then traded.

    The result is an inferred NSE trading calendar: weekends and exchange
    holidays drop out because (almost) no stock traded on them. Only bars with
    volume > 0 count, because Yahoo sometimes emits zero-volume placeholder
    bars on exchange holidays. Special weekend sessions (Diwali Muhurat trading,
    Budget-day Saturdays) stay in because the whole market traded.
    """
    frames = [f for f in frames if not f.empty]
    if not frames:
        return pd.DatetimeIndex([])
    traded = [f.loc[f["volume"].fillna(0) > 0, ["date"]].drop_duplicates() for f in frames]
    present = pd.concat(traded)["date"].value_counts()
    # Count only symbols that were listed on each date (first <= d <= last).
    listed = pd.Series(0, index=present.index)
    for f in frames:
        lo, hi = f["date"].min(), f["date"].max()
        listed += (present.index >= lo) & (present.index <= hi)
    keep = present[present >= min_fraction * listed].index
    return pd.DatetimeIndex(sorted(keep))


def check_schema(df: pd.DataFrame) -> list[str]:
    errors = []
    if list(df.columns) != list(SCHEMA):
        errors.append(f"columns {list(df.columns)} != expected {list(SCHEMA)}")
        return errors
    for col, dtype in SCHEMA.items():
        if str(df[col].dtype) != dtype:
            errors.append(f"column '{col}' has dtype {df[col].dtype}, expected {dtype}")
    return errors


def validate(df: pd.DataFrame, symbol: str, calendar: pd.DatetimeIndex | None = None) -> ValidationReport:
    """Run all checks on one symbol's frame. `calendar` enables the missing-date check."""
    report = ValidationReport(symbol=symbol, rows=len(df))

    report.errors += check_schema(df)
    if report.errors or df.empty:
        if df.empty:
            report.errors.append("no rows")
        return report

    # Ordering and duplicates
    if not df["date"].is_monotonic_increasing:
        report.errors.append("dates are not sorted chronologically")
    dupes = df["date"][df["date"].duplicated()]
    if not dupes.empty:
        report.errors.append(f"{len(dupes)} duplicate date(s), e.g. {dupes.iloc[0].date()}")
    if (df["symbol"] != symbol).any():
        report.errors.append("symbol column contains other symbols")

    # Missing values
    price_cols = ["open", "high", "low", "close"]
    for col in price_cols + ["volume"]:
        n = int(df[col].isna().sum())
        if n:
            report.errors.append(f"{n} missing value(s) in '{col}'")

    # Value sanity (NaNs are already reported above, so compare on complete rows)
    full = df.dropna(subset=price_cols)
    n = int((full[price_cols] <= 0).any(axis=1).sum())
    if n:
        report.errors.append(f"{n} row(s) with non-positive prices")
    n = int((df["volume"].dropna() < 0).sum())
    if n:
        report.errors.append(f"{n} row(s) with negative volume")
    bad_ohlc = (
        (full["high"] < full[["open", "close", "low"]].max(axis=1))
        | (full["low"] > full[["open", "close", "high"]].min(axis=1))
    )
    if bad_ohlc.any():
        first = full.loc[bad_ohlc, "date"].iloc[0].date()
        report.errors.append(f"{int(bad_ohlc.sum())} row(s) violate low <= open/close <= high, e.g. {first}")

    if calendar is None or not len(calendar):
        n = int((df["volume"] == 0).sum())
        if n:
            report.warnings.append(f"{n} zero-volume bar(s)")
        return report

    # Calendar checks, within this symbol's own life span so that a stock
    # listed in 2022 is not flagged for 2016.
    lo, hi = df["date"].min(), df["date"].max()
    expected = calendar[(calendar >= lo) & (calendar <= hi)]
    report.holidays_skipped = len(pd.bdate_range(lo, hi).difference(calendar))

    missing = expected.difference(pd.DatetimeIndex(df["date"]))
    if len(missing):
        report.suspicious_missing_dates = list(missing)
        report.warnings.append(f"{len(missing)} suspicious missing trading day(s), e.g. {missing[0].date()}")

    # Bars on dates the market did not trade: usually Yahoo holiday placeholders.
    off_days = df[~df["date"].isin(calendar)]
    if not off_days.empty:
        report.non_trading_day_bars = list(off_days["date"])
        report.warnings.append(
            f"{len(off_days)} bar(s) on non-trading days (likely Yahoo holiday placeholders), "
            f"e.g. {off_days['date'].iloc[0].date()}"
        )

    # Zero volume on a real trading day: legal (e.g. a halt) but worth a look.
    n = int(((df["volume"] == 0) & df["date"].isin(calendar)).sum())
    if n:
        report.warnings.append(f"{n} zero-volume bar(s) on trading days")

    return report
