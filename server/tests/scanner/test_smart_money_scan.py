import numpy as np
import pandas as pd
import pytest

from src.scanner import SMART_MONEY_COLUMNS, scan_smart_money
from src.strategy.baseline import generate_baseline_signals

DATES = pd.bdate_range("2026-01-01", periods=70)


def stock(symbol, closes, volumes, dates=DATES) -> pd.DataFrame:
    c = np.asarray(closes, dtype=float)
    d = dates[-len(c):]
    return pd.DataFrame({"date": d, "symbol": symbol, "open": c, "high": c + 1, "low": c - 1, "close": c,
                         "volume": pd.array(volumes, dtype="Int64")})


def strategy(*frames) -> pd.DataFrame:
    return generate_baseline_signals(pd.concat(frames, ignore_index=True))


def rising(n=70):
    return [100 + 0.1 * i for i in range(n)]


def test_ranked_by_volume_spike_with_latest_day_fields():
    big = stock("BIG.NS", rising(), [1000] * 69 + [4000])    # 4x volume on an up day
    mid = stock("MID.NS", rising(), [1000] * 69 + [2000])
    dull = stock("DULL.NS", [100.0] * 70, [1000] * 70)       # flat: no up day
    out = scan_smart_money(strategy(dull, mid, big), names={"BIG.NS": "Big Co"})
    assert list(out.columns) == SMART_MONEY_COLUMNS
    assert out["symbol"].tolist() == ["BIG.NS", "MID.NS", "DULL.NS"]
    big_row = out.iloc[0]
    assert big_row["name"] == "Big Co" and big_row["date"] == DATES[-1]
    assert big_row["vol_spike_ratio"] == pytest.approx(4000 / ((19 * 1000 + 4000) / 20))
    assert big_row["return_1d_pct"] == pytest.approx((106.9 / 106.8 - 1) * 100)
    assert big_row["institutional_accumulation"] and big_row["pocket_pivot"] and big_row["smart_money_active_10d"]
    assert big_row["trend"] == "UPTREND"
    assert not out.iloc[2]["pocket_pivot"] and out.iloc[2]["trend"] == "DOWNTREND"  # EMA20 == EMA50


def test_short_history_has_no_trend():
    out = scan_smart_money(strategy(stock("NEW.NS", rising(30), [1000] * 30)))
    assert out.loc[0, "trend"] == "INSUFFICIENT_DATA" and not out.loc[0, "pocket_pivot"]


def test_stock_without_a_bar_on_the_scan_date_is_not_ranked_on_stale_values():
    fresh = stock("FRESH.NS", rising(), [1000] * 70)
    stale = stock("STALE.NS", rising(69), [1000] * 68 + [9000], dates=DATES[:-1])  # big spike, but a day old
    out = scan_smart_money(strategy(stale, fresh)).set_index("symbol")
    assert out.index.tolist() == ["FRESH.NS", "STALE.NS"]
    row = out.loc["STALE.NS"]
    assert "No bar on" in row["note"] and np.isnan(row["vol_spike_ratio"])
    assert not row["institutional_accumulation"] and not row["smart_money_active_10d"]


def test_deliverables_are_matched_on_the_same_date():
    s = stock("A.NS", rising(), [1000] * 70)
    deliv = pd.DataFrame({
        "date": DATES[-21:], "symbol": "A.NS",
        "deliv_qty": [100.0] * 20 + [500.0], "deliv_per": [40.0] * 20 + [70.0],
    })
    row = scan_smart_money(strategy(s), deliverables=deliv).iloc[0]
    assert row["deliv_qty"] == 500 and row["deliv_per"] == 70
    assert row["deliv_spike_ratio"] == pytest.approx(500 / ((19 * 100 + 500) / 20))
    assert row["delivery_spike"]

    older = deliv.assign(date=deliv["date"] - pd.offsets.BDay(1))  # nothing on the scan date
    row = scan_smart_money(strategy(s), deliverables=older).iloc[0]
    assert np.isnan(row["deliv_qty"]) and not row["delivery_spike"]


def test_empty_input():
    assert scan_smart_money(pd.DataFrame()).empty
