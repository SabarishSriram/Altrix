import pandas as pd
import pytest

from src.data.provider import normalize


def make_bars(symbol="TEST.NS", start="2024-01-01", days=10, dates=None) -> pd.DataFrame:
    """Valid, sorted OHLCV bars on business days (or on the given dates)."""
    dates = pd.to_datetime(dates) if dates is not None else pd.bdate_range(start, periods=days)
    n = len(dates)
    close = [100.0 + i for i in range(n)]
    raw = pd.DataFrame(
        {
            "date": dates,
            "open": [c - 0.5 for c in close],
            "high": [c + 1.0 for c in close],
            "low": [c - 1.0 for c in close],
            "close": close,
            "volume": [1000 + i for i in range(n)],
        }
    )
    return normalize(raw, symbol)


@pytest.fixture
def bars():
    return make_bars()
