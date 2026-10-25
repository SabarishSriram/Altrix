from datetime import date

import pandas as pd

from src.data.downloader import ParquetStore, download_all, update_symbol, validate_all
from src.data.provider import SCHEMA, MarketDataProvider, ProviderError

from .conftest import make_bars


class FakeProvider(MarketDataProvider):
    """Serves bars from an in-memory frame and records each request."""

    def __init__(self, full: pd.DataFrame, fail: set[str] = frozenset()):
        self.full, self.fail, self.calls = full, fail, []

    def get_daily_history(self, symbol, start, end):
        self.calls.append((symbol, start, end))
        if symbol in self.fail:
            raise ProviderError(f"{symbol}: not found")
        df = self.full.assign(symbol=symbol).astype(SCHEMA)
        mask = (df["date"] >= pd.Timestamp(start)) & (df["date"] < pd.Timestamp(end))
        return df[mask].reset_index(drop=True)


def test_initial_download_writes_parquet(tmp_path):
    store = ParquetStore(tmp_path)
    provider = FakeProvider(make_bars(days=10))  # 2024-01-01 .. 2024-01-12
    r = update_symbol("A.NS", provider, store, date(2024, 1, 1), date(2024, 1, 13))

    assert r.status == "downloaded" and r.new_rows == 10
    stored = store.load("A.NS")
    assert len(stored) == 10
    assert {c: str(t) for c, t in stored.dtypes.items()} == SCHEMA


def test_incremental_fetches_only_after_last_stored_date(tmp_path):
    store = ParquetStore(tmp_path)
    provider = FakeProvider(make_bars(days=10))
    update_symbol("A.NS", provider, store, date(2024, 1, 1), date(2024, 1, 6))  # first week only
    assert len(store.load("A.NS")) == 5

    r = update_symbol("A.NS", provider, store, date(2024, 1, 1), date(2024, 1, 13))
    assert r.status == "updated" and r.new_rows == 5
    assert provider.calls[-1][1] == date(2024, 1, 6)  # started the day after the last stored bar
    stored = store.load("A.NS")
    assert len(stored) == 10 and stored["date"].is_monotonic_increasing
    assert not stored["date"].duplicated().any()


def test_up_to_date_skips_provider_over_weekend(tmp_path):
    store = ParquetStore(tmp_path)
    provider = FakeProvider(make_bars(days=5))  # Mon 1 .. Fri 5 Jan 2024
    update_symbol("A.NS", provider, store, date(2024, 1, 1), date(2024, 1, 6))
    n_calls = len(provider.calls)

    r = update_symbol("A.NS", provider, store, date(2024, 1, 1), date(2024, 1, 8))  # run on Sunday
    assert r.status == "up_to_date"
    assert len(provider.calls) == n_calls


def test_failures_do_not_stop_pipeline(tmp_path):
    store = ParquetStore(tmp_path)
    provider = FakeProvider(make_bars(days=5), fail={"BAD.NS"})
    results = download_all(["A.NS", "BAD.NS", "B.NS"], provider, store,
                           date(2024, 1, 1), date(2024, 1, 6))

    assert [r.status for r in results] == ["downloaded", "failed", "downloaded"]
    assert "not found" in results[1].error
    assert store.symbols() == ["A.NS", "B.NS"]


def test_full_refresh_ignores_existing_file(tmp_path):
    store = ParquetStore(tmp_path)
    provider = FakeProvider(make_bars(days=5))
    update_symbol("A.NS", provider, store, date(2024, 1, 1), date(2024, 1, 6))
    r = update_symbol("A.NS", provider, store, date(2024, 1, 1), date(2024, 1, 6), full_refresh=True)
    assert r.status == "downloaded"
    assert provider.calls[-1][1] == date(2024, 1, 1)


def test_validate_subset_still_detects_gap(tmp_path):
    """Validating one symbol alone must not turn its own gaps into 'holidays'."""
    store = ParquetStore(tmp_path)
    days = pd.bdate_range("2024-01-01", periods=10)
    for i in range(3):
        store.save(f"P{i}.NS", make_bars(f"P{i}.NS", dates=days))
    store.save("GAP.NS", make_bars("GAP.NS", dates=days.drop(days[5])))

    [report] = validate_all(["GAP.NS"], store)
    assert report.symbol == "GAP.NS"
    assert report.suspicious_missing_dates == [days[5]]
    assert report.holidays_skipped == 0

    assert validate_all(["NOPE.NS"], store) == []  # unknown symbols are skipped
