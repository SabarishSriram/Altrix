"""Altrix trading strategies: signal generation only (no execution or backtesting)."""

from .baseline import generate_baseline_signals

__all__ = ["generate_baseline_signals"]
