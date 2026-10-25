"""Altrix: local research app (Streamlit).

    streamlit run app/streamlit_app.py

Two pages:
  - Opportunity Scanner (default): NIFTY 100 stocks with a 20/50 EMA crossover
    signal on the latest trading day          -> app/views/scanner.py
  - Backtest: historical simulation of the same strategy -> app/views/backtest.py

Both are display layers over src/ (data, strategy, scanner, backtest).
"""

from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

st.set_page_config(page_title="Altrix", layout="wide")

VIEWS = Path(__file__).resolve().parent / "views"
page = st.navigation([
    st.Page(VIEWS / "scanner.py", title="Opportunity Scanner", default=True),
    st.Page(VIEWS / "backtest.py", title="Backtest"),
])
page.run()
