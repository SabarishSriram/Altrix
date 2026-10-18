"""Altrix REST API (FastAPI): a thin JSON layer over src/ for the web frontend.

    uvicorn api.main:app --reload --port 8000

No strategy, scanning or backtesting logic lives here: the API calls
src.scanner, src.strategy and src.backtest and only serialises their output.
"""

__version__ = "0.1.0"
