import numpy as np
import pandas as pd
import pytest

from src.data.cleaner import clean, load_clean
from src.data.downloader import ParquetStore
from src.data.provider import SCHEMA
from src.data.validator import build_trading_calendar

from .conftest import make_bars

DAYS = pd.bdate_range("2024-01-01", periods=10)
CALENDAR = DAYS.drop(DAYS[4])  # DAYS[4] is a market holiday


def test_clean_data_is_untouched():
    df = make_bars(dates=CALENDAR)
    result = clean(df, "TEST.NS", CALENDAR)
    pd.testing.assert_frame_equal(result.data, df)
    assert result.removed == {} and result.gaps == []


def test_drops_holiday_placeholder_without_creating_gap():
    df = make_bars(dates=DAYS)
    df.loc[4, ["open", "high", "low", "close", "volume"]] = [103.0, 103.0, 103.0, 103.0, 0]
    result = clean(df, "TEST.NS", CALENDAR)
    assert DAYS[4] not in set(result.data["date"])
    assert result.removed == {"holiday": 1}
    assert result.gaps == []  # a holiday is not a gap


def test_drops_filler_bar_and_reports_gap():
    df = make_bars(dates=CALENDAR)
    prev_close = df.loc[2, "close"]
    df.loc[3, ["open", "high", "low", "close", "volume"]] = [prev_close] * 4 + [0]
    result = clean(df, "TEST.NS", CALENDAR)
    assert result.removed == {"filler": 1}
    assert result.gaps == [CALENDAR[3]]
    assert len(result.data) == len(CALENDAR) - 1


def test_keeps_zero_volume_bar_with_real_price_range():
    df = make_bars(dates=CALENDAR)
    df.loc[3, "volume"] = 0  # prices still vary within the day, so not a filler bar
    result = clean(df, "TEST.NS", CALENDAR)
    assert result.removed == {}
    assert len(result.data) == len(CALENDAR)


@pytest.mark.parametrize(
    "col, value",
    [("close", np.nan), ("volume", pd.NA), ("open", -1.0), ("high", 50.0), ("volume", -5)],
)
def test_drops_invalid_rows(col, value):
    df = make_bars(dates=CALENDAR)
    df.loc[2, col] = value
    result = clean(df, "TEST.NS", CALENDAR)
    assert result.removed == {"invalid": 1}
    assert result.gaps == [CALENDAR[2]]


def test_dedupes_sorts_and_never_fills():
    df = make_bars(dates=CALENDAR)
    shuffled = pd.concat([df.iloc[::-1], df.iloc[[0]]]).reset_index(drop=True)
    shuffled = shuffled[shuffled["date"] != CALENDAR[5]]  # a genuine gap
    result = clean(shuffled, "TEST.NS", CALENDAR)

    out = result.data
    assert out["date"].is_monotonic_increasing and not out["date"].duplicated().any()
    assert result.removed == {"duplicate": 1}
    assert result.gaps == [CALENDAR[5]]
    assert CALENDAR[5] not in set(out["date"])  # gap is not filled
    assert {c: str(t) for c, t in out.dtypes.items()} == SCHEMA


def test_load_clean_uses_whole_universe_calendar(tmp_path):
    store = ParquetStore(tmp_path)
    for i in range(3):
        store.save(f"P{i}.NS", make_bars(f"P{i}.NS", dates=CALENDAR))
    gappy = make_bars("GAP.NS", dates=CALENDAR.drop(CALENDAR[6]))
    store.save("GAP.NS", gappy)

    result = load_clean(store, ["GAP.NS"])["GAP.NS"]
    assert result.gaps == [CALENDAR[6]]
    assert set(load_clean(store)) == {"GAP.NS", "P0.NS", "P1.NS", "P2.NS"}

    with pytest.raises(KeyError):
        load_clean(store, ["NOPE.NS"])
