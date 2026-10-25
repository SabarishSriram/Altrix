import numpy as np
import pandas as pd
import pytest

from src.strategy.baseline import generate_baseline_signals
from src.strategy.smart_money import add_smart_money_footprint, generate_smart_money_signals


def bars(closes, volumes=None, symbol="T.NS", highs=None, lows=None) -> pd.DataFrame:
    """Daily bars; by default high/low are close +/- 1 (so CLV = 0.5) and volume is 1000."""
    n = len(closes)
    closes = [float(c) for c in closes]
    return pd.DataFrame({
        "date": pd.bdate_range("2024-01-01", periods=n),
        "symbol": symbol,
        "open": closes,
        "high": highs if highs is not None else [c + 1 for c in closes],
        "low": lows if lows is not None else [c - 1 for c in closes],
        "close": closes,
        "volume": pd.array(volumes if volumes is not None else [1000] * n, dtype="Int64"),
    })


def rising(n=70, start=100.0, step=0.1):
    return [start + step * i for i in range(n)]


# Volume spike and close location ------------------------------------------------

def test_volume_spike_ratio_is_volume_over_its_20_day_mean():
    vols = [100] * 19 + [300] + [100] * 5
    out = add_smart_money_footprint(bars(rising(25), vols))
    assert out["vol_spike_ratio"].iloc[:19].isna().all()  # needs 20 days
    assert out.loc[19, "vol_spike_ratio"] == pytest.approx(300 / ((19 * 100 + 300) / 20))
    assert out.loc[24, "vol_spike_ratio"] == pytest.approx(100 / ((19 * 100 + 300) / 20))


def test_close_location_value():
    closes = [100, 100, 100]
    out = add_smart_money_footprint(bars(closes, highs=[100, 104, 100], lows=[96, 100, 100]))
    assert out["clv"].iloc[0] == pytest.approx(1.0)  # closed at the high
    assert out["clv"].iloc[1] == pytest.approx(0.0)  # closed at the low
    assert np.isnan(out["clv"].iloc[2])             # no range: undefined, never a division by zero


# Pocket pivot ---------------------------------------------------------------------

def test_pocket_pivot_must_beat_every_down_day_volume_in_the_prior_10_days():
    closes = rising(62)
    closes[55] = closes[54] - 0.5  # one down day, 5 rows before the test day
    vols = [1000] * 62
    vols[55] = 5000
    weak = add_smart_money_footprint(bars(closes, vols[:60] + [5000, 1000]))
    assert not weak.loc[60, "pocket_pivot"]  # equal to the down-day volume is not enough

    strong = add_smart_money_footprint(bars(closes, vols[:60] + [5001, 1000]))
    assert strong.loc[60, "pocket_pivot"]
    assert not strong.loc[55, "pocket_pivot"]  # a down day itself never qualifies


def test_down_day_older_than_10_rows_no_longer_counts():
    closes = rising(62)
    closes[49] = closes[48] - 0.5
    vols = [1000] * 62
    vols[49] = 9000  # row 49 is 11 rows before row 60
    out = add_smart_money_footprint(bars(closes, vols))
    assert out.loc[60, "pocket_pivot"]


def test_pocket_pivot_needs_close_near_or_above_ema50():
    closes = [100.0] * 55 + [90.0, 90.5]  # up day at row 56, but 90.5 < 95% of EMA50 (~99.4)
    out = add_smart_money_footprint(bars(closes))
    assert out.loc[56, "close"] < 0.95 * out.loc[56, "ema50"]
    assert not out.loc[56, "pocket_pivot"]


def test_no_pocket_pivot_before_50_rows():
    out = add_smart_money_footprint(bars(rising(60)))
    assert not out.loc[:48, "pocket_pivot"].any()  # EMA50 undefined
    assert out.loc[49:, "pocket_pivot"].all()      # steady rise, no down days: every up day qualifies


# Institutional accumulation and the 10-day memory --------------------------------

def test_institutional_accumulation():
    closes = rising(30)
    vols = [1000] * 30
    vols[25] = 3000
    highs = [c + 1 for c in closes]
    lows = [c - 1 for c in closes]
    out = add_smart_money_footprint(bars(closes, vols, highs=highs, lows=lows))
    assert out.loc[25, "vol_spike_ratio"] >= 2 and out.loc[25, "clv"] == pytest.approx(0.5)
    assert out.loc[25, "institutional_accumulation"]
    assert out["institutional_accumulation"].sum() == 1

    lows[25] = closes[25] - 0.5  # range 1.5 -> CLV 1/3 (closed in the lower half)
    weak = add_smart_money_footprint(bars(closes, vols, highs=highs, lows=lows))
    assert not weak.loc[25, "institutional_accumulation"]


def test_smart_money_active_10d_window_includes_today_and_9_prior_days():
    closes = rising(45)
    vols = [1000] * 45
    vols[25] = 3000  # accumulation on row 25 (no pocket pivots: EMA50 is undefined before row 49)
    out = add_smart_money_footprint(bars(closes, vols))
    active = out["smart_money_active_10d"]
    assert not active.loc[24] and active.loc[25:34].all() and not active.loc[35]


def test_footprint_never_looks_ahead():
    rng = np.random.default_rng(7)
    closes = list(100 * np.exp(np.cumsum(rng.normal(0, 0.02, 120))))
    vols = list(rng.integers(500, 5000, 120))
    full = add_smart_money_footprint(bars(closes, vols))
    cut = add_smart_money_footprint(bars(closes[:80], vols[:80]))
    cols = ["vol_spike_ratio", "clv", "pocket_pivot", "institutional_accumulation", "smart_money_active_10d"]
    pd.testing.assert_frame_equal(full.loc[:79, cols], cut[cols])


def test_symbols_are_computed_independently():
    a = bars(rising(30), [1000] * 29 + [3000], symbol="A.NS")
    b = bars(rising(30), [1000] * 30, symbol="B.NS")
    out = add_smart_money_footprint(pd.concat([b, a], ignore_index=True))
    assert out.groupby("symbol")["institutional_accumulation"].sum().to_dict() == {"A.NS": 1, "B.NS": 0}


def test_missing_columns_rejected():
    with pytest.raises(ValueError, match="volume"):
        add_smart_money_footprint(bars(rising(5)).drop(columns="volume"))


# Smart-money filtered EMA 20/50 strategy ------------------------------------------

def crossover_case(crossover_volume: int) -> pd.DataFrame:
    """Flat at 100 with a high-volume dip on row 55, then a jump to 110 on row 60 (EMA20 crosses EMA50)."""
    closes = [100.0] * 60 + [110.0] + [110.0] * 5
    closes[55] = 99.9
    vols = [1000] * 66
    vols[55] = 5000
    vols[60] = crossover_volume
    return bars(closes, vols)


def test_crossover_without_smart_money_is_filtered_out():
    out = generate_smart_money_signals(crossover_case(crossover_volume=1000))
    assert out.loc[60, "baseline_buy_signal"]  # the baseline would buy
    assert not out.loc[51:60, "smart_money_active_10d"].any()
    assert not out.loc[60, "buy_signal"]


def test_crossover_with_smart_money_is_kept():
    out = generate_smart_money_signals(crossover_case(crossover_volume=6000))
    assert out.loc[60, "pocket_pivot"] and out.loc[60, "buy_signal"]


def test_pocket_pivot_reentry_in_an_established_uptrend():
    closes = [100.0] * 60 + [110 + i for i in range(20)] + [130.0] * 25 + [131.0, 131.0]
    out = generate_smart_money_signals(bars(closes))
    day = 105  # 130 -> 131 on normal volume, no down days in the prior 10: a pocket pivot
    assert out.loc[day, "pocket_pivot"]
    assert out.loc[day, "ema20"] > out.loc[day, "ema50"] and abs(out.loc[day, "close"] / out.loc[day, "ema20"] - 1) <= 0.05
    assert out.loc[day, "buy_signal"] and not out.loc[day, "baseline_buy_signal"]
    # Early in the rise the close is far above EMA20, so pivots there are not re-entries.
    assert out.loc[62, "pocket_pivot"] and not out.loc[62, "buy_signal"]


def test_sells_are_the_baselines_and_never_coincide_with_buys():
    rng = np.random.default_rng(3)
    closes = list(100 * np.exp(np.cumsum(rng.normal(0, 0.02, 400))))
    vols = list(rng.integers(500, 5000, 400))
    df = bars(closes, vols)
    out = generate_smart_money_signals(df)
    base = generate_baseline_signals(df)
    assert out["sell_signal"].tolist() == base["sell_signal"].tolist()
    assert not (out["buy_signal"] & out["sell_signal"]).any()
    assert (out["buy_signal"] & ~out["baseline_buy_signal"]).sum() > 0  # pivot re-entries exist
    assert not (out["baseline_buy_signal"] & ~out["smart_money_active_10d"] & out["buy_signal"]).any()


def test_input_not_mutated():
    df = crossover_case(6000)
    before = df.copy()
    generate_smart_money_signals(df)
    pd.testing.assert_frame_equal(df, before)
