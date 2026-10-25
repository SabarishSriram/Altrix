import numpy as np
import pandas as pd
import pytest

from src.strategy.baseline import generate_baseline_signals

from ..conftest import make_bars


def frame(closes, symbol="TEST.NS", start="2024-01-01") -> pd.DataFrame:
    dates = pd.bdate_range(start, periods=len(closes))
    return pd.DataFrame({"date": dates, "symbol": symbol, "close": [float(c) for c in closes]})


def signal_rows(out: pd.DataFrame, col: str) -> list[int]:
    return out.index[out[col]].tolist()


def random_walk(n: int, seed: int) -> list[float]:
    rng = np.random.default_rng(seed)
    return list(100 * np.exp(np.cumsum(rng.normal(0, 0.02, n))))


def manual_ema(closes: list[float], span: int) -> list[float]:
    """Reference EMA: alpha = 2 / (span + 1), seeded with the first close, hidden for span - 1 rows."""
    alpha = 2 / (span + 1)
    out, e = [], None
    for c in closes:
        e = c if e is None else alpha * c + (1 - alpha) * e
        out.append(e)
    return [np.nan] * (span - 1) + out[span - 1:]


# Flat for 60 days (EMA20 == EMA50), then a sharp rise, a plateau, and a sharp fall.
FLAT, UP, PLATEAU, DOWN = [100] * 60, [110 + i for i in range(20)], [130] * 40, [60] * 40
CROSS_CLOSES = FLAT + UP + PLATEAU + DOWN
BUY_DAY = 60  # first rise: EMA20 jumps above EMA50 (they were equal the day before)


# 1. EMA calculation -------------------------------------------------------

def test_ema_values_match_the_recursive_formula():
    closes = random_walk(120, seed=1)
    out = generate_baseline_signals(frame(closes))
    e20, e50 = manual_ema(closes, 20), manual_ema(closes, 50)
    for t in (19, 49, 77, 119):
        assert out.loc[t, "ema20"] == pytest.approx(e20[t])
        if t >= 49:
            assert out.loc[t, "ema50"] == pytest.approx(e50[t])


def test_ema_weights_recent_closes_more_than_a_simple_average():
    closes = [100.0] * 60 + [120.0] * 5  # a jump: the EMA follows faster than the 20-day mean
    out = generate_baseline_signals(frame(closes))
    assert out.loc[64, "ema20"] > np.mean(closes[45:65])


# 2-4. Crossovers ----------------------------------------------------------

def test_buy_on_crossover_day_only():
    out = generate_baseline_signals(frame(CROSS_CLOSES))
    assert out.loc[BUY_DAY - 1, "ema20"] == out.loc[BUY_DAY - 1, "ema50"]  # equal the day before
    assert out.loc[BUY_DAY, "ema20"] > out.loc[BUY_DAY, "ema50"]
    assert signal_rows(out, "buy_signal") == [BUY_DAY]


def test_sell_on_crossover_day_only():
    out = generate_baseline_signals(frame(CROSS_CLOSES))
    sells = signal_rows(out, "sell_signal")
    assert len(sells) == 1
    t = sells[0]
    assert t >= len(FLAT + UP + PLATEAU)  # happens during the fall
    assert out.loc[t - 1, "ema20"] >= out.loc[t - 1, "ema50"]
    assert out.loc[t, "ema20"] < out.loc[t, "ema50"]


def test_no_repeated_signals_while_trend_persists():
    out = generate_baseline_signals(frame(CROSS_CLOSES))
    above = out["ema20"] > out["ema50"]
    below = out["ema20"] < out["ema50"]
    assert above.sum() > 30 and below.sum() > 10  # EMA20 stays on each side for many days
    assert out["buy_signal"].sum() == 1
    assert out["sell_signal"].sum() == 1


def test_matches_reference_loop_on_random_prices():
    closes = random_walk(600, seed=7)
    out = generate_baseline_signals(frame(closes))
    s20, s50 = manual_ema(closes, 20), manual_ema(closes, 50)
    buys = [t for t in range(50, len(closes)) if s20[t - 1] <= s50[t - 1] and s20[t] > s50[t]]
    sells = [t for t in range(50, len(closes)) if s20[t - 1] >= s50[t - 1] and s20[t] < s50[t]]

    assert buys and sells
    assert signal_rows(out, "buy_signal") == buys
    assert signal_rows(out, "sell_signal") == sells
    # BUY and SELL alternate: never two of the same in a row.
    events = sorted([(t, "B") for t in buys] + [(t, "S") for t in sells])
    assert all(a[1] != b[1] for a, b in zip(events, events[1:]))


# 5. Insufficient history --------------------------------------------------

def test_no_ema_or_signal_before_enough_history():
    out = generate_baseline_signals(frame(random_walk(80, seed=3)))
    assert out["ema20"].iloc[:19].isna().all() and out["ema20"].iloc[19:].notna().all()
    assert out["ema50"].iloc[:49].isna().all() and out["ema50"].iloc[49:].notna().all()
    assert not out[["buy_signal", "sell_signal"]].iloc[:50].any().any()


def test_already_above_when_ema50_first_exists_is_not_a_buy():
    # Steady rise: EMA20 > EMA50 from the first day EMA50 exists, but no crossover is ever seen.
    out = generate_baseline_signals(frame([100 + i for i in range(80)]))
    assert out.loc[49, "ema20"] > out.loc[49, "ema50"]
    assert not out["buy_signal"].any() and not out["sell_signal"].any()


def test_short_history_gives_no_signals():
    out = generate_baseline_signals(frame([100.0] * 30))
    assert out["ema50"].isna().all()
    assert not out["buy_signal"].any() and not out["sell_signal"].any()


# 6. Multiple symbols --------------------------------------------------------

def test_symbols_are_independent():
    a = frame(CROSS_CLOSES, symbol="A.NS")
    b = frame([50.0] * len(CROSS_CLOSES), symbol="B.NS")  # flat: never crosses
    out = generate_baseline_signals(pd.concat([b, a]))     # B first on input

    assert out["symbol"].tolist() == ["A.NS"] * len(a) + ["B.NS"] * len(b)
    got_a = out[out.symbol == "A.NS"].reset_index(drop=True)
    got_b = out[out.symbol == "B.NS"]

    alone = generate_baseline_signals(a)
    pd.testing.assert_frame_equal(got_a, alone)          # B has no influence on A
    assert not got_b["buy_signal"].any() and not got_b["sell_signal"].any()
    assert got_b["ema20"].dropna().eq(50.0).all()         # A's prices never leak into B
    assert got_b["ema50"].iloc[:49].isna().all()          # each stock needs its own 50 rows


# 7. Purity and lookahead ----------------------------------------------------

def test_input_not_mutated_and_columns_kept():
    df = make_bars("RELIANCE.NS", days=80)
    before = df.copy(deep=True)
    out = generate_baseline_signals(df)

    pd.testing.assert_frame_equal(df, before)
    assert list(out.columns) == list(df.columns) + ["ema20", "ema50", "buy_signal", "sell_signal"]
    assert out["buy_signal"].dtype == bool and out["sell_signal"].dtype == bool
    pd.testing.assert_frame_equal(out[df.columns], df)


def test_no_lookahead_future_rows_do_not_change_past_signals():
    closes = random_walk(300, seed=11)
    full = generate_baseline_signals(frame(closes))
    for cut in (60, 150, 299):
        partial = generate_baseline_signals(frame(closes[: cut + 1]))
        pd.testing.assert_frame_equal(partial, full.iloc[: cut + 1])


def test_target_column_is_ignored():
    df = frame(random_walk(200, seed=5))
    with_target = df.assign(target=np.random.default_rng(0).integers(0, 2, len(df)).astype(float))
    a = generate_baseline_signals(df)
    b = generate_baseline_signals(with_target)
    pd.testing.assert_frame_equal(a, b.drop(columns="target"))


def test_output_is_chronological_even_if_input_is_not():
    df = frame(CROSS_CLOSES)
    out = generate_baseline_signals(df.iloc[::-1])
    assert out["date"].is_monotonic_increasing
    assert signal_rows(out, "buy_signal") == [BUY_DAY]


# 8. Errors ----------------------------------------------------------------

@pytest.mark.parametrize("col", ["date", "symbol", "close"])
def test_missing_required_column_raises_clear_error(col):
    with pytest.raises(ValueError, match=f"missing required column.*'{col}'"):
        generate_baseline_signals(frame([100.0] * 60).drop(columns=col))


def test_duplicate_dates_raise():
    df = frame([100.0] * 60)
    with pytest.raises(ValueError, match="duplicate"):
        generate_baseline_signals(pd.concat([df, df.iloc[[3]]]))
