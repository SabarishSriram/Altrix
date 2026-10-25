import pytest
import numpy as np
import pandas as pd

from src.data.validator import build_trading_calendar, check_schema, validate

from .conftest import make_bars


def test_valid_data_passes(bars):
    report = validate(bars, "TEST.NS")
    assert report.ok, report.errors
    assert report.warnings == []
    assert report.rows == 10


# --- schema -----------------------------------------------------------------

def test_schema_ok(bars):
    assert check_schema(bars) == []


def test_schema_wrong_columns(bars):
    errors = check_schema(bars.drop(columns="volume"))
    assert errors and "columns" in errors[0]


def test_schema_wrong_dtype(bars):
    bad = bars.assign(close=bars["close"].astype("float32"))
    assert any("close" in e for e in check_schema(bad))


def test_empty_frame_is_error(bars):
    assert not validate(bars.iloc[0:0], "TEST.NS").ok


# --- duplicates & ordering --------------------------------------------------

def test_duplicate_dates_detected(bars):
    dup = pd.concat([bars, bars.iloc[[3]]]).sort_values("date").reset_index(drop=True)
    report = validate(dup, "TEST.NS")
    assert any("duplicate" in e for e in report.errors)


def test_unsorted_dates_detected(bars):
    report = validate(bars.iloc[::-1].reset_index(drop=True), "TEST.NS")
    assert any("sorted" in e for e in report.errors)


# --- OHLCV values -----------------------------------------------------------

def test_missing_values_detected(bars):
    bars.loc[2, "close"] = np.nan
    bars.loc[4, "volume"] = pd.NA
    report = validate(bars, "TEST.NS")
    assert any("'close'" in e for e in report.errors)
    assert any("'volume'" in e for e in report.errors)


def test_high_below_close_detected(bars):
    bars.loc[1, "high"] = bars.loc[1, "close"] - 5
    assert any("violate" in e for e in validate(bars, "TEST.NS").errors)


def test_low_above_open_detected(bars):
    bars.loc[1, "low"] = bars.loc[1, "open"] + 5
    assert any("violate" in e for e in validate(bars, "TEST.NS").errors)


def test_non_positive_price_detected(bars):
    bars.loc[0, ["open", "low"]] = [0.0, 0.0]
    assert any("non-positive" in e for e in validate(bars, "TEST.NS").errors)


def test_negative_volume_detected(bars):
    bars.loc[0, "volume"] = -1
    assert any("negative volume" in e for e in validate(bars, "TEST.NS").errors)


def test_zero_volume_is_warning_not_error(bars):
    bars.loc[0, "volume"] = 0
    report = validate(bars, "TEST.NS")
    assert report.ok
    assert any("zero-volume" in w for w in report.warnings)


# --- missing dates vs holidays ----------------------------------------------

def test_holiday_is_not_flagged_but_gap_is():
    days = pd.bdate_range("2024-01-01", periods=10)
    holiday = days[4]  # nobody traded that weekday -> exchange holiday
    trading = days.drop(holiday)

    peers = [make_bars(f"P{i}.NS", dates=trading) for i in range(4)]
    gappy = make_bars("GAP.NS", dates=trading.drop(trading[6]))  # one stock misses a trading day

    calendar = build_trading_calendar(peers + [gappy])
    assert holiday not in calendar
    assert pd.Timestamp("2024-01-06") not in calendar  # weekend

    clean = validate(peers[0], "P0.NS", calendar)
    assert clean.ok and clean.warnings == []
    assert clean.holidays_skipped == 1

    report = validate(gappy, "GAP.NS", calendar)
    assert report.ok  # a gap is a warning, data is not "wrong"
    assert report.suspicious_missing_dates == [trading[6]]


def test_yahoo_zero_volume_holiday_placeholder():
    """Yahoo sometimes emits a zero-volume bar for every stock on an exchange holiday."""
    days = pd.bdate_range("2024-01-01", periods=10)
    holiday = days[4]
    stocks = []
    for i in range(4):
        df = make_bars(f"P{i}.NS", dates=days)
        df.loc[df["date"] == holiday, "volume"] = 0  # placeholder bar
        stocks.append(df)
    no_placeholder = make_bars("CLEAN.NS", dates=days.drop(holiday))

    calendar = build_trading_calendar(stocks + [no_placeholder])
    assert holiday not in calendar

    clean = validate(no_placeholder, "CLEAN.NS", calendar)
    assert clean.warnings == []  # not penalised for lacking the fake bar

    report = validate(stocks[0], "P0.NS", calendar)
    assert report.ok
    assert report.non_trading_day_bars == [holiday]
    assert not any("on trading days" in w for w in report.warnings)


def test_special_weekend_session_is_a_trading_day():
    days = pd.bdate_range("2024-01-01", periods=5).append(pd.DatetimeIndex(["2024-01-06"]))  # Saturday
    stocks = [make_bars(f"P{i}.NS", dates=days) for i in range(3)]
    calendar = build_trading_calendar(stocks)
    assert pd.Timestamp("2024-01-06") in calendar
    assert validate(stocks[0], "P0.NS", calendar).warnings == []


def test_late_listing_not_flagged_for_dates_before_listing():
    days = pd.bdate_range("2024-01-01", periods=20)
    peers = [make_bars(f"P{i}.NS", dates=days) for i in range(3)]
    newcomer = make_bars("NEW.NS", dates=days[10:])
    calendar = build_trading_calendar(peers + [newcomer])
    assert validate(newcomer, "NEW.NS", calendar).suspicious_missing_dates == []


# --- corporate actions -----------------------------------------------------------

def test_large_one_day_drop_flagged_as_possible_corporate_action(bars):
    df = bars.copy()
    df.loc[6:, ["open", "high", "low", "close"]] *= 0.35  # a VEDL-style unadjusted demerger: -65%
    report = validate(df, "TEST.NS")
    assert report.ok  # a warning to verify, never an error or a fix
    assert report.corporate_action_suspects == [df.loc[6, "date"]]
    assert any("possible unadjusted split/demerger" in w for w in report.warnings)


def test_ordinary_fall_is_not_flagged(bars):
    df = bars.copy()
    df.loc[6:, ["open", "high", "low", "close"]] *= 0.7  # -30%: large, but above the -35% threshold
    report = validate(df, "TEST.NS")
    assert report.corporate_action_suspects == [] and report.warnings == []


def test_large_price_drops_lists_the_events(bars):
    from src.data.validator import large_price_drops

    df = bars.copy()
    df.loc[3:, "close"] *= 0.5
    drops = large_price_drops(df)
    assert drops["date"].tolist() == [df.loc[3, "date"]]
    assert drops["return"].iloc[0] == pytest.approx(df.loc[3, "close"] / df.loc[2, "close"] - 1)
