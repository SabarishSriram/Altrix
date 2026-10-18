"""Altrix market-data layer: universe, providers, storage, validation, cleaning, targets."""

from .cleaner import CleanResult, clean, load_clean
from .downloader import DownloadResult, ParquetStore, download_all, update_symbol, validate_all
from .provider import COLUMNS, SCHEMA, MarketDataProvider, ProviderError, YahooFinanceProvider
from .target import add_medium_term_target
from .universe import Nifty100Universe, UniverseProvider, parse_nse_index_csv
from .validator import ValidationReport, build_trading_calendar, validate

__all__ = [
    "COLUMNS",
    "SCHEMA",
    "CleanResult",
    "clean",
    "load_clean",
    "DownloadResult",
    "MarketDataProvider",
    "Nifty100Universe",
    "ParquetStore",
    "ProviderError",
    "UniverseProvider",
    "ValidationReport",
    "YahooFinanceProvider",
    "add_medium_term_target",
    "build_trading_calendar",
    "download_all",
    "parse_nse_index_csv",
    "update_symbol",
    "validate",
    "validate_all",
]
