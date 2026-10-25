import numpy as np
import pandas as pd
import pytest

from src.data.target import add_medium_term_target

from .conftest import make_bars


def frame(closes, dates=None, symbol="RELIANCE.NS") -> pd.DataFrame:
    if dates is None:
        dates = pd.bdate_range("2026-01-05", periods=len(closes))
    return pd.DataFrame({"date": pd.to_datetime(dates), "symbol": symbol, "close": closes})


def path(today: float, future: list[float], tail: int = 0) -> list[float]:
    """Today's close, then the future path, then `tail` extra rows."""
    return [today] + future + [today] * tail


# 1. Correct maximum future return ------------------------------------------

def test_max_future_return_over_next_horizon_rows():
    closes = [100.0, 103.0, 99.0, 106.0, 101.0, 95.0, 120.0]
    out = add_medium_term_target(frame(closes), horizon=4)
    # t=0 window = rows 1..4 = [103, 99, 106, 101] -> max 106 (row 6's 120 is outside)
    assert out.loc[0, "future_max_return_4d"] == pytest.approx(0.06)
    # t=2 window = rows 3..6 = [106, 101, 95, 120] -> max 120
    assert out.loc[2, "future_max_return_4d"] == pytest.approx(120 / 99 - 1)


def test_today_close_is_not_in_the_window():
    # Today is the highest close; every future close is lower.
    closes = path(100.0, [90.0] * 60)
    out = add_medium_term_target(frame(closes))
    assert out.loc[0, "future_max_return_60d"] == pytest.approx(-0.10)
    assert out.loc[0, "target"] == 0


def test_return_can_be_negative_when_stock_only_falls():
    closes = path(100.0, [99.0, 97.0, 95.0, 96.0])
    out = add_medium_term_target(frame(closes), horizon=4)
    assert out.loc[0, "future_max_return_4d"] == pytest.approx(-0.01)


# 2-4. Target values -------------------------------------------------------

def test_spec_example_reaches_eight_percent():
    future = [101.0] * 30 + [108.0] + [102.0] * 29
    out = add_medium_term_target(frame(path(100.0, future)))
    assert out.loc[0, "future_max_return_60d"] == pytest.approx(0.08)
    assert out.loc[0, "target"] == 1


def test_spec_example_only_five_percent():
    future = [101.0] * 30 + [105.0] + [102.0] * 29
    out = add_medium_term_target(frame(path(100.0, future)))
    assert out.loc[0, "future_max_return_60d"] == pytest.approx(0.05)
    assert out.loc[0, "target"] == 0


def test_rises_above_threshold_then_falls_back_is_still_one():
    # Spec: day 20 = 104, day 35 = 112, day 50 = 109, day 60 = 103.
    future = [100.0] * 60
    future[19], future[34], future[49], future[59] = 104.0, 112.0, 109.0, 103.0
    out = add_medium_term_target(frame(path(100.0, future)))
    assert out.loc[0, "future_max_return_60d"] == pytest.approx(0.12)
    assert out.loc[0, "target"] == 1
    # Ending only +3% would have failed a "close in 60 days" target.
    assert future[-1] / 100.0 - 1 < 0.07


@pytest.mark.parametrize(
    "today, best, expected",
    [
        (100.0, 107.0, 1.0),    # exactly +7% counts (">= 7%")
        (105.0, 112.35, 1.0),   # exactly +7%, but computes as 0.06999999999999984
        (100.0, 106.95, 0.0),   # one NSE tick (0.05) short
    ],
)
def test_threshold_is_inclusive_and_float_safe(today, best, expected):
    out = add_medium_term_target(frame(path(today, [best] + [today] * 59)))
    assert out.loc[0, "target"] == expected


# 5. Incomplete future windows ---------------------------------------------

def test_exactly_last_horizon_rows_are_nan_not_zero():
    out = add_medium_term_target(frame([100.0 + i for i in range(75)]))
    unavailable = out["target"].isna()
    assert unavailable.tolist() == [False] * 15 + [True] * 60
    assert out["future_max_return_60d"].isna().tolist() == unavailable.tolist()
    assert not (out.loc[unavailable, "target"] == 0).any()


def test_series_shorter_than_horizon_is_all_nan():
    out = add_medium_term_target(frame([100.0] * 40))
    assert out["target"].isna().all()


def test_nan_close_in_window_gives_nan_not_partial_max():
    closes = path(100.0, [101.0] * 3 + [np.nan] + [101.0] * 56)
    out = add_medium_term_target(frame(closes))
    assert np.isnan(out.loc[0, "target"])


# 6. Weekends/holidays -----------------------------------------------------

def test_weekend_and_holiday_gaps_use_rows_not_calendar_days():
    # Real NSE-like dates: weekends absent, plus a mid-week holiday removed.
    dates = pd.bdate_range("2026-01-05", periods=8).delete(6)  # drop Tue 2026-01-13
    closes = [100.0, 101.0, 102.0, 103.0, 104.0, 110.0, 105.0]
    out = add_medium_term_target(frame(closes, dates), horizon=5, threshold=0.07)

    assert len(out) == len(closes)  # no rows invented
    # t=0 (Mon 5th) -> next 5 rows are 6th..9th and Mon 12th (7 calendar days on):
    assert out.loc[0, "future_max_return_5d"] == pytest.approx(110 / 100 - 1)
    # t=1 (Tue 6th) -> next 5 rows reach Wed 14th, skipping the holiday:
    assert out.loc[1, "future_max_return_5d"] == pytest.approx(110 / 101 - 1)
    assert out["target"].isna().sum() == 5


# 7. Multiple symbols --------------------------------------------------------

def test_symbols_are_handled_independently():
    a = frame([100.0] * 65, symbol="A.NS")       # flat: never +7%
    b = frame([50.0] * 5 + [500.0] * 60, symbol="B.NS")
    out = add_medium_term_target(pd.concat([b, a]))  # B first, interleaved order

    assert out["symbol"].tolist() == ["A.NS"] * 65 + ["B.NS"] * 65
    got_a = out[out.symbol == "A.NS"]
    assert got_a["target"].dropna().eq(0).all()  # B's 500s never leak into A
    assert got_a["target"].isna().sum() == 60
    assert out[out.symbol == "B.NS"]["target"].iloc[0] == 1


# 8. Purity ------------------------------------------------------------------

def test_input_not_mutated_and_columns_kept():
    df = make_bars("RELIANCE.NS", days=70)
    before = df.copy(deep=True)
    out = add_medium_term_target(df)

    pd.testing.assert_frame_equal(df, before)
    assert list(out.columns) == list(df.columns) + ["future_max_return_60d", "target"]
    pd.testing.assert_frame_equal(out[df.columns], df)


def test_output_is_chronological_even_if_input_is_not():
    closes = [100.0 + i for i in range(10)]
    out = add_medium_term_target(frame(closes).iloc[::-1], horizon=3)
    assert out["date"].is_monotonic_increasing
    assert out.loc[0, "future_max_return_3d"] == pytest.approx(103 / 100 - 1)


# 9. Errors ----------------------------------------------------------------

@pytest.mark.parametrize("col", ["date", "symbol", "close"])
def test_missing_required_column_raises_clear_error(col):
    df = frame([100.0] * 70).drop(columns=col)
    with pytest.raises(ValueError, match=f"missing required column.*'{col}'"):
        add_medium_term_target(df)


def test_duplicate_dates_raise():
    df = frame([100.0] * 70)
    with pytest.raises(ValueError, match="duplicate"):
        add_medium_term_target(pd.concat([df, df.iloc[[3]]]))


def test_invalid_horizon_raises():
    with pytest.raises(ValueError, match="horizon"):
        add_medium_term_target(frame([100.0] * 5), horizon=0)


# 10. Custom horizon and threshold -------------------------------------------

def test_custom_horizon_and_threshold():
    closes = [100.0, 102.0, 104.0, 111.0, 100.0, 100.0]
    out = add_medium_term_target(frame(closes), horizon=2, threshold=0.03)

    assert "future_max_return_2d" in out.columns
    # t=0 window rows 1..2 -> max 104 -> +4% >= 3% -> 1 (the 111 on row 3 is outside)
    assert out.loc[0, "future_max_return_2d"] == pytest.approx(0.04)
    assert out.loc[0, "target"] == 1
    # same data with a 5% threshold -> 0
    assert add_medium_term_target(frame(closes), horizon=2, threshold=0.05).loc[0, "target"] == 0
    assert out["target"].isna().sum() == 2
