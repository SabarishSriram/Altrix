import numpy as np
import pandas as pd
import pytest

from src.data import ParquetStore
from src.scanner import (
    BUY,
    HOLD,
    INSUFFICIENT_DATA,
    SCAN_COLUMNS,
    SELL,
    recent_crossovers,
    run_universe_scan,
    scan_current_opportunities,
)

from ..conftest import make_bars

FLAT = [100.0] * 60


def frame(closes, symbol="TEST.NS", start="2024-01-01") -> pd.DataFrame:
    dates = pd.bdate_range(start, periods=len(closes))
    return pd.DataFrame({"date": dates, "symbol": symbol, "close": [float(c) for c in closes]})


def row(table: pd.DataFrame, symbol: str) -> pd.Series:
    return table.set_index("symbol").loc[symbol]


# 1-3. BUY / SELL / HOLD --------------------------------------------------------

def test_buy_when_crossover_is_on_latest_day():
    r = row(scan_current_opportunities(frame(FLAT + [110])), "TEST.NS")
    assert r["signal"] == BUY
    assert r["signal_date"] == r["date"] == pd.bdate_range("2024-01-01", periods=61)[-1]
    assert r["ema20"] > r["ema50"] and r["ema_difference"] == pytest.approx(r["ema20"] - r["ema50"])
    assert r["last_crossover"] == BUY and r["last_crossover_date"] == r["date"]


def test_sell_when_downward_crossover_is_on_latest_day():
    r = row(scan_current_opportunities(frame(FLAT + [90])), "TEST.NS")
    assert r["signal"] == SELL and r["signal_date"] == r["date"]
    assert r["ema20"] < r["ema50"]


def test_ema20_above_ema50_without_new_crossover_is_hold_not_buy():
    df = frame(FLAT + [110, 111, 112, 113])  # crossed up 4 days ago, still above
    r = row(scan_current_opportunities(df), "TEST.NS")
    assert r["ema20"] > r["ema50"]
    assert r["signal"] == HOLD                 # NOT a new BUY
    assert pd.isna(r["signal_date"])
    assert r["last_crossover"] == BUY          # the earlier crossover is still reported
    assert r["last_crossover_date"] == df["date"].iloc[60]


def test_ema20_below_ema50_without_new_crossover_is_hold():
    r = row(scan_current_opportunities(frame(FLAT + [90, 89, 88])), "TEST.NS")
    assert r["ema20"] < r["ema50"] and r["signal"] == HOLD and r["last_crossover"] == SELL


def test_never_crossed_has_no_last_crossover():
    r = row(scan_current_opportunities(frame(FLAT)), "TEST.NS")
    assert r["signal"] == HOLD and r["last_crossover"] is None and pd.isna(r["last_crossover_date"])


# 4. Multiple stocks ---------------------------------------------------------------

def test_stocks_are_scanned_independently():
    df = pd.concat([frame(FLAT + [90], "S.NS"), frame(FLAT + [110], "B.NS"),
                    frame(FLAT + [100], "H.NS")])
    table = scan_current_opportunities(df)
    assert table["signal"].tolist() == [BUY, SELL, HOLD]          # sorted BUY, SELL, HOLD
    assert table["symbol"].tolist() == ["B.NS", "S.NS", "H.NS"]
    for sym in ("B.NS", "S.NS", "H.NS"):
        alone = scan_current_opportunities(df[df.symbol == sym])
        assert row(table, sym)["signal"] == alone["signal"].iloc[0]
        assert row(table, sym)["close"] == alone["close"].iloc[0]


# 5. Insufficient data --------------------------------------------------------------

def test_fewer_than_50_bars_is_insufficient_and_never_a_signal():
    r = row(scan_current_opportunities(frame([100.0] * 30 + [150.0] * 19)), "TEST.NS")
    assert r["signal"] == INSUFFICIENT_DATA
    assert pd.isna(r["ema50"]) and pd.isna(r["signal_date"])
    assert "Insufficient historical data" in r["note"]


def test_exactly_50_bars_cannot_cross_yet():
    # EMA50 exists on bar 50 but not on bar 49, so no crossover can be observed.
    r = row(scan_current_opportunities(frame([100.0] * 49 + [130.0])), "TEST.NS")
    assert r["ema20"] > r["ema50"] and r["signal"] == HOLD


def test_insufficient_stock_does_not_affect_others():
    df = pd.concat([frame([100.0] * 10, "NEW.NS"), frame(FLAT + [110], "OLD.NS")])
    table = scan_current_opportunities(df)
    assert row(table, "NEW.NS")["signal"] == INSUFFICIENT_DATA
    assert row(table, "OLD.NS")["signal"] == BUY


# 6. Latest date ----------------------------------------------------------------------

def test_uses_latest_trading_day():
    df = frame(FLAT + [110, 111])  # BUY was on the previous day
    r = row(scan_current_opportunities(df), "TEST.NS")
    assert r["date"] == df["date"].max()
    assert r["close"] == 111.0 and r["signal"] == HOLD


def test_stock_missing_latest_day_is_not_reported_as_current_signal():
    # STALE.NS's own last bar is a BUY, but it has no bar on the market's latest day.
    df = pd.concat([frame(FLAT + [110], "STALE.NS"), frame(FLAT + [100, 100], "LIVE.NS")])
    table = scan_current_opportunities(df)
    stale = row(table, "STALE.NS")
    assert stale["signal"] == HOLD and "latest bar is" in stale["note"]
    assert stale["last_crossover"] == BUY  # still visible as history


def test_as_of_scans_a_past_date_without_future_rows():
    df = frame(FLAT + [110, 111, 112])
    as_of = df["date"].iloc[60]
    r = row(scan_current_opportunities(df, as_of=as_of), "TEST.NS")
    assert r["date"] == as_of and r["signal"] == BUY and r["close"] == 110.0


# 7. No mutation and output shape ---------------------------------------------------

def test_input_not_mutated():
    df = pd.concat([frame(FLAT + [110], "A.NS"), frame(FLAT + [90], "B.NS")]).reset_index(drop=True)
    before = df.copy(deep=True)
    scan_current_opportunities(df)
    pd.testing.assert_frame_equal(df, before)


def test_output_columns_and_empty_input():
    assert list(scan_current_opportunities(frame(FLAT)).columns) == SCAN_COLUMNS
    empty = scan_current_opportunities(frame([]))
    assert empty.empty and list(empty.columns) == SCAN_COLUMNS


def test_missing_columns_raise():
    with pytest.raises(ValueError, match="missing required column"):
        scan_current_opportunities(frame(FLAT).drop(columns="close"))


def test_matches_strategy_signals_on_random_data():
    """The scanner reports exactly what baseline.py says about each stock's last bar."""
    from src.strategy import generate_baseline_signals

    rng = np.random.default_rng(0)
    frames = [frame(100 * np.exp(np.cumsum(rng.normal(0, 0.03, 200))), f"R{i}.NS") for i in range(40)]
    df = pd.concat(frames)
    table = scan_current_opportunities(df)
    last = generate_baseline_signals(df).groupby("symbol").tail(1).set_index("symbol")
    expected = np.where(last.buy_signal, BUY, np.where(last.sell_signal, SELL, HOLD))
    assert table.set_index("symbol").loc[last.index, "signal"].tolist() == expected.tolist()


# Recent crossovers -------------------------------------------------------------------

def test_recent_crossovers_lists_past_signals_newest_first():
    from src.strategy import generate_baseline_signals

    df = pd.concat([frame(FLAT + [110, 111, 112], "A.NS"), frame(FLAT + [100, 100, 90], "B.NS")])
    recent = recent_crossovers(generate_baseline_signals(df), trading_days=5)
    assert recent[["symbol", "signal"]].values.tolist() == [["B.NS", SELL], ["A.NS", BUY]]
    assert recent["date"].is_monotonic_decreasing
    assert recent_crossovers(generate_baseline_signals(df), trading_days=1).values.tolist()[0][1] == "B.NS"


# Universe scan (stored data) ----------------------------------------------------------

def store_bars(store, symbol, closes):
    df = make_bars(symbol, days=len(closes))
    c = np.asarray(closes, dtype=float)
    store.save(symbol, df.assign(open=c, high=c * 1.01, low=c * 0.99, close=c))


def test_universe_scan_uses_universe_names_and_records_failures(tmp_path):
    store = ParquetStore(tmp_path)
    store_bars(store, "A.NS", FLAT + [110])
    store_bars(store, "B.NS", FLAT + [100])
    (tmp_path / "BAD.NS.parquet").write_bytes(b"not a parquet file")
    store_bars(store, "OLD.NS", FLAT + [100])  # stored, but no longer in the universe

    universe = [{"symbol": "A.NS", "name": "Alpha Ltd", "exchange": "NSE"},
                {"symbol": "B.NS", "name": "Beta Ltd", "exchange": "NSE"},
                {"symbol": "BAD.NS", "name": "Broken Ltd", "exchange": "NSE"},
                {"symbol": "NEW.NS", "name": "Never Downloaded", "exchange": "NSE"}]
    r = run_universe_scan(universe, store)

    assert r.table["symbol"].tolist() == ["A.NS", "B.NS"]       # OLD.NS not in universe
    assert row(r.table, "A.NS")["name"] == "Alpha Ltd" and row(r.table, "A.NS")["signal"] == BUY
    assert set(r.failed) == {"BAD.NS", "NEW.NS"}
    assert "could not read" in r.failed["BAD.NS"] and "no stored data" in r.failed["NEW.NS"]
    assert r.universe_size == 4 and r.as_of == r.table["date"].max()
    assert r.counts() == {BUY: 1, SELL: 0, HOLD: 1, INSUFFICIENT_DATA: 0}
    assert set(r.strategy_frame["symbol"]) == {"A.NS", "B.NS"}


def test_universe_scan_with_no_data(tmp_path):
    r = run_universe_scan([{"symbol": "X.NS", "name": "X"}], ParquetStore(tmp_path))
    assert r.table.empty and r.as_of is None and "X.NS" in r.failed
