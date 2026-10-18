"""FastAPI app: REST endpoints over the existing scanner, strategy and backtester.

    uvicorn api.main:app --reload --port 8000      # docs at http://localhost:8000/docs

Environment:
    ALTRIX_CORS_ORIGINS  comma-separated allowed origins (default http://localhost:3000,http://127.0.0.1:3000)
    ALTRIX_DATA_DIR / ALTRIX_RAW_DIR / ALTRIX_OFFLINE  as for the Streamlit app
"""

from __future__ import annotations

import logging
import os
import re
import threading
from contextlib import asynccontextmanager
from datetime import date

import pandas as pd
from fastapi import FastAPI, HTTPException, Path, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app import dashboard as dash

from . import __version__
from . import schemas as s
from .service import STRATEGY, DATA_SOURCE, AltrixService, DataUnavailableError, NotFoundError, iso_date, num, offline_mode

logger = logging.getLogger("altrix.api")

# Yahoo NSE tickers: letters, digits, '&' and '-' (M&M.NS, BAJAJ-AUTO.NS), optional .NS suffix.
SYMBOL_RE = re.compile(r"^[A-Z0-9&-]{1,20}(\.NS)?$")
DEFAULT_ORIGINS = "http://localhost:3000,http://127.0.0.1:3000"


def normalize_symbol(raw: str) -> str:
    symbol = raw.strip().upper()
    if not SYMBOL_RE.fullmatch(symbol):
        raise HTTPException(422, f"Invalid symbol {raw!r}: expected an NSE ticker such as RELIANCE or RELIANCE.NS")
    return symbol if symbol.endswith(".NS") else f"{symbol}.NS"


def create_app(service: AltrixService | None = None, warm: bool = True) -> FastAPI:
    svc = service or AltrixService()

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        if warm:  # scan once in the background so the first page load is fast
            def _warm() -> None:
                try:
                    svc.scan()
                except Exception:
                    logger.exception("Initial scan failed")
            threading.Thread(target=_warm, name="altrix-warm", daemon=True).start()
        yield

    app = FastAPI(
        title="Altrix API",
        version=__version__,
        description="Research API for the NIFTY 100 SMA20/SMA50 crossover scanner and backtester. "
                    "Historical end-of-day data only; not real-time, not investment advice.",
        lifespan=lifespan,
    )
    app.state.service = svc
    origins = [o.strip() for o in os.environ.get("ALTRIX_CORS_ORIGINS", DEFAULT_ORIGINS).split(",") if o.strip()]
    app.add_middleware(CORSMiddleware, allow_origins=origins, allow_methods=["GET", "POST"], allow_headers=["*"])

    @app.exception_handler(DataUnavailableError)
    async def _unavailable(_: Request, exc: DataUnavailableError):
        return JSONResponse(status_code=503, content={"detail": str(exc)})

    @app.exception_handler(NotFoundError)
    async def _not_found(_: Request, exc: NotFoundError):
        return JSONResponse(status_code=404, content={"detail": str(exc)})

    @app.get("/health", response_model=s.HealthResponse, tags=["system"])
    def health():
        """API availability and data status. Never triggers a scan or a download."""
        return {"version": __version__, **svc.health()}

    @app.get("/api/meta", response_model=s.MetaResponse, tags=["system"])
    def meta():
        """Strategy, data source and configuration (read-only)."""
        d = dash.BacktestSettings()
        return {
            "version": __version__,
            "strategy": STRATEGY,
            "data_source": DATA_SOURCE,
            "offline_mode": offline_mode(),
            "backtest_defaults": {"initial_capital": d.initial_capital, "transaction_cost": d.transaction_cost,
                                  "max_position_weight": d.max_position_weight},
        }

    @app.get("/api/scanner", response_model=s.ScannerResponse, tags=["scanner"])
    def scanner():
        """Latest-day BUY / SELL / HOLD for every stock in the universe (cached until the data changes)."""
        result = svc.scanner()
        if result["data_as_of"] is None:
            raise HTTPException(503, "No usable price data. Download it first with: python scripts/download_data.py")
        return result

    @app.get("/api/scanner/{symbol}/history", response_model=s.HistoryResponse, tags=["scanner"])
    def history(
        symbol: str = Path(description="NSE ticker, e.g. RELIANCE.NS or RELIANCE (URL-encode '&')"),
        start: date | None = Query(None, description="First date (inclusive)"),
        end: date | None = Query(None, description="Last date (inclusive)"),
    ):
        """Daily bars with SMA20, SMA50 and the strategy's historical crossover signals."""
        sym = normalize_symbol(symbol)
        if start and end and start > end:
            raise HTTPException(422, f"start {start} is after end {end}")
        return svc.history(sym, None if start is None else pd.Timestamp(start),
                           None if end is None else pd.Timestamp(end))

    @app.get("/api/signals/recent", response_model=s.RecentSignalsResponse, tags=["scanner"])
    def recent_signals(days: int = Query(30, ge=1, le=260, description="Trading days to look back")):
        """Past crossovers across the universe (context only; current signals are the latest day's)."""
        return svc.recent_signals(days)

    @app.get("/api/backtest", response_model=s.BacktestResponse, tags=["backtest"])
    def backtest(
        initial_capital: float = Query(100_000.0, gt=0),
        transaction_cost: float = Query(0.001, ge=0, lt=1, description="Fraction per BUY and per SELL"),
        max_position_weight: float = Query(0.10, gt=0, le=1),
        years: int | None = Query(None, ge=1, le=30, description="Lookback ending on the latest stored date (instead of start/end)"),
        start: date | None = Query(None),
        end: date | None = Query(None),
    ):
        """Run the existing backtester (baseline strategy) on the stored data. Results are cached."""
        start_ts = None if start is None else pd.Timestamp(start)
        end_ts = None if end is None else pd.Timestamp(end)
        if years is not None:
            if start or end:
                raise HTTPException(422, "Use either years or start/end, not both")
            start_ts = svc.market_data()["date"].max() - pd.DateOffset(years=years)
        settings = dash.BacktestSettings(initial_capital, transaction_cost, max_position_weight, start_ts, end_ts)
        try:
            result, data = svc.backtest(settings)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        return _backtest_response(result, data, settings)

    @app.get("/api/refresh", response_model=s.RefreshStatus, tags=["refresh"])
    def refresh_status():
        """Status of the latest rescan or download."""
        return svc.job.to_dict()

    @app.post("/api/refresh", response_model=s.RefreshStatus, tags=["refresh"])
    def refresh(download: bool = Query(False, description="Also fetch new bars from Yahoo Finance (background)")):
        """Rescan the stored data now, or start the incremental downloader (202; poll GET /api/refresh)."""
        if not download:
            return svc.rescan()
        status, started = svc.start_download()
        return JSONResponse(status_code=202 if started else 409, content=status)

    return app


def _backtest_response(result, data: pd.DataFrame, settings: dash.BacktestSettings) -> dict:
    curve = result.equity_curve
    trades = result.trades_frame()
    positions = result.open_positions_frame()
    return {
        "config": {
            "initial_capital": settings.initial_capital,
            "transaction_cost": settings.transaction_cost,
            "max_position_weight": settings.max_position_weight,
            "start": iso_date(settings.start),
            "end": iso_date(settings.end),
        },
        "data_start": iso_date(data["date"].min()),
        "data_end": iso_date(data["date"].max()),
        "symbols": int(data["symbol"].nunique()),
        "metrics": {k: (num(v) if isinstance(v, float) else v) for k, v in result.metrics.items()},
        "equity_curve": [{
            "date": iso_date(r.date), "total_equity": float(r.total_equity), "cash": float(r.cash),
            "invested_value": float(r.invested_value), "positions": int(r.positions), "drawdown": float(r.drawdown),
        } for r in curve.itertuples(index=False)],
        "trades": [{
            **{k: getattr(r, k) for k in ("symbol", "entry_price", "exit_price", "gross_pnl",
                                          "transaction_cost", "net_pnl", "return_pct")},
            "entry_date": iso_date(r.entry_date), "exit_date": iso_date(r.exit_date),
            "quantity": int(r.quantity), "holding_days": int(r.holding_days),
        } for r in trades.itertuples(index=False)],
        "open_positions": [{
            "symbol": r.symbol, "quantity": int(r.quantity), "entry_date": iso_date(r.entry_date),
            "entry_price": float(r.entry_price), "last_price": float(r.last_price),
            "market_value": float(r.market_value), "unrealized_pnl": float(r.unrealized_pnl),
        } for r in positions.itertuples(index=False)],
    }


app = create_app()
