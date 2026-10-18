from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from app import dashboard as dash
from app import scanner_ui as ui
from src.data import ParquetStore
from src.data.provider import SCHEMA, MarketDataProvider
from src.data.universe import UniverseError
from src.scanner import run_universe_scan

from ..conftest import make_bars

ROOT = Path(__file__).resolve().parents[2]
SCANNER_PAGE = str(ROOT / "app" / "views" / "scanner.py")
ENTRYPOINT = str(ROOT / "app" / "streamlit_app.py")

DATES = pd.bdate_range("2026-06-01", periods=61)
FLAT = [100.0] * 60
CSV_HEADER = "Company Name,Industry,Symbol,Series,ISIN Code\n"


def save(store, symbol, closes, dates=DATES):
    c = np.asarray(closes, dtype=float)
    df = make_bars(symbol, dates=dates[-len(c):])
    store.save(symbol, df.assign(open=c, high=c * 1.01, low=c * 0.99, close=c))


def make_world(tmp_path, buy=True):
    """Stored data + universe snapshot: one BUY, one SELL, two HOLD, one short, one missing."""
    processed, raw = tmp_path / "processed", tmp_path / "raw"
    store = ParquetStore(processed)
    save(store, "BUYCO.NS", FLAT + ([110.0] if buy else [100.0]))
    save(store, "SELLCO.NS", FLAT + [90.0])
    save(store, "FLATCO.NS", FLAT + [100.0])
    save(store, "UPCO.NS", FLAT[:-3] + [110.0, 111.0, 112.0, 113.0])  # above, but crossed earlier
    save(store, "NEWCO.NS", [100.0] * 20)                             # recently listed
    raw.mkdir()
    rows = [("Buy Co", "BUYCO"), ("Sell Co", "SELLCO"), ("Flat Co", "FLATCO"), ("Up Co", "UPCO"),
            ("New Co", "NEWCO"), ("Missing Co", "MISSING")]
    (raw / ui.SNAPSHOT_NAME).write_text(
        CSV_HEADER + "".join(f"{n},X,{s},EQ,INE{i:09d}\n" for i, (n, s) in enumerate(rows)), encoding="utf-8")
    return processed, raw


@pytest.fixture
def world(tmp_path, monkeypatch):
    processed, raw = make_world(tmp_path)
    monkeypatch.setenv("ALTRIX_DATA_DIR", str(processed))
    monkeypatch.setenv("ALTRIX_RAW_DIR", str(raw))
    monkeypatch.setenv("ALTRIX_OFFLINE", "1")
    return processed, raw


@pytest.fixture
def scan(world):
    processed, _ = world
    return run_universe_scan(ui.load_universe(), ParquetStore(processed))


# ---- Helpers --------------------------------------------------------------------------

def test_load_universe_offline_uses_existing_parser(world):
    universe = ui.load_universe()
    assert [u["symbol"] for u in universe][:2] == ["BUYCO.NS", "SELLCO.NS"]
    assert universe[0]["name"] == "Buy Co"


def test_load_universe_offline_without_snapshot(tmp_path, monkeypatch):
    monkeypatch.setenv("ALTRIX_RAW_DIR", str(tmp_path))
    monkeypatch.setenv("ALTRIX_OFFLINE", "1")
    with pytest.raises(UniverseError):
        ui.load_universe()


def test_scan_classifications(scan):
    sig = scan.table.set_index("symbol")["signal"].to_dict()
    assert sig == {"BUYCO.NS": "BUY", "SELLCO.NS": "SELL", "FLATCO.NS": "HOLD",
                   "UPCO.NS": "HOLD", "NEWCO.NS": "INSUFFICIENT_DATA"}
    assert list(scan.failed) == ["MISSING.NS"]
    assert scan.as_of == DATES[-1]


def test_display_table_renames_without_changing_values(scan):
    table = ui.display_table(scan.table, ui.ALL_STOCKS_FIELDS)
    assert list(table.columns) == [ui.DISPLAY_COLUMNS[f] for f in ui.ALL_STOCKS_FIELDS]
    assert table["Close"].tolist() == scan.table["close"].tolist()
    assert table["SMA 20"].tolist() == scan.table["sma20"].tolist()
    assert "Insufficient historical data" in table["Signal"].tolist()


def test_stock_chart_shows_selected_symbol_and_strategy_crossovers(scan):
    fig = ui.stock_chart(scan, "UPCO.NS")
    sf = scan.strategy_frame[scan.strategy_frame.symbol == "UPCO.NS"]
    close = next(t for t in fig.data if t.name == "Close")
    assert list(close.y) == sf["close"].tolist()  # 61 bars < 6 months: whole history shown
    buys = next(t for t in fig.data if t.name == "BUY crossover")
    assert list(pd.to_datetime(buys.x)) == sf.loc[sf.buy_signal, "date"].tolist()


def test_stock_chart_window_is_about_six_months():
    store_dates = pd.bdate_range("2025-01-01", periods=400)
    df = make_bars("LONG.NS", dates=store_dates).assign(buy_signal=False, sell_signal=False,
                                                        sma20=100.0, sma50=100.0)
    from src.scanner import ScanResult
    result = ScanResult(table=pd.DataFrame(), strategy_frame=df, as_of=store_dates[-1], universe_size=1)
    x = pd.to_datetime(ui.stock_chart(result, "LONG.NS").data[0].x)
    assert x.max() == store_dates[-1]
    assert store_dates[-1] - pd.DateOffset(months=6) < x.min() <= store_dates[-1] - pd.DateOffset(months=6) + pd.Timedelta(days=5)


def test_format_date_and_staleness():
    assert ui.format_date(pd.Timestamp("2026-10-05")) == "05 Oct 2026"
    assert ui.format_date(pd.NaT) == "—"
    thu = pd.Timestamp("2026-10-01")
    assert not ui.is_stale(thu, today=pd.Timestamp("2026-10-05"))   # Fri holiday + weekend
    assert ui.is_stale(thu, today=pd.Timestamp("2026-10-12"))


class FakeProvider(MarketDataProvider):
    def __init__(self, extra: pd.DataFrame):
        self.extra = extra

    def get_daily_history(self, symbol, start, end):
        df = self.extra.assign(symbol=symbol).astype(SCHEMA)
        return df[(df.date >= pd.Timestamp(start)) & (df.date < pd.Timestamp(end))].reset_index(drop=True)


def test_refresh_uses_existing_downloader_incrementally(tmp_path, monkeypatch):
    store = ParquetStore(tmp_path)
    old = make_bars("A.NS", dates=pd.bdate_range("2026-09-01", periods=10))
    store.save("A.NS", old)
    new = make_bars("A.NS", dates=pd.bdate_range("2026-09-01", periods=12))
    monkeypatch.setattr(ui, "default_end", lambda: pd.Timestamp("2026-10-01").date())
    results = ui.refresh_market_data(["A.NS", "B.NS"], store, FakeProvider(new))
    summary = ui.refresh_summary(results)
    assert len(store.load("A.NS")) == 12
    assert store.load("A.NS").iloc[:10].reset_index(drop=True).equals(old)  # history untouched
    assert summary["updated"] == 2 and summary["new_rows"] == 2 + 12


# ---- Page (headless Streamlit) ----------------------------------------------------------

def run_page(path=SCANNER_PAGE) -> AppTest:
    at = AppTest.from_file(path, default_timeout=120)
    at.run()
    return at


def tables(at) -> list[pd.DataFrame]:
    return [d.value for d in at.dataframe]


def test_page_shows_summary_and_current_signals(world):
    at = run_page()
    assert not at.exception and not at.error
    assert at.title[0].value == "Altrix"
    assert any("NIFTY 100 Opportunity Scanner" in m.value for m in at.markdown)
    metrics = {m.label: m.value for m in at.metric}
    assert metrics["Data as of"] == ui.format_date(DATES[-1])
    assert metrics["Universe"] == "NIFTY 100" and metrics["Strategy"] == dash.STRATEGY_NAME
    assert metrics["BUY signals"] == "1" and metrics["SELL signals"] == "1"
    assert metrics["Insufficient history"] == "1"

    subheaders = [s.value for s in at.subheader]
    assert subheaders[:2] == ["Current BUY Signals", "Current SELL Signals"]
    buy_table, sell_table = tables(at)[:2]
    assert buy_table["Symbol"].tolist() == ["BUYCO.NS"] and buy_table["Signal"].tolist() == ["BUY"]
    assert sell_table["Symbol"].tolist() == ["SELLCO.NS"]
    assert "UPCO.NS" not in buy_table["Symbol"].tolist()  # above SMA50 but no new crossover

    assert any("MISSING.NS" in w.value for w in at.warning)  # failed symbol reported
    all_table = tables(at)[-1]
    assert len(all_table) == 5
    texts = " ".join(c.value for c in at.caption)
    assert "not real-time" in texts and "next trading day's open" in texts
    assert "not investment advice" in texts


def test_page_without_buy_signals_says_so(tmp_path, monkeypatch):
    processed, raw = make_world(tmp_path, buy=False)
    monkeypatch.setenv("ALTRIX_DATA_DIR", str(processed))
    monkeypatch.setenv("ALTRIX_RAW_DIR", str(raw))
    monkeypatch.setenv("ALTRIX_OFFLINE", "1")
    at = run_page()
    assert not at.exception
    assert any(i.value == "No new BUY signals detected in the current NIFTY 100 universe." for i in at.info)


def test_selecting_a_stock_shows_its_values(world, scan):
    at = run_page()
    box =next(s for s in at.selectbox if s.label == "Select Stock")
    box.set_value("UPCO.NS").run()
    assert not at.exception
    m = {x.label: x.value for x in at.metric}
    d = scan.table.set_index("symbol").loc["UPCO.NS"]
    assert m["Current Price"] == dash.format_inr(d["close"], 2)
    assert m["SMA20"] == dash.format_inr(d["sma20"], 2)
    assert m["Current Signal"] == "HOLD" and m["Signal Date"] == "—"


def test_refresh_button_calls_downloader_and_rescans(world, monkeypatch):
    calls = []
    monkeypatch.setattr(ui, "refresh_market_data", lambda symbols, store: calls.append(symbols) or [])
    at = run_page()
    next(b for b in at.button if b.label == "Refresh Data").click().run()
    assert not at.exception
    assert calls and "BUYCO.NS" in calls[0]
    assert any("Refresh complete" in s.value for s in at.success)


def test_page_with_no_data_shows_clear_error(tmp_path, monkeypatch):
    raw = make_world(tmp_path)[1]
    monkeypatch.setenv("ALTRIX_DATA_DIR", str(tmp_path / "empty"))
    monkeypatch.setenv("ALTRIX_RAW_DIR", str(raw))
    monkeypatch.setenv("ALTRIX_OFFLINE", "1")
    at = run_page()
    assert not at.exception
    assert any("No usable price data" in e.value for e in at.error)


def test_entrypoint_opens_scanner_and_links_backtest(world):
    at = run_page(ENTRYPOINT)
    assert not at.exception
    assert any("NIFTY 100 Opportunity Scanner" in m.value for m in at.markdown)
    at.switch_page(str(ROOT / "app" / "views" / "backtest.py")).run()
    assert not at.exception
    assert any("Historical Backtesting Dashboard" in m.value for m in at.markdown)
