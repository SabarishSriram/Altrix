# Altrix

Altrix is a Python quantitative trading platform for Indian equities, built in small steps:

```
NIFTY 100 → market data → feature engineering → ML models → backtesting → live dashboard → automated trading
                ▲
          you are here (Step 1)
```

**Step 1 (this repo today)** is the market-data ingestion layer. It finds the current NIFTY 100
constituents, downloads about 10 years of daily price history for each stock, normalizes it,
validates it, and caches it locally as Parquet.

## Repository layout

```
altrix/
  server/    Python: data pipeline, strategy, backtester, scanner, FastAPI (api/), Streamlit (app/), tests
  client/    Next.js web app that calls the API
  .github/   GitHub Actions (daily data update + API deploy)
```

**Run every Python command from `server/`.** Python paths in this README (`scripts/...`, `src/...`,
`data/processed/`) are relative to `server/`. Frontend commands run from `client/`.

---

## What is OHLCV?

Each row is one trading day ("daily bar") for one stock:

| Field    | Meaning                                                   |
|----------|-----------------------------------------------------------|
| `open`   | First traded price of the day                             |
| `high`   | Highest traded price of the day                           |
| `low`    | Lowest traded price of the day                            |
| `close`  | Last traded price of the day                              |
| `volume` | Number of shares traded that day                          |

Every valid bar satisfies `low ≤ open, close ≤ high`, all prices are `> 0`, and volume is `≥ 0`.

## Why yfinance?

[yfinance](https://github.com/ranaroussi/yfinance) is a free Python library that reads
Yahoo Finance's public endpoints. It covers NSE stocks (`RELIANCE.NS`) and needs no API key or
broker account, which makes it a good way to bootstrap research. All vendor-specific code sits
behind `MarketDataProvider`, so it can be swapped out later.

The constituent list comes straight from NSE Indices' official file
(`ind_nifty100list.csv`). Nothing is hardcoded.

## Limitations of free Yahoo Finance data

Read this before you trust any backtest built on this data.

- **Unofficial and unsupported.** Yahoo can change or rate-limit its endpoints at any time.
  yfinance breaks occasionally and needs upgrading (`pip install -U yfinance`).
- **Placeholder bars on holidays.** Yahoo sometimes returns a fake bar on an NSE holiday,
  with open = high = low = close and volume = 0. The validator detects these and reports them.
  The raw Parquet files keep what Yahoo returned. Load data through `load_clean()` (see
  [Loading clean data](#loading-clean-data)), which removes these rows.
- **Split-adjusted, not dividend-adjusted.** We store Yahoo's `auto_adjust=False` prices. These
  are adjusted for splits and bonuses but not for dividends. When a stock splits, Yahoo restates
  its entire history, so already-stored rows go stale. Run `--full-refresh` periodically, or
  after a known corporate action.
- **Survivorship bias.** The universe is *today's* NIFTY 100. Stocks that were in the index in
  2017 but have since dropped out are missing, which makes historical results look better than
  reality. `UniverseProvider` exists so that a point-in-time membership source can replace it.
- **Renamed or demerged tickers.** Some history may be short or missing. For example, Tata
  Motors' demerged entities (`TMCV.NS`, `TMPV.NS`) and new listings like `HYUNDAI.NS` only go
  back to their listing or rename date.
- **Occasional bad ticks and zero-volume days.** These are reported, never "fixed".
- **Delayed, not real-time,** and not suitable for live order decisions.

## Installation

Requires Python 3.11+. On Windows (PowerShell):

```powershell
cd C:\Webdev\altrix\server
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

On macOS/Linux:

```bash
cd altrix/server
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
```

Run the tests. They are offline and never call Yahoo or NSE:

```bash
pytest
```

## Downloading the dataset

```bash
python scripts/download_data.py                  # first run: ~10 years; later runs: only new bars
python scripts/download_data.py -v               # show per-symbol progress
python scripts/download_data.py --full-refresh   # ignore cache, re-download everything
python scripts/download_data.py --years 5        # shorter history on first download
python scripts/download_data.py --symbols RELIANCE.NS TCS.NS
```

The exit code is `0` when every symbol downloaded and validated without errors, and `1`
otherwise. A failing symbol never stops the others.

**Caching and incremental updates.** For each symbol, the downloader reads the last stored date
and requests only bars after it. Today's bar is fetched only after 16:00 IST, once the NSE
session has closed, so a partial intraday bar is never stored as a daily bar. No future dates
are ever requested.

## Where the data is stored

```
data/
  raw/
    nifty100_constituents.csv      # last successfully downloaded NSE constituent file
                                   # (used as fallback if NSE is unreachable)
  processed/
    RELIANCE.NS.parquet            # one file per symbol
    TCS.NS.parquet
    ...
```

Schema of every Parquet file:

| column   | dtype            | notes                                   |
|----------|------------------|-----------------------------------------|
| `date`   | `datetime64[ns]` | trading date (IST calendar date, no tz) |
| `symbol` | `string`         | Yahoo ticker, e.g. `RELIANCE.NS`        |
| `open`   | `float64`        | INR                                     |
| `high`   | `float64`        | INR                                     |
| `low`    | `float64`        | INR                                     |
| `close`  | `float64`        | INR, split-adjusted                     |
| `volume` | `Int64`          | nullable int, shares                    |

Rows are sorted by `date` with no duplicate dates. Load the data with:

```python
import pandas as pd
df = pd.read_parquet("data/processed/RELIANCE.NS.parquet")
```

## Example output

```
NIFTY 100 stocks found: 100
Requesting 100 symbol(s), 2016-10-05 -> 2026-10-05 (end exclusive) ...

========================================================
NIFTY 100 stocks found: 100
Stocks downloaded:      100  (new 100, updated 0, up to date 0)
Failed:                 0
New rows this run:      226,933
Total rows:             226,933
Date range:             2016-10-05 -> 2026-10-01
Stored in:              C:\Webdev\altrix\server\data\processed
========================================================

Validation: 85 clean, 15 with stock-specific warnings, 0 with errors
  NOTE     Yahoo placeholder bars on 6 market holiday(s) in 100 symbol(s): 2025-03-18, 2026-01-15, ...
  WARNING  DLF.NS: 5 zero-volume bar(s) on trading days
  ...
```

A failure looks like this:

```
Failed:                 1
  FAILED  XYZ.NS: XYZ.NS: HTTP Error 404 ...
```

## How validation works

`src/data/validator.py` checks each symbol for:

| Check                                   | Severity |
|-----------------------------------------|----------|
| Schema (column names, order, dtypes)    | error    |
| Duplicate dates                         | error    |
| Not sorted chronologically              | error    |
| Missing open/high/low/close/volume      | error    |
| `low ≤ open, close ≤ high` violated     | error    |
| Price ≤ 0, volume < 0                   | error    |
| Suspicious missing trading day          | warning  |
| Bar on a non-trading day (placeholder)  | warning  |
| Zero volume on a trading day            | warning  |
| One-day close drop of 35% or more       | warning  |

**Holidays vs. suspicious gaps.** No free, official NSE holiday API exists, so the trading
calendar is inferred from the data. A date counts as a trading day if at least half of the stocks
listed at the time traded on it (volume > 0). This means:

- Weekends and NSE holidays are never flagged as missing.
- Special sessions (Diwali Muhurat trading, Budget-day Saturdays) count as trading days.
- A trading day missing for one stock, inside that stock's own listed period, is flagged as
  **suspicious**.
- Missing days are **never** filled with synthetic OHLCV values.

**Possible corporate actions.** A one-day close-to-close fall of 35% or more is flagged
(`report.corporate_action_suspects`, `large_price_drops()`), because Yahoo often leaves demergers unadjusted
for a while. On the current data it flags `VEDL.NS` 2026-04-30 (−64.9%), `TMPV.NS` 2025-10-14 (−40.2%) and
`IDEA.NS` 2020-03-18 (−35.1%, a real crash). The flag asks you to verify the price history; nothing is
adjusted or removed, so the backtester still trades through these days. For example, the baseline buys VEDL on
2026-04-17 and sells it on 2026-05-06 at −60.5%, a loss that the demerger, not the market, created.

## Loading clean data

The Parquet files hold exactly what the provider returned. For any analysis, load data through
the cleaner instead of reading the files directly:

```python
from src.data import ParquetStore, load_clean

result = load_clean(ParquetStore("data/processed"), ["RELIANCE.NS"])["RELIANCE.NS"]
df = result.data        # same schema as above, sorted, unique dates
result.removed          # {'holiday': 6}: what was dropped and why
result.gaps             # trading days with no bar (never filled)
```

Cleaning only **removes** rows. It never fills or edits values:

| Reason      | Rows removed                                                              |
|-------------|---------------------------------------------------------------------------|
| `holiday`   | bar on a date the market did not trade (Yahoo placeholder)                |
| `filler`    | volume 0 and open = high = low = close: no trade, provider repeated price |
| `invalid`   | missing values, price ≤ 0, volume < 0, low/high not bracketing open/close |
| `duplicate` | repeated date (last kept)                                                 |

A removed `filler` or `invalid` row on a trading day becomes a **gap** and is listed in
`result.gaps`. Code that compares consecutive rows (returns, for example) must account for gaps
rather than assume rows are one trading day apart.

The trading calendar is always inferred from every stored symbol, so cleaning one symbol gives
the same result as cleaning all of them.

On the current dataset, cleaning keeps 226,310 of 226,933 rows. It removes 587 holiday
placeholder rows and 36 filler bars. 15 symbols are left with 1–5 gap days each.

## Running a backtest

```bash
python scripts/run_backtest.py                                  # all stored stocks, defaults
python scripts/run_backtest.py --capital 500000 --cost 0.002 --weight 0.05
python scripts/run_backtest.py --symbols RELIANCE.NS TCS.NS INFY.NS
```

The backtester uses only the data in `data/processed/`, cleaned with `load_clean()`. It never
downloads anything. Results go to `data/results/baseline_sma/`:

| File                 | Contents                                                            |
|----------------------|---------------------------------------------------------------------|
| `metrics.json`       | config + summary metrics                                            |
| `equity_curve.csv`   | one row per trading day: cash, invested_value, total_equity, positions, drawdown |
| `trades.csv`         | completed round trips with P&L, costs, return, holding days        |
| `executions.csv`     | every BUY/SELL fill (for chart markers)                             |
| `signals.csv`        | every strategy signal and what happened to it                      |
| `open_positions.csv` | positions still held on the last day                               |

**V1 rules:**

- **Timing.** A signal on day T is decided after T's close. It fills at the **open of that
  stock's next trading row**, never at T's close. A signal on a stock's last available row is
  not executed.
- **Daily order.** SELLs fill first, then BUYs (so sale proceeds can be reused the same
  morning). Positions are then marked to market at the close, which gives one equity-curve row.
- **Long-only.** One position per stock, always sold in full. No shorting, leverage or
  fractional shares.
- **Sizing.** BUYs filling on the same day are ranked by their **20-day rate of change** at the signal close
  (`close / close 20 rows earlier − 1`, highest first; stocks without 20 rows of history last, then by symbol),
  so the order never depends on file or alphabetical order. In that order each BUY gets
  `min(max_position_weight × equity at previous close, cash left)`. Quantity is
  `floor(budget / (open × (1 + cost)))`, so fees fit inside the budget and cash never goes negative.
- **Minimum position.** A BUY is skipped unless its budget is at least `min_position_weight` (default 5%) of
  equity, so a nearly empty cash balance never buys a ₹1,000 "cash dust" position. The old rule split cash
  equally and made 500 such sub-₹5,000 BUYs over 10 years; pass `min_position_weight=0` to allow small
  budgets again.
- **Costs.** A flat `transaction_cost` (default 0.1%) on every BUY and SELL. No STT, GST,
  stamp duty or slippage yet.
- **Ignored signals** are recorded with a reason in `signals.csv`:
  - `ignored_already_held`: BUY for a stock already held
  - `ignored_not_held`: SELL for a stock not held
  - `no_next_day`: signal on a stock's last row
  - `invalid_open`: missing, zero or negative open price
  - `below_min_position`: budget below `min_position_weight` of equity
  - `insufficient_cash`: budget too small for one share
- **Benchmark.** `run_backtest(..., benchmark=series)` adds a buy-and-hold comparison if you
  pass in a price series. None is downloaded.

**Survivorship bias.** The universe is *today's* NIFTY 100, so results are inflated: stocks
that fell out of the index since 2016 are missing.

## Smart Money (institutional footprint)

`src/strategy/smart_money.py` reads institutional footprints from the stored daily OHLCV. Per stock, per day
(every window looks backwards; rows are the stock's own trading days):

| Column | Rule |
|---|---|
| `vol_spike_ratio` | `volume / volume.rolling(20).mean()` (today included) |
| `clv` | close location value `(close - low) / (high - low)`: 1 = closed at the high; empty when high = low |
| `pocket_pivot` | up close, **and** volume above every down-day volume of the prior 10 trading days (0 if there were none), **and** `close >= 0.95 × SMA50` |
| `institutional_accumulation` | up close, `vol_spike_ratio >= 2.0` and `clv >= 0.5` |
| `smart_money_active_10d` | a pocket pivot or accumulation on any of the last 10 trading days (today included) |

**Smart-money filtered SMA 20/50** (`generate_smart_money_signals`): the baseline SELL rule, but a BUY needs
either an SMA20 ↑ SMA50 crossover **with** `smart_money_active_10d`, or a fresh pocket pivot that closes within
5% of SMA20 while SMA20 was already above SMA50 (yesterday and today). The unfiltered crossover stays available
as `baseline_buy_signal`.

**Optional NSE delivery data.** `python scripts/download_deliverables.py` (default: last 45 days, only days not
stored yet) downloads NSE's daily `sec_bhavdata_full_DDMMYYYY.csv`, keeps `SERIES == "EQ"` rows for the NIFTY
100, and stores `DELIV_QTY` / `DELIV_PER` in `data/deliverables/deliverables.parquet`
(`src/data/deliverables.py`). `deliv_spike_ratio = DELIV_QTY / DELIV_QTY.rolling(20).mean()`, flagged as a
delivery spike when it is `>= 2.0` and `DELIV_PER >= 55`. Weekends are skipped; holidays return no file (or the
previous session's file, which is ignored). Nothing else depends on this data: without it, delivery columns are
simply empty. The deployed API gets it when the daily workflow can reach NSE.

**Scanner.** `src/scanner/smart_money_scan.py` takes each stock's latest bar, ranked by `vol_spike_ratio`. A stock
with no bar on the scan date keeps a note and no footprint values, so a stale spike is never ranked as today's.

**Comparison.** With the same settings over the last 10 years of stored data (to 16 Oct 2026):

| | Baseline SMA 20/50 | Smart-Money filtered |
|---|---|---|
| CAGR | 14.2% | 19.2% |
| Max drawdown | −32.1% | −29.4% |
| Profit factor | 1.73 | 2.00 |
| Win rate | 40.0% | 46.2% |
| Expectancy (net P&L per trade) | ₹624 | ₹995 |
| Completed trades | 433 | 461 |

The rules and thresholds were fixed in advance, not tuned, but this is still one in-sample run on a
survivorship-biased universe: treat it as a reason to research further, not as evidence of an edge.

## The Altrix app (Opportunity Scanner + Backtest)

```bash
cd altrix/server
.\.venv\Scripts\Activate.ps1        # Windows (source .venv/bin/activate on macOS/Linux)
pip install -r requirements.txt            # includes streamlit and plotly
python scripts/download_data.py            # once, if data/processed/ is empty
streamlit run app/streamlit_app.py         # opens http://localhost:8501
```

The app has two pages, listed in the sidebar:

- **Opportunity Scanner** (default): which NIFTY 100 stocks have a 20/50 SMA crossover signal
  on the latest trading day.
- **Backtest**: the historical simulation of the same strategy (see below).

### Opportunity Scanner

`src/scanner/` takes the constituent list from `src/data/universe.py` and the stored prices
(cleaned with the same rules as `load_clean`). It runs the existing strategy
(`src/strategy/baseline.py`) and reads each stock's latest bar. The page itself computes no
signals.

| Signal | Meaning on the latest trading day ("Data as of") |
|---|---|
| **BUY** | SMA20 crossed **above** SMA50 that day |
| **SELL** | SMA20 crossed **below** SMA50 that day |
| **HOLD** | no new crossover that day. A stock whose SMA20 has been above SMA50 since an earlier crossover is HOLD, **not** BUY |
| **Insufficient historical data** | fewer than 50 bars, so SMA50 and any signal are undefined |

The page shows:
- **Header:** "Data as of" date, universe and strategy.
- **Signal sections:** Current BUY Signals, Current SELL Signals, recent crossovers from the
  last 10 trading days (for context), and the full 100-stock table (sortable).
- **Stock Details:** price, SMA20, SMA50, today's signal, the last crossover, and a 6-month
  chart with the strategy's crossover markers.

**Timing.** Data is end-of-day, not real-time. A signal dated D uses D's closing price, so it is
known only after the close. The backtester would act on it at the next trading day's open.
These are research signals from a baseline strategy, not investment advice.

**Refresh Data** runs the existing incremental downloader (the same as
`python scripts/download_data.py`). It fetches only bars newer than what is stored, then
re-scans. Nothing polls automatically. The scan is cached until the stored data changes, so
selecting a stock doesn't re-scan.

**Missing data.** A constituent without stored data is listed in a warning and skipped. This
happens, for example, after NSE changes the index, until you run the downloader. A stock with no
bar on the latest date is shown as HOLD, with a note, never as a stale BUY.

Environment overrides:
- `ALTRIX_DATA_DIR`: processed data folder.
- `ALTRIX_RAW_DIR`: constituent snapshot folder.
- `ALTRIX_OFFLINE=1`: use only the local constituent snapshot, never NSE.

## Backtesting dashboard

The **Backtest** page of the app is for exploring backtest results. It only displays results: every
number and chart comes from the existing backtester (`run_backtest`), and the dashboard never
calculates signals, trades or metrics itself. Open it from the sidebar of
`streamlit run app/streamlit_app.py`.

1. In the sidebar, set initial capital, transaction cost, maximum position weight and a date
   range. The strategy is fixed to *20 / 50 SMA Crossover* for now.
2. Click **Run Backtest**. Data is loaded from `data/processed/` once and cached. Nothing is
   downloaded. A full 10-year, 100-stock run takes about 2 seconds after the first load
   (about 13 seconds).

The dashboard shows:

| Section | Contents |
|---|---|
| Performance | initial capital, final value, total return, max drawdown, trades, win rate, winning/losing trades, average trade return, CAGR |
| Portfolio Equity Over Time | daily total equity vs initial capital (hover for ₹ value) |
| Drawdown | % below the previous equity peak, every day |
| Trade Analysis | winning vs losing trades, distribution of trade returns, sortable table of all completed trades |
| Stock Analysis | pick a stock: close + SMA20 + SMA50, BUY/SELL markers (filled = executed next open, hollow = not traded, hover for the reason), its trades, realized P&L, win rate |
| Portfolio Summary | final cash / invested / total, open positions with current price and unrealized P&L |
| Download Results | trades CSV and equity-curve CSV, generated in memory |

**Date range.** The SMAs are warmed up on the history *before* the start date, so signals
inside the range match a full-history run. The portfolio always starts in cash on the start
date. Data after the end date is never seen by the strategy.

**Current limitations:**
- One strategy only.
- No benchmark line yet: no index data is stored.
- Results are kept for the browser session only. Changing settings shows a warning until you
  re-run.
- The return % column in tables uses Streamlit's percent format.
- Survivorship bias (today's NIFTY 100 constituents) applies here as in the CLI backtest.
- Research only: there is no live data, paper trading or order placement.

To use a different data folder, set `ALTRIX_DATA_DIR=/path/to/processed`.

## Web app (Next.js + FastAPI)

A research terminal for the scanner and backtester:

```
Next.js (client/, :3000)  ->  FastAPI (server/api/, :8000)  ->  server/src/ (universe, strategy, scanner, backtest)  ->  server/data/processed/*.parquet
```

The frontend only calls the API. It never reads Parquet files or contacts Yahoo/NSE, and it contains no
strategy logic: every signal, SMA and metric comes from the Python modules.

### Start both services

Requires Node.js 20+ and the Python setup above.

```powershell
# Terminal 1: API
cd server
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn api.main:app --reload --port 8000        # docs: http://localhost:8000/docs

# Terminal 2: frontend
cd client
npm install
copy .env.example .env.local                      # cp on macOS/Linux
npm run dev                                       # http://localhost:3000
```

For a production build: `npm run build` then `npm start` in `client/`.

The API scans once in the background at startup (about 10-15 s) and caches the result until the stored
data changes, so later requests are fast.

### Environment variables

| Variable | Where | Default | Purpose |
|---|---|---|---|
| `NEXT_PUBLIC_API_BASE_URL` | `client/.env.local` | `http://localhost:8000` | API base URL used by the browser |
| `ALTRIX_CORS_ORIGINS` | API | `http://localhost:3000,http://127.0.0.1:3000` | allowed frontend origins (comma-separated) |
| `ALTRIX_DATA_DIR` | API | `data/processed` | processed Parquet folder |
| `ALTRIX_RAW_DIR` | API | `data/raw` | constituent snapshot folder |
| `ALTRIX_OFFLINE` | API | unset | `1` = read the constituent list only from the local snapshot |
| `ALTRIX_DELIVERABLES_DIR` | API | `data/deliverables` | optional NSE deliverables folder |
| `ALTRIX_DISABLE_DOWNLOAD` | API | unset | `1` = reject `POST /api/refresh?download=true` with 403 and hide *Download new bars* in the web app (read-only deployments) |

### Endpoints

| Method | Path | Description |
|---|---|---|
| GET | `/health` | API and data status. Never scans or downloads |
| GET | `/api/meta` | strategy, data source, offline mode, backtest defaults |
| GET | `/api/scanner` | latest-day BUY/SELL/HOLD for every constituent, with counts and failed symbols |
| GET | `/api/scanner/{symbol}/history?start=&end=` | daily bars with SMA20, SMA50 and the strategy's historical crossovers |
| GET | `/api/signals/recent?days=30` | past crossovers and per-day BUY/SELL counts (context only) |
| GET | `/api/smart-money` | latest-day footprint for every constituent, ranked by `vol_spike_ratio`, with NSE delivery columns when stored |
| GET | `/api/backtest?initial_capital=&transaction_cost=&max_position_weight=&min_position_weight=&strategy=&years=` (or `start=&end=`) | runs `run_backtest`; `years` looks back from the latest stored date: metrics (incl. profit factor, expectancy), equity curve, trades, open positions. `strategy=smart_money` also returns `comparison` with the baseline |
| POST | `/api/refresh` | rescan the stored data now |
| POST | `/api/refresh?download=true` | start the incremental downloader in the background (202, 409 if one is running, 403 if `ALTRIX_DISABLE_DOWNLOAD=1`) |
| GET | `/api/refresh` | status of the latest rescan or download |

Symbols are NSE tickers (`RELIANCE.NS` or `RELIANCE`). URL-encode `&`: `M%26M.NS`. Invalid symbols return
422, unknown or unavailable ones 404, and missing data or universe 503.

`daily_change_pct` is in percent, measured against the stock's previous stored bar (`previous_date`). Backtest
returns are fractions (0.05 = +5%), as in the backtester.

### Pages

- **Overview:** scan summary, today's BUY/SELL list, crossovers per day over the last 30 trading days (strategy
  history across today's constituents; no scan snapshots are stored), recent crossovers.
- **Stock Scanner:** summary cards, All/BUY/SELL/HOLD tabs, sortable and searchable table. On wide screens,
  clicking a row opens a preview panel; the chart icon opens the full analysis.
- **Stock Analysis:** stock picker, plus a detail page with an interactive close/SMA20/SMA50 chart
  (1M/3M/6M/1Y/ALL, volume pane, BUY/SELL markers from the strategy), crossovers per year and full signal history.
- **Smart Money:** footprint counts, All / Pocket pivots / Accumulation / Active-in-10-days tabs, and a sortable table
  ranked by volume spike: close, 1D %, volume spike, CLV, pocket pivot, accumulation, 10-day memory, SMA 20/50
  trend, and delivery spike / delivered % when NSE delivery data is stored.
- **Backtesting:** runs the existing backtester over the last 1, 2, 3, 5 or 10 years: metrics, equity curve, drawdown, trades,
  open positions. *Require 10-Day Smart Money Confirmation for SMA 20/50 Entry* runs the filtered strategy and adds a
  side-by-side comparison (CAGR, max drawdown, profit factor, win rate, expectancy, trade count) with the baseline.
- **Settings:** read-only view of the configuration that exists (API URL, data source, strategy rules,
  backtest defaults).
- **Refresh** (top bar): *Rescan stored data*, or *Download new bars* (the same incremental downloader as
  `scripts/download_data.py`, then a rescan). Nothing downloads automatically.

The Streamlit app (`streamlit run app/streamlit_app.py`) still works. It uses the same backtester (so the new sizing
rules apply) but has no Smart Money page.

## Deployment (Vercel, free tier)

Both halves run on Vercel as two projects:

```
altrix-web  (Next.js, client/, deployed from GitHub on every push)
    -> altrix-api  (FastAPI as one Vercel Function, deployed by GitHub Actions with the data bundled in)
```

Vercel Functions have no persistent disk and stop between requests, so the deployed API is **read-only**:
`ALTRIX_OFFLINE=1` and `ALTRIX_DISABLE_DOWNLOAD=1` are set by `server/deploy/vercel-api/index.py`, and *Download new
bars* is hidden. Fresh data comes from `.github/workflows/deploy-api.yml` instead. On weekdays at 18:00 IST it
restores the stored Parquet files from the Actions cache, runs the tests, runs `scripts/download_data.py`
(new bars only) and, best effort, `scripts/download_deliverables.py`, stages the API with `scripts/stage_api_deploy.py` and deploys it. It also runs on pushes to
`main` that touch the API under `server/`, and from the Actions tab (*Run workflow*). The first run downloads the full 10 years.

`scripts/stage_api_deploy.py OUT_DIR` copies only what the API needs (`api/`, `src/`, two `app/` modules, the
Parquet files, the constituent snapshot and `deploy/vercel-api/`) into `OUT_DIR`. The API's dependencies are
pinned in `deploy/vercel-api/requirements.txt` (about 310 MB installed; Vercel's Python limit is 500 MB), and CI
runs the tests on those exact versions with Python 3.12, the version Vercel uses.

### One-time setup

1. Push this repository to GitHub.
2. Create the API project without deploying it. Stage once and link the folder:

   ```bash
   cd server
   python scripts/stage_api_deploy.py ../../altrix-api-stage
   npx vercel@63.1.2 link --cwd ../../altrix-api-stage     # log in, create a new project named altrix-api
   ```

   `altrix-api-stage/.vercel/project.json` (next to the repository folder) now holds `orgId` and `projectId`. Do **not** connect this project
   to the Git repository: a Git deployment would have no data. In the project's settings, add the environment
   variable `ALTRIX_CORS_ORIGINS=https://<your-web-project>.vercel.app`.
3. Create a token at <https://vercel.com/account/tokens>. In GitHub, go to *Settings → Secrets and variables →
   Actions* and add `VERCEL_TOKEN`, `VERCEL_ORG_ID` (`orgId`) and `VERCEL_PROJECT_ID` (`projectId`). Until these
   exist, the workflow skips the deploy.
4. Run *Deploy API* from the Actions tab. Check `https://<api-project>.vercel.app/health`: `stored_symbols`
   should be 100 and `downloads_enabled` false.
5. In Vercel, import the GitHub repository as a second project: Root Directory `client`, environment variable
   `NEXT_PUBLIC_API_BASE_URL=https://<api-project>.vercel.app`. It is read at build time, so redeploy after
   changing it.

The API runs in Mumbai (`bom1`, set in `server/deploy/vercel-api/vercel.json`).

### Limitations

- The first request to a cold API instance scans every stock: about 5-15 s. A first 10-year backtest loads all
  the data: about 10 s. Later requests reuse the in-memory cache.
- Data updates once per weekday, after GitHub starts the scheduled run (it can start late).
  *Refresh → Rescan stored data* still works but only re-reads the deployed data.
- Only the origins in `ALTRIX_CORS_ORIGINS` can call the API, so Vercel preview deployments of the frontend
  can't call it unless you add their URLs.
- The API has no authentication. It is read-only, but anyone with the URL can run backtests.

## Code layout

```
server/
  src/data/
    universe.py     UniverseProvider interface + Nifty100Universe (NSE CSV, cached fallback)
    provider.py     MarketDataProvider interface + YahooFinanceProvider, normalized SCHEMA
    downloader.py   ParquetStore, incremental update_symbol / download_all, validate_all
    validator.py    validate(), build_trading_calendar(), large_price_drops(), ValidationReport
    deliverables.py optional NSE sec_bhavdata_full parser/downloader, DeliverableStore, delivery spikes
    cleaner.py      clean(), load_clean(): tidy frames for downstream use, gaps reported
    target.py       add_medium_term_target(): future_max_return_60d + binary target (label only, never a feature)
  src/strategy/
    baseline.py     generate_baseline_signals(): SMA20/SMA50 crossover BUY/SELL signals (signal on day t,
                    executed at the stock's next trading day's open by the backtester)
    smart_money.py  add_smart_money_footprint(), generate_smart_money_signals(): volume spike, CLV,
                    pocket pivots, accumulation, 10-day memory, smart-money filtered SMA 20/50
  src/backtest/
    models.py       BacktestConfig, Position, Execution, Trade, BacktestResult
    engine.py       run_backtest(strategy=...) / run_backtest_on_signals() (any signals); ROC20 BUY ranking,
                    minimum position size
    metrics.py      compute_metrics() (incl. profit factor, expectancy), max_drawdown(), drawdown_series(), cagr()
  src/scanner/
    opportunity_scanner.py  run_universe_scan(), scan_current_opportunities(): latest-day BUY/SELL/HOLD
    smart_money_scan.py     scan_smart_money(): latest-day footprint ranked by volume spike
  app/
    streamlit_app.py   entry point: page navigation (Opportunity Scanner, Backtest)
    views/scanner.py   Opportunity Scanner page (layout, widgets, caching; no logic)
    views/backtest.py  Backtest page (layout, widgets, session state; no logic)
    scanner_ui.py      universe loading, refresh, tables and chart for the scanner page
    dashboard.py       turns a BacktestResult into tables, metric cards and Plotly figures
  api/
    main.py            FastAPI app and endpoints (uvicorn api.main:app)
    service.py         cached access to the scanner, strategy output, backtester and downloader
    schemas.py         response models (OpenAPI docs at /docs)
  scripts/
    download_data.py   download / update data
    run_backtest.py    backtest the baseline strategy, save results to data/results/
    download_deliverables.py  optional NSE deliverable volume (sec_bhavdata_full)
    stage_api_deploy.py  assemble the API + data folder that is deployed to Vercel
  deploy/vercel-api/   Vercel entrypoint (index.py), pinned runtime requirements, Python version, vercel.json
  tests/               offline pytest suite (fake providers, synthetic data, headless AppTest)
  data/                raw/ constituent snapshot, processed/ Parquet files, deliverables/ (downloaded, not committed)
client/                Next.js frontend (App Router, Tailwind, shadcn/ui, lightweight-charts, Recharts)
.github/workflows/
  deploy-api.yml       weekday data update + API deploy to Vercel
```

To add a new data vendor, subclass `MarketDataProvider` and implement
`get_daily_history(symbol, start, end)` so that it returns a frame in `SCHEMA`.

## Not implemented yet

- Feature engineering and machine-learning models
- Realistic Indian fee model (STT, GST, stamp duty), slippage, advanced position sizing/risk management
- Broker APIs, order execution, live trading
- Historical (point-in-time) index membership
- Dividend-adjusted total-return prices
- Intraday data
