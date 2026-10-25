"""Altrix trading strategies: signal generation only (no execution or backtesting)."""

from .baseline import generate_baseline_signals
from .smart_money import add_smart_money_footprint, generate_smart_money_signals

__all__ = ["add_smart_money_footprint", "generate_baseline_signals", "generate_smart_money_signals"]
