"""Stock universe: which symbols Altrix tracks.

`UniverseProvider` is the interface. `Nifty100Universe` returns the *current*
NIFTY 100 constituents from the official NSE index CSV. A future
point-in-time implementation (historical membership, to avoid survivorship
bias) can implement the same interface.
"""

from __future__ import annotations

import io
import logging
import urllib.request
from abc import ABC, abstractmethod
from pathlib import Path

import pandas as pd

logger = logging.getLogger(__name__)

# Official constituent files published by NSE Indices. Tried in order.
NIFTY100_URLS = [
    "https://archives.nseindia.com/content/indices/ind_nifty100list.csv",
    "https://www.niftyindices.com/IndexConstituent/ind_nifty100list.csv",
]
# NSE rejects requests without a browser-like User-Agent.
_HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}


class UniverseError(Exception):
    """Raised when the constituent list cannot be obtained or parsed."""


class UniverseProvider(ABC):
    """Interface for anything that returns a list of tradable instruments."""

    @abstractmethod
    def get_constituents(self) -> list[dict]:
        """Return [{"symbol": "RELIANCE.NS", "name": "...", "exchange": "NSE"}, ...]."""


def parse_nse_index_csv(text: str, suffix: str = ".NS") -> list[dict]:
    """Parse an NSE index constituent CSV into universe records.

    NSE's format has columns: Company Name, Industry, Symbol, Series, ISIN Code.
    `suffix` maps NSE symbols to Yahoo tickers (RELIANCE -> RELIANCE.NS).
    """
    try:
        df = pd.read_csv(io.StringIO(text))
    except Exception as exc:
        raise UniverseError(f"could not parse constituent CSV: {exc}") from exc

    df.columns = [c.strip() for c in df.columns]
    if not {"Symbol", "Company Name"} <= set(df.columns):
        raise UniverseError(f"unexpected CSV columns: {list(df.columns)}")

    records = []
    seen = set()
    for _, row in df.iterrows():
        sym = str(row["Symbol"]).strip().upper()
        if not sym or sym == "NAN" or sym in seen:
            continue
        seen.add(sym)
        records.append(
            {"symbol": f"{sym}{suffix}", "name": str(row["Company Name"]).strip(), "exchange": "NSE"}
        )
    if not records:
        raise UniverseError("constituent CSV contained no symbols")
    return records


class Nifty100Universe(UniverseProvider):
    """Current NIFTY 100 constituents from NSE, with a local snapshot fallback.

    Every successful download is saved to `cache_path`. If NSE is unreachable,
    the last saved snapshot is used instead (with a warning).
    """

    def __init__(self, cache_path: Path, urls: list[str] | None = None, timeout: int = 20):
        self.cache_path = Path(cache_path)
        self.urls = urls or NIFTY100_URLS
        self.timeout = timeout

    def get_constituents(self) -> list[dict]:
        errors = []
        for url in self.urls:
            try:
                text = self._fetch(url)
                records = parse_nse_index_csv(text)
                self.cache_path.parent.mkdir(parents=True, exist_ok=True)
                self.cache_path.write_text(text, encoding="utf-8")
                logger.info("Loaded %d constituents from %s", len(records), url)
                return records
            except Exception as exc:
                logger.warning("Universe source failed (%s): %s", url, exc)
                errors.append(f"{url}: {exc}")

        if self.cache_path.exists():
            logger.warning("Using cached constituent snapshot %s", self.cache_path)
            return parse_nse_index_csv(self.cache_path.read_text(encoding="utf-8"))
        raise UniverseError("could not load NIFTY 100 constituents:\n" + "\n".join(errors))

    def _fetch(self, url: str) -> str:
        req = urllib.request.Request(url, headers=_HEADERS)
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            return resp.read().decode("utf-8-sig")
