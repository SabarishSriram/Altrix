"""FastAPI endpoints on synthetic stored data. Offline: no NSE, no Yahoo."""

from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient

from api.main import create_app
from api.service import AltrixService
from src.data import DownloadResult, ParquetStore

from ..app.test_scanner_ui import make_world


@pytest.fixture
def world(tmp_path, monkeypatch):
    processed, raw = make_world(tmp_path)
    monkeypatch.setenv("ALTRIX_RAW_DIR", str(raw))
    monkeypatch.setenv("ALTRIX_OFFLINE", "1")
    return processed, raw


@pytest.fixture
def service(world):
    processed, _ = world
    return AltrixService(data_dir=processed, refresher=lambda symbols, store: [])


@pytest.fixture
def client(service):
    return TestClient(create_app(service, warm=False))


def by_symbol(body):
    return {s["symbol"]: s for s in body["stocks"]}


# ---- /health and /api/meta ---------------------------------------------------------

def test_health_never_scans(client, service):
    body = client.get("/health").json()
    assert body["status"] == "ok"
    assert body["data_available"] is True
    assert body["stored_symbols"] == 5
    assert body["scan_cached"] is False and service.scan_cached() is None
    assert body["offline_mode"] is True
    assert body["downloads_enabled"] is True
    assert body["refresh"]["state"] == "idle"


def test_health_degraded_without_data(tmp_path, monkeypatch):
    monkeypatch.setenv("ALTRIX_OFFLINE", "1")
    c = TestClient(create_app(AltrixService(data_dir=tmp_path / "empty"), warm=False))
    body = c.get("/health").json()
    assert body["status"] == "degraded" and body["data_available"] is False


def test_meta(client):
    body = client.get("/api/meta").json()
    assert body["strategy"]["short_window"] == 20 and body["strategy"]["long_window"] == 50
    assert body["data_source"]["real_time"] is False
    assert body["backtest_defaults"]["transaction_cost"] == 0.001


# ---- /api/scanner --------------------------------------------------------------------

def test_scanner_structure_and_counts(client):
    r = client.get("/api/scanner")
    assert r.status_code == 200
    body = r.json()
    assert body["data_as_of"] == "2026-08-24"
    assert body["universe"] == "NIFTY 100" and body["universe_size"] == 6
    assert body["scanned_count"] == 5
    assert (body["buy_count"], body["sell_count"], body["hold_count"], body["insufficient_count"]) == (1, 1, 2, 1)
    assert body["failed_symbols"] == [
        {"symbol": "MISSING.NS", "reason": "no stored data (run: python scripts/download_data.py)"}]
    assert {"name", "buy_rule", "sell_rule"} <= set(body["strategy"])
    for stock in body["stocks"]:
        assert {"symbol", "date", "close", "previous_close", "daily_change_pct", "sma20", "sma50",
                "signal", "signal_date"} <= set(stock)


def test_signal_mapping_uses_strategy_crossovers(client):
    stocks = by_symbol(client.get("/api/scanner").json())
    buy, sell = stocks["BUYCO.NS"], stocks["SELLCO.NS"]
    assert buy["signal"] == "BUY" and buy["signal_date"] == "2026-08-24"
    assert sell["signal"] == "SELL" and sell["signal_date"] == "2026-08-24"
    # SMA20 above SMA50 from an *earlier* crossover is HOLD, not BUY
    up = stocks["UPCO.NS"]
    assert up["sma20"] > up["sma50"]
    assert up["signal"] == "HOLD" and up["signal_date"] is None
    assert up["last_crossover"] == "BUY" and up["last_crossover_date"] < "2026-08-24"
    assert stocks["FLATCO.NS"]["signal"] == "HOLD"


def test_daily_change_from_previous_stored_bar(client):
    buy = by_symbol(client.get("/api/scanner").json())["BUYCO.NS"]
    assert buy["close"] == 110.0 and buy["previous_close"] == 100.0
    assert buy["previous_date"] == "2026-08-21"  # previous business day
    assert buy["daily_change_pct"] == pytest.approx(10.0)


def test_insufficient_history(client):
    new = by_symbol(client.get("/api/scanner").json())["NEWCO.NS"]
    assert new["signal"] == "INSUFFICIENT_DATA"
    assert new["sma50"] is None and new["sma_difference"] is None  # NaN serialised as null
    assert new["sma20"] == pytest.approx(100.0)
    assert "Insufficient" in new["note"]


def test_scan_is_cached_until_data_changes(client, service, world, monkeypatch):
    first = client.get("/api/scanner").json()
    calls = []
    import api.service as svc_mod
    real = svc_mod.run_universe_scan
    monkeypatch.setattr(svc_mod, "run_universe_scan", lambda *a, **k: calls.append(1) or real(*a, **k))

    assert client.get("/api/scanner").json()["scanned_at"] == first["scanned_at"]
    assert calls == []

    processed, _ = world
    time.sleep(0.01)
    store = ParquetStore(processed)
    store.save("FLATCO.NS", store.load("FLATCO.NS"))  # touch: new mtime -> new data version
    client.get("/api/scanner")
    assert calls == [1]


def test_scanner_without_any_data_is_503(tmp_path, monkeypatch, world):
    c = TestClient(create_app(AltrixService(data_dir=tmp_path / "empty"), warm=False))
    r = c.get("/api/scanner")
    assert r.status_code == 503
    assert "download_data.py" in r.json()["detail"]


def test_universe_unavailable_is_503(tmp_path, monkeypatch):
    monkeypatch.setenv("ALTRIX_OFFLINE", "1")
    monkeypatch.setenv("ALTRIX_RAW_DIR", str(tmp_path / "no-snapshot"))
    c = TestClient(create_app(AltrixService(data_dir=tmp_path), warm=False))
    r = c.get("/api/scanner")
    assert r.status_code == 503
    assert "constituent list" in r.json()["detail"]
    assert str(tmp_path) not in r.text  # no local paths leak


# ---- /api/scanner/{symbol}/history ------------------------------------------------------

def test_history_points_and_crossovers(client):
    r = client.get("/api/scanner/BUYCO.NS/history")
    assert r.status_code == 200
    body = r.json()
    assert body["symbol"] == "BUYCO.NS" and body["name"] == "Buy Co"
    assert body["total_bars"] == len(body["points"]) == 61
    assert body["points"][0]["sma50"] is None  # warm-up
    assert body["points"][-1]["signal"] == "BUY"
    assert [c["date"] for c in body["crossovers"]] == ["2026-08-24"]
    assert body["stock"]["signal"] == "BUY"


def test_history_accepts_bare_and_lowercase_symbols(client):
    assert client.get("/api/scanner/buyco/history").json()["symbol"] == "BUYCO.NS"


def test_history_date_range(client):
    body = client.get("/api/scanner/BUYCO.NS/history?start=2026-08-17&end=2026-08-21").json()
    assert [p["date"] for p in body["points"]] == ["2026-08-17", "2026-08-18", "2026-08-19", "2026-08-20", "2026-08-21"]
    assert body["crossovers"] == []
    assert body["total_bars"] == 61
    assert client.get("/api/scanner/BUYCO.NS/history?start=2026-08-21&end=2026-08-17").status_code == 422


@pytest.mark.parametrize("bad", ["bad!!", "a b", "X" * 30, "RELIANCE.BO"])
def test_history_invalid_symbol_is_422(client, bad):
    assert client.get(f"/api/scanner/{bad}/history").status_code == 422


def test_history_unknown_symbol_is_404(client):
    r = client.get("/api/scanner/ZZZ.NS/history")
    assert r.status_code == 404
    assert "not in the NIFTY 100" in r.json()["detail"]


def test_history_constituent_without_data_is_404(client):
    r = client.get("/api/scanner/MISSING.NS/history")
    assert r.status_code == 404
    assert "no stored data" in r.json()["detail"]


def test_history_insufficient_data_has_no_signals(client):
    body = client.get("/api/scanner/NEWCO.NS/history").json()
    assert body["total_bars"] == 20
    assert body["crossovers"] == []
    assert all(p["sma50"] is None for p in body["points"])


# ---- /api/signals/recent -----------------------------------------------------------------

def test_recent_signals(client):
    body = client.get("/api/signals/recent?days=5").json()
    assert len(body["daily_counts"]) == 5
    assert body["daily_counts"][-1] == {"date": "2026-08-24", "buy": 1, "sell": 1}
    latest = [c for c in body["crossovers"] if c["date"] == "2026-08-24"]
    assert {(c["symbol"], c["signal"]) for c in latest} == {("BUYCO.NS", "BUY"), ("SELLCO.NS", "SELL")}
    assert client.get("/api/signals/recent?days=0").status_code == 422


# ---- /api/backtest -----------------------------------------------------------------------

def test_backtest_runs_existing_engine(client):
    r = client.get("/api/backtest?initial_capital=50000")
    assert r.status_code == 200
    body = r.json()
    assert body["config"]["initial_capital"] == 50000
    assert body["metrics"]["initial_capital"] == 50000
    assert len(body["equity_curve"]) == body["metrics"]["trading_days"]
    assert body["symbols"] == 5
    assert {"total_equity", "drawdown", "cash"} <= set(body["equity_curve"][0])


def test_backtest_years_lookback(client):
    body = client.get("/api/backtest?years=1").json()
    assert body["config"]["start"] == "2025-08-24"  # one year before the latest stored date
    assert body["config"]["end"] is None
    assert body["metrics"]["start_date"] == "2026-06-01"  # less history than requested: starts at the first bar
    assert client.get("/api/backtest?years=0").status_code == 422
    assert client.get("/api/backtest?years=1&start=2026-06-01").status_code == 422


def test_backtest_invalid_settings(client):
    assert client.get("/api/backtest?initial_capital=0").status_code == 422
    r = client.get("/api/backtest?start=2026-08-20&end=2026-08-01")
    assert r.status_code == 422 and "after" in r.json()["detail"]


# ---- /api/refresh --------------------------------------------------------------------------

def test_rescan(client):
    body = client.post("/api/refresh").json()
    assert body["state"] == "succeeded" and body["kind"] == "rescan"
    assert client.get("/health").json()["scan_cached"] is True


def test_download_runs_in_background(world):
    processed, _ = world
    seen = []

    def fake_refresher(symbols, store):
        seen.append(sorted(symbols))
        return [DownloadResult(s, "up_to_date") for s in symbols]

    c = TestClient(create_app(AltrixService(data_dir=processed, refresher=fake_refresher), warm=False))
    r = c.post("/api/refresh?download=true")
    assert r.status_code in (202, 409)
    for _ in range(100):
        status = c.get("/api/refresh").json()
        if status["state"] != "running":
            break
        time.sleep(0.05)
    assert status["state"] == "succeeded" and status["kind"] == "download"
    assert status["up_to_date"] == 6 and status["new_rows"] == 0
    assert seen and "BUYCO.NS" in seen[0]


def test_download_disabled_on_read_only_deployment(world, monkeypatch):
    monkeypatch.setenv("ALTRIX_DISABLE_DOWNLOAD", "1")
    processed, _ = world
    calls = []
    c = TestClient(create_app(AltrixService(data_dir=processed, refresher=lambda s, store: calls.append(s) or []),
                              warm=False))
    r = c.post("/api/refresh?download=true")
    assert r.status_code == 403 and "disabled" in r.json()["detail"]
    assert calls == [] and c.get("/api/refresh").json()["state"] == "idle"
    assert c.get("/health").json()["downloads_enabled"] is False
    assert c.get("/api/meta").json()["downloads_enabled"] is False
    assert c.post("/api/refresh").json()["state"] == "succeeded"  # rescanning stored data still works


def test_cors_allows_local_frontend(client):
    r = client.get("/health", headers={"Origin": "http://localhost:3000"})
    assert r.headers.get("access-control-allow-origin") == "http://localhost:3000"
