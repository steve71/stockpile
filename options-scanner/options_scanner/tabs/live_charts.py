"""Live Charts tab: embed the standalone trading dashboard.

The trading dashboard is a separate Flask + JS app (live multi-pane
candlestick charts with Yahoo Finance / Schwab / Hyperliquid sources). When
the combined launcher (`uv run run.py`) is used, that Flask app runs on
http://localhost:5000 and is embedded here via an iframe — it also stays
reachable directly at localhost:5000 (same server, two views).

If the dashboard isn't running (e.g. the scanner was started on its own),
this tab shows how to start it rather than a broken iframe.
"""

from __future__ import annotations

import urllib.request

import streamlit as st
import streamlit.components.v1 as components

from options_scanner.ui_theme import section_header

DASHBOARD_URL = "http://localhost:5000"


@st.cache_data(ttl=5, show_spinner=False)
def _dashboard_up(url: str) -> bool:
    """Whether the trading dashboard is reachable. Cached briefly so the
    health check doesn't run a blocking request on every rerun."""
    try:
        with urllib.request.urlopen(f"{url}/api/health", timeout=0.8) as resp:
            return resp.status == 200
    except Exception:
        return False


def tab_live_charts() -> None:
    if not _dashboard_up(DASHBOARD_URL):
        st.info(
            "The live dashboard isn't running. Start everything together with "
            "`uv run run.py`, or run the dashboard on its own with "
            "`uv run trading-dashboard/app.py`, then reload this tab."
        )
        return

    components.iframe(DASHBOARD_URL, height=900, scrolling=True)

    # Title + context live below the chart so the dashboard is front-and-center.
    section_header(
        title="Live charts",
        subtitle="Multi-pane live candlesticks — Yahoo Finance, Schwab, and "
                 "Hyperliquid — served by the trading dashboard.",
    )
    st.caption(
        f"Embedded from {DASHBOARD_URL} — open it full-screen in a new tab: "
        f"[{DASHBOARD_URL} ↗]({DASHBOARD_URL})"
    )
