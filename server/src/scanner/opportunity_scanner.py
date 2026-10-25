"""Current-opportunity scanner: which stocks have a strategy signal *today*?

    Universe -> stored data -> clean -> baseline strategy -> latest row per stock

Signals come only from `src.strategy.baseline.generate_baseline_signals`; this
module just reads the strategy's output on the latest trading day.

Classification of each stock on the scan date (`as_of`, the latest trading day
in the data):

    BUY                SMA20 crossed above SMA50 on `as_of`  (strategy buy_signal)
    SELL               SMA20 crossed below SMA50 on `as_of`  (strategy sell_signal)
    HOLD               no new crossover on `as_of`. This includes stocks whose
                       SMA20 is above SMA50 from an *earlier* crossover; that
                       is not a new BUY.
    INSUFFICIENT_DATA  fewer than 50 bars, so SMA50 (and any signal) is undefined

A signal on `as_of` is computed from that day's close, so it is only known
after the close. A backtest would execute it at the next trading day's open.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from src.data.cleaner import clean
from src.data.downloader import ParquetStore
from src.data.validator import build_trading_calendar
from src.strategy.baseline import LONG_WINDOW, generate_baseline_signals

BUY = "BUY"
SELL = "SELL"
HOLD = "HOLD"
INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
SIGNAL_ORDER = {BUY: 0, SELL: 1, HOLD: 2, INSUFFICIENT_DATA: 3}

SCAN_COLUMNS = [
    "symbol",
    "name",
    "date",  # the stock's latest bar
    "close",
    "sma20",
    "sma50",
    "sma_difference",  # sma20 - sma50
    "signal",  # BUY / SELL / HOLD / INSUFFICIENT_DATA on the scan date
    "signal_date",  # = date for BUY/SELL, empty otherwise
    "last_crossover",  # most recent BUY or SELL signal in the stock's history
    "last_crossover_date",
    "note",
]
_STRATEGY_COLUMNS = ("date", "symbol", "close", "sma20", "sma50", "buy_signal", "sell_signal")


def scan_signals(strategy_frame: pd.DataFrame, as_of: pd.Timestamp | None = None) -> pd.DataFrame:
    """Classify each stock's latest bar from the strategy's own output.

    Args:
        strategy_frame: output of `generate_baseline_signals` (one or more symbols).
        as_of: scan date; defaults to the latest date in the data. Rows after it
            are ignored. A stock without a bar on `as_of` gets HOLD with a note.

    Returns:
        One row per symbol with SCAN_COLUMNS, sorted BUY, SELL, HOLD,
        INSUFFICIENT_DATA, then by symbol. `name` is empty (see run_universe_scan).
    """
    missing = [c for c in _STRATEGY_COLUMNS if c not in strategy_frame.columns]
    if missing:
        raise ValueError(f"scan_signals: missing strategy column(s) {missing}")
    if strategy_frame.empty:
        return pd.DataFrame(columns=SCAN_COLUMNS)

    df = strategy_frame[list(_STRATEGY_COLUMNS)]
    as_of = df["date"].max() if as_of is None else pd.Timestamp(as_of)
    df = df[df["date"] <= as_of]

    rows = []
    for symbol, g in df.groupby("symbol", sort=True):
        g = g.sort_values("date")
        last = g.iloc[-1]
        crossings = g[g["buy_signal"] | g["sell_signal"]]
        last_cross = crossings.iloc[-1] if not crossings.empty else None

        note = ""
        if pd.isna(last["sma50"]):
            signal = INSUFFICIENT_DATA
            note = f"Insufficient historical data ({len(g)} bars; SMA50 needs {LONG_WINDOW})"
        elif last["date"] < as_of:
            signal = HOLD  # no bar on the scan date -> no crossover on the scan date
            note = f"No data for {as_of.date()}; latest bar is {last['date'].date()}"
        elif last["buy_signal"]:
            signal = BUY
        elif last["sell_signal"]:
            signal = SELL
        else:
            signal = HOLD

        rows.append({
            "symbol": symbol,
            "name": "",
            "date": last["date"],
            "close": last["close"],
            "sma20": last["sma20"],
            "sma50": last["sma50"],
            "sma_difference": last["sma20"] - last["sma50"],
            "signal": signal,
            "signal_date": last["date"] if signal in (BUY, SELL) else pd.NaT,
            "last_crossover": None if last_cross is None else (BUY if last_cross["buy_signal"] else SELL),
            "last_crossover_date": pd.NaT if last_cross is None else last_cross["date"],
            "note": note,
        })

    out = pd.DataFrame(rows, columns=SCAN_COLUMNS)
    order = out["signal"].map(SIGNAL_ORDER)
    return out.assign(_o=order).sort_values(["_o", "symbol"]).drop(columns="_o").reset_index(drop=True)


def scan_current_opportunities(data: pd.DataFrame, as_of: pd.Timestamp | None = None) -> pd.DataFrame:
    """Run the baseline strategy on daily bars and classify each stock's latest bar.

    `data` needs at least date, symbol and close. It is not modified.
    """
    if as_of is not None:
        data = data[pd.to_datetime(data["date"]) <= pd.Timestamp(as_of)]
    return scan_signals(generate_baseline_signals(data), as_of)


def recent_crossovers(strategy_frame: pd.DataFrame, trading_days: int = 10) -> pd.DataFrame:
    """BUY/SELL signals from the last `trading_days` dates in the data, newest first.

    These are past signals for context, not current ones: only signals on the
    latest date are "current".
    """
    if strategy_frame.empty:
        return pd.DataFrame(columns=["date", "symbol", "signal", "close", "sma20", "sma50"])
    dates = strategy_frame["date"].drop_duplicates().nlargest(trading_days)
    df = strategy_frame[strategy_frame["date"].isin(dates)
                        & (strategy_frame["buy_signal"] | strategy_frame["sell_signal"])]
    out = df.assign(signal=df["buy_signal"].map({True: BUY, False: SELL}))
    return (out[["date", "symbol", "signal", "close", "sma20", "sma50"]]
            .sort_values(["date", "signal", "symbol"], ascending=[False, True, True])
            .reset_index(drop=True))


@dataclass
class ScanResult:
    table: pd.DataFrame  # one row per scanned stock, SCAN_COLUMNS
    strategy_frame: pd.DataFrame  # full strategy output (for charts), same data the scan used
    as_of: pd.Timestamp | None  # latest trading date in the data
    universe_size: int
    failed: dict[str, str] = field(default_factory=dict)  # symbol -> reason it was not scanned

    def with_signal(self, *signals: str) -> pd.DataFrame:
        return self.table[self.table["signal"].isin(signals)].reset_index(drop=True)

    def counts(self) -> dict[str, int]:
        return {s: int((self.table["signal"] == s).sum()) for s in SIGNAL_ORDER}


def run_universe_scan(
    universe: list[dict],
    store: ParquetStore,
    as_of: pd.Timestamp | None = None,
) -> ScanResult:
    """Scan every stock in `universe` using the locally stored data.

    A stock whose data is missing, unreadable or empty is recorded in
    `failed` and skipped; it never stops the scan. Data is cleaned exactly as
    `load_clean` does (Yahoo holiday placeholders and filler bars removed,
    nothing filled), with the trading calendar inferred from every readable
    stored file.
    """
    names = {u["symbol"]: u.get("name", "") for u in universe}
    stored = set(store.symbols())

    frames: dict[str, pd.DataFrame] = {}
    failed: dict[str, str] = {}
    for symbol in sorted(stored):  # read everything once: the calendar needs all of it
        try:
            frames[symbol] = store.load(symbol)
        except Exception as exc:
            if symbol in names:
                failed[symbol] = f"could not read stored data: {exc}"
    for symbol in names:
        if symbol not in stored:
            failed[symbol] = "no stored data (run: python scripts/download_data.py)"

    calendar = build_trading_calendar(list(frames.values()))
    cleaned = []
    for symbol in names:
        if symbol not in frames:
            continue
        data = clean(frames[symbol], symbol, calendar).data
        if data.empty:
            failed[symbol] = "no valid rows after cleaning"
        else:
            cleaned.append(data)

    if not cleaned:
        return ScanResult(pd.DataFrame(columns=SCAN_COLUMNS), pd.DataFrame(), None, len(names), failed)

    data = pd.concat(cleaned, ignore_index=True)
    if as_of is not None:
        data = data[data["date"] <= pd.Timestamp(as_of)]
    strategy = generate_baseline_signals(data)
    table = scan_signals(strategy, as_of)
    table["name"] = table["symbol"].map(names).fillna("")
    return ScanResult(
        table=table,
        strategy_frame=strategy,
        as_of=strategy["date"].max() if as_of is None else pd.Timestamp(as_of),
        universe_size=len(names),
        failed=dict(sorted(failed.items())),
    )
