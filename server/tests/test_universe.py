import pytest

from src.data.universe import Nifty100Universe, UniverseError, parse_nse_index_csv

# Same layout as NSE's ind_nifty100list.csv
SAMPLE_CSV = """Company Name,Industry,Symbol,Series,ISIN Code
Reliance Industries Ltd.,Oil Gas & Consumable Fuels,RELIANCE,EQ,INE002A01018
Tata Consultancy Services Ltd.,Information Technology,TCS,EQ,INE467B01029
Mahindra & Mahindra Ltd.,Automobile and Auto Components,M&M,EQ,INE101A01026
Bajaj Auto Ltd.,Automobile and Auto Components,BAJAJ-AUTO,EQ,INE917I01010
"""


def test_parse_nse_csv():
    records = parse_nse_index_csv(SAMPLE_CSV)
    assert len(records) == 4
    assert records[0] == {"symbol": "RELIANCE.NS", "name": "Reliance Industries Ltd.", "exchange": "NSE"}
    assert [r["symbol"] for r in records] == ["RELIANCE.NS", "TCS.NS", "M&M.NS", "BAJAJ-AUTO.NS"]


def test_parse_removes_duplicates_and_whitespace():
    text = SAMPLE_CSV + "Reliance Industries Ltd.,Oil,  reliance ,EQ,INE002A01018\n"
    assert len(parse_nse_index_csv(text)) == 4


def test_parse_rejects_unexpected_format():
    with pytest.raises(UniverseError):
        parse_nse_index_csv("foo,bar\n1,2\n")


def test_universe_falls_back_to_cached_snapshot(tmp_path, monkeypatch):
    cache = tmp_path / "nifty100.csv"
    cache.write_text(SAMPLE_CSV, encoding="utf-8")
    universe = Nifty100Universe(cache_path=cache, urls=["https://example.invalid/x.csv"])
    monkeypatch.setattr(universe, "_fetch", lambda url: (_ for _ in ()).throw(OSError("offline")))
    assert len(universe.get_constituents()) == 4


def test_universe_saves_snapshot_on_success(tmp_path, monkeypatch):
    cache = tmp_path / "raw" / "nifty100.csv"
    universe = Nifty100Universe(cache_path=cache, urls=["https://example.invalid/x.csv"])
    monkeypatch.setattr(universe, "_fetch", lambda url: SAMPLE_CSV)
    assert len(universe.get_constituents()) == 4
    assert cache.read_text(encoding="utf-8") == SAMPLE_CSV


def test_universe_raises_without_source_or_cache(tmp_path, monkeypatch):
    universe = Nifty100Universe(cache_path=tmp_path / "none.csv", urls=["https://example.invalid/x.csv"])
    monkeypatch.setattr(universe, "_fetch", lambda url: (_ for _ in ()).throw(OSError("offline")))
    with pytest.raises(UniverseError):
        universe.get_constituents()
