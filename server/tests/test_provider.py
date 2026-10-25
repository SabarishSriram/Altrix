from datetime import date

import pandas as pd
import pytest

from src.data.provider import (
    COLUMNS,
    SCHEMA,
    MarketDataProvider,
    ProviderError,
    YahooFinanceProvider,
)


def test_interface_cannot_be_instantiated():
    with pytest.raises(TypeError):
        MarketDataProvider()


def test_subclass_must_implement_get_daily_history():
    class Incomplete(MarketDataProvider):
        pass

    with pytest.raises(TypeError):
        Incomplete()


def test_yahoo_provider_is_a_market_data_provider():
    assert isinstance(YahooFinanceProvider(), MarketDataProvider)


def _yahoo_like_frame():
    """Shape of yfinance Ticker.history(auto_adjust=False) output for an NSE stock."""
    idx = pd.DatetimeIndex(
        ["2024-01-02", "2024-01-01", "2024-01-03"], tz="Asia/Kolkata", name="Date"
    )
    return pd.DataFrame(
        {
            "Open": [101.0, 100.0, 102.0],
            "High": [103.0, 102.0, 104.0],
            "Low": [100.0, 99.0, 101.0],
            "Close": [102.0, 101.0, 103.0],
            "Adj Close": [98.0, 97.0, 99.0],
            "Volume": [2000, 1000, 3000],
        },
        index=idx,
    )


class _FakeTicker:
    def __init__(self, frame=None, exc=None):
        self.frame, self.exc = frame, exc

    def history(self, **kwargs):
        if self.exc:
            raise self.exc
        return self.frame


def test_yahoo_provider_normalizes_schema(monkeypatch):
    import yfinance

    monkeypatch.setattr(yfinance, "Ticker", lambda s: _FakeTicker(_yahoo_like_frame()))
    df = YahooFinanceProvider().get_daily_history("ABC.NS", date(2024, 1, 1), date(2024, 1, 3))

    assert list(df.columns) == COLUMNS
    assert {c: str(t) for c, t in df.dtypes.items()} == SCHEMA
    # sorted, tz-naive, end-exclusive, symbol filled in
    assert list(df["date"]) == [pd.Timestamp("2024-01-01"), pd.Timestamp("2024-01-02")]
    assert (df["symbol"] == "ABC.NS").all()
    assert df["close"].tolist() == [101.0, 102.0]  # raw close, not Adj Close


def test_yahoo_provider_empty_response(monkeypatch):
    import yfinance

    monkeypatch.setattr(yfinance, "Ticker", lambda s: _FakeTicker(pd.DataFrame()))
    df = YahooFinanceProvider().get_daily_history("ABC.NS", date(2024, 1, 1), date(2024, 2, 1))
    assert df.empty and list(df.columns) == COLUMNS


def test_yahoo_provider_raises_provider_error_after_retries(monkeypatch):
    import yfinance

    monkeypatch.setattr(yfinance, "Ticker", lambda s: _FakeTicker(exc=ConnectionError("boom")))
    provider = YahooFinanceProvider(retries=1, pause_seconds=0)
    with pytest.raises(ProviderError, match="boom"):
        provider.get_daily_history("ABC.NS", date(2024, 1, 1), date(2024, 2, 1))
