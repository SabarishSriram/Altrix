"""NSE sec_bhavdata_full deliverables: parsing, storage, spike flags. Offline: no NSE calls."""

import io
import urllib.error
from datetime import date

import pandas as pd
import pytest

from src.data.deliverables import (DeliverableError, DeliverableStore, add_delivery_signals, bhavdata_url,
                                   download_deliverables, fetch_bhavdata, parse_bhavdata)

# Real rows from sec_bhavdata_full_23102026.csv (columns are separated by ", ").
SAMPLE = """SYMBOL, SERIES, DATE1, PREV_CLOSE, OPEN_PRICE, HIGH_PRICE, LOW_PRICE, LAST_PRICE, CLOSE_PRICE, AVG_PRICE, TTL_TRD_QNTY, TURNOVER_LACS, NO_OF_TRADES, DELIV_QTY, DELIV_PER
3IINFOLTD, BE, 23-Oct-2026, 21.19, 21.19, 21.19, 20.14, 20.19, 20.23, 20.29, 308747, 62.65, 828, -, -
574GS2026, GS, 23-Oct-2026, 102.55, 99.98, 102.65, 99.98, 102.65, 102.65, 100.43, 12, 0.01, 3, 10, 83.33
M&M, EQ, 23-Oct-2026, 2864.10, 2853.00, 2861.20, 2802.40, 2861.20, 2861.20, 2826.25, 2294559, 64850.00, 89940, 1298946, 56.61
RELIANCE, EQ, 23-Oct-2026, 1184.50, 1184.00, 1201.90, 1163.10, 1190.00, 1190.00, 1180.79, 14905641, 176004.07, 241397, 7634419, 51.22
"""


def test_url_format():
    assert bhavdata_url(date(2026, 10, 23)).endswith("/sec_bhavdata_full_23102026.csv")


def test_parse_keeps_eq_series_only():
    df = parse_bhavdata(SAMPLE)
    assert list(df.columns) == ["date", "symbol", "deliv_qty", "deliv_per"]
    assert df["symbol"].tolist() == ["M&M.NS", "RELIANCE.NS"]
    assert (df["date"] == pd.Timestamp("2026-10-23")).all()
    assert df.set_index("symbol").loc["RELIANCE.NS"].tolist()[1:] == [7634419, 51.22]


def test_parse_dash_becomes_missing():
    text = SAMPLE.replace("3IINFOLTD, BE", "3IINFOLTD, EQ")
    df = parse_bhavdata(text).set_index("symbol")
    assert df.loc["3IINFOLTD.NS", ["deliv_qty", "deliv_per"]].isna().all()


def test_parse_rejects_other_files():
    with pytest.raises(DeliverableError, match="columns"):
        parse_bhavdata("Symbol,Company Name\nRELIANCE,Reliance\n")


class FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def test_fetch_returns_none_on_holiday_and_raises_on_other_errors():
    def holiday(req, timeout):
        raise urllib.error.HTTPError(req.full_url, 404, "Not Found", {}, None)

    def blocked(req, timeout):
        raise urllib.error.HTTPError(req.full_url, 403, "Forbidden", {}, None)

    def ok(req, timeout):
        assert "Mozilla" in req.get_header("User-agent")
        return FakeResponse(SAMPLE.encode())

    day = date(2026, 10, 24)
    assert fetch_bhavdata(day, opener=holiday) is None
    with pytest.raises(DeliverableError, match="403"):
        fetch_bhavdata(day, opener=blocked)
    assert len(fetch_bhavdata(day, opener=ok)) == 2


def test_store_appends_and_replaces_refetched_days(tmp_path):
    store = DeliverableStore(tmp_path / "deliv")
    assert store.load().empty and store.dates() == set()
    day = parse_bhavdata(SAMPLE)
    store.append(day)
    store.append(day.assign(deliv_per=60.0))  # same day fetched again: replaced, not duplicated
    stored = store.load()
    assert len(stored) == 2 and (stored["deliv_per"] == 60.0).all()


def test_download_skips_weekends_stored_days_and_survives_failures(tmp_path):
    store = DeliverableStore(tmp_path)
    calls = []

    def fetch(day):
        calls.append(day)
        if day == date(2026, 10, 21):
            raise DeliverableError("HTTP 403")
        if day == date(2026, 10, 22):
            return None  # holiday
        return parse_bhavdata(SAMPLE.replace("23-Oct-2026", f"{day:%d-%b-%Y}"))

    result = download_deliverables(store, date(2026, 10, 19), date(2026, 10, 25), {"RELIANCE.NS"}, fetch=fetch)
    assert calls == [date(2026, 10, d) for d in (19, 20, 21, 22, 23)]  # no weekend requests
    assert result["fetched"] == ["2026-10-19", "2026-10-20", "2026-10-23"]
    assert result["no_file"] == ["2026-10-22"] and list(result["failed"]) == ["2026-10-21"]
    assert set(store.load()["symbol"]) == {"RELIANCE.NS"}  # only the requested universe kept

    calls.clear()
    download_deliverables(store, date(2026, 10, 19), date(2026, 10, 25), {"RELIANCE.NS"}, fetch=fetch)
    assert calls == [date(2026, 10, 21), date(2026, 10, 22)]  # stored days are not fetched again


def test_holiday_file_repeating_the_previous_session_is_not_a_new_day(tmp_path):
    store = DeliverableStore(tmp_path)
    previous = parse_bhavdata(SAMPLE.replace("23-Oct-2026", "19-Oct-2026"))
    result = download_deliverables(store, date(2026, 10, 20), date(2026, 10, 20), fetch=lambda day: previous)
    assert result["fetched"] == [] and result["no_file"] == ["2026-10-20"]
    assert store.load().empty


def test_delivery_spike_needs_ratio_2_and_55_percent_delivery():
    dates = pd.bdate_range("2026-01-01", periods=21)
    qty = [100.0] * 19 + [500.0, 500.0]
    per = [40.0] * 19 + [60.0, 50.0]
    out = add_delivery_signals(pd.DataFrame({"date": dates, "symbol": "A.NS", "deliv_qty": qty, "deliv_per": per}))
    assert out["deliv_spike_ratio"].iloc[:19].isna().all()
    assert out.loc[19, "deliv_spike_ratio"] == pytest.approx(500 / ((19 * 100 + 500) / 20))
    assert out.loc[19, "delivery_spike"]       # ratio >= 2 and 60% delivered
    assert not out.loc[20, "delivery_spike"]   # ratio still >= 2, but only 50% delivered
