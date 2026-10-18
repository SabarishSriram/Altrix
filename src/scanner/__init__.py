"""Altrix scanner: latest strategy signals across the stock universe."""

from .opportunity_scanner import (
    BUY,
    HOLD,
    INSUFFICIENT_DATA,
    SCAN_COLUMNS,
    SELL,
    ScanResult,
    recent_crossovers,
    run_universe_scan,
    scan_current_opportunities,
    scan_signals,
)

__all__ = [
    "BUY",
    "HOLD",
    "INSUFFICIENT_DATA",
    "SCAN_COLUMNS",
    "SELL",
    "ScanResult",
    "recent_crossovers",
    "run_universe_scan",
    "scan_current_opportunities",
    "scan_signals",
]
