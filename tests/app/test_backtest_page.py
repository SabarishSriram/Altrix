"""Smoke tests that execute the real Backtest page headlessly (no browser)."""

from datetime import date
from pathlib import Path

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from app import dashboard as dash

from .test_dashboard import write_market

APP = str(Path(__file__).resolve().parents[2] / "app" / "views" / "backtest.py")


def app_with_data(monkeypatch, directory) -> AppTest:
    monkeypatch.setenv("ALTRIX_DATA_DIR", str(directory))
    at = AppTest.from_file(APP, default_timeout=120)
    at.run()
    return at


def test_initial_state_asks_to_run_backtest(tmp_path, monkeypatch):
    at = app_with_data(monkeypatch, write_market(tmp_path / "p"))
    assert not at.exception
    assert at.title[0].value == "Altrix"
    assert any("Run a backtest to view results." in i.value for i in at.info)
    assert at.selectbox[0].value == dash.STRATEGY_NAME and at.selectbox[0].disabled


def test_run_backtest_displays_result_metrics(tmp_path, monkeypatch):
    directory = write_market(tmp_path / "p")
    at = app_with_data(monkeypatch, directory)
    at.button[0].click().run()
    assert not at.exception and not at.error

    expected = dash.run_dashboard_backtest(dash.load_market_data(directory), dash.BacktestSettings(
        start=pd.Timestamp(at.date_input[0].value), end=pd.Timestamp(at.date_input[1].value)))
    # The first ten metric cards are the performance section, in order.
    cards = dash.headline_metrics(expected) + dash.trade_metrics(expected)
    shown = [(m.label, m.value) for m in at.metric][: len(cards)]
    assert shown == [(c.label, c.value) for c in cards]
    assert expected.metrics["completed_trades"] > 0
    assert {"Portfolio Equity Over Time", "Drawdown", "Trade Analysis", "Stock Analysis",
            "Portfolio Summary", "Download Results"} <= {s.value for s in at.subheader}


def test_selecting_a_stock_updates_stock_section(tmp_path, monkeypatch):
    at = app_with_data(monkeypatch, write_market(tmp_path / "p"))
    at.button[0].click().run()
    stock = next(s for s in at.selectbox if s.label == "Select Stock")
    stock.set_value("CCC.NS").run()
    assert not at.exception
    assert next(s for s in at.selectbox if s.label == "Select Stock").value == "CCC.NS"


def test_invalid_date_range_shows_error(tmp_path, monkeypatch):
    at = app_with_data(monkeypatch, write_market(tmp_path / "p"))
    at.date_input[0].set_value(date(2023, 12, 1))
    at.date_input[1].set_value(date(2023, 6, 1))
    at.button[0].click().run()
    assert not at.exception
    assert any("after end date" in e.value for e in at.error)


def test_missing_data_shows_clear_error(tmp_path, monkeypatch):
    at = app_with_data(monkeypatch, tmp_path / "nothing_here")
    assert not at.exception
    assert any("No processed market data" in e.value for e in at.error)
