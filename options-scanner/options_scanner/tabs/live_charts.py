"""Live Charts tab: embed the standalone trading dashboard.

The trading dashboard is a separate Flask + JS app (live multi-pane
candlestick charts with Yahoo Finance / Schwab / Hyperliquid sources). When
the combined launcher (`uv run run.py`) is used, that Flask app runs on
port 5000 and is embedded here via an iframe — it also stays reachable
directly at that port (same server, two views).

An iframe `src` is resolved by the *viewer's* browser, not the Streamlit
server, so a hardcoded `localhost:5000` only works when the browser and the
server are the same machine (the local case). For remote / cloud use we derive
the host the browser actually reached the scanner on (from the request
`Host` / `X-Forwarded-Host` header) and point the dashboard iframe at that
same host on the dashboard port. This covers any setup where the dashboard
port is also reachable from the client (local, port-forwarded, a VPS with both
ports open). Set `OSC_DASHBOARD_URL` to override the whole URL — e.g. a
reverse-proxy path or a single-exposed-port deployment.

If the dashboard isn't running on the server (e.g. the scanner was started on
its own), this tab shows how to start it rather than a broken iframe.
"""

from __future__ import annotations

import os
import urllib.request

import streamlit as st
import streamlit.components.v1 as components

from options_scanner.ui_theme import section_header

def _dashboard_port() -> int:
    """Dashboard TCP port, overridable via OSC_DASHBOARD_PORT (default 5000)
    for hosts where 5000 is taken. The Flask app and the `uv run run.py`
    launcher read the same var, so all three stay in sync."""
    raw = os.environ.get("OSC_DASHBOARD_PORT", "").strip()
    try:
        port = int(raw)
    except ValueError:
        return 5000
    return port if 1 <= port <= 65535 else 5000


DASHBOARD_PORT = _dashboard_port()
# Server-side health-probe target: any dashboard launched alongside the scanner
# runs on this same machine's loopback. This is *not* what the iframe points at
# (the iframe is resolved by the client browser) — see _browser_dashboard_url.
LOCAL_HEALTH_URL = f"http://127.0.0.1:{DASHBOARD_PORT}"


def _override_url() -> str:
    """Explicit dashboard URL from the environment, or "" if unset."""
    return os.environ.get("OSC_DASHBOARD_URL", "").strip()


@st.cache_data(ttl=5, show_spinner=False)
def _dashboard_up(url: str) -> bool:
    """Whether the trading dashboard is reachable from the server. Cached
    briefly so the health check doesn't run a blocking request on every
    rerun."""
    try:
        with urllib.request.urlopen(f"{url}/api/health", timeout=0.8) as resp:
            return resp.status == 200
    except Exception:
        return False


def _browser_dashboard_url() -> str:
    """The dashboard URL as the *client browser* should reach it.

    An explicit ``OSC_DASHBOARD_URL`` wins. Otherwise derive the host from the
    request the browser made to the scanner (``X-Forwarded-Host`` from a proxy,
    else ``Host``) so the iframe follows whatever host the user reached the
    scanner on, and point it at the dashboard port. Falls back to ``localhost``
    when no header is available (the local single-machine case)."""
    override = _override_url()
    if override:
        return override.rstrip("/")

    host, proto = "localhost", "http"
    try:
        headers = st.context.headers or {}
        raw_host = headers.get("X-Forwarded-Host") or headers.get("Host") or ""
        hostname = raw_host.split(",")[0].split(":")[0].strip()
        if hostname:
            host = hostname
        fwd_proto = (headers.get("X-Forwarded-Proto") or "").split(",")[0].strip()
        if fwd_proto in ("http", "https"):
            proto = fwd_proto
    except Exception:
        pass
    return f"{proto}://{host}:{DASHBOARD_PORT}"


def tab_live_charts() -> None:
    # With no override we can only embed a dashboard running on this server, so
    # gate on a loopback health probe and show a start hint instead of a broken
    # iframe. With an override the target may live elsewhere (proxy / other
    # host) where the server can't probe it, so trust it and skip the probe.
    if not _override_url() and not _dashboard_up(LOCAL_HEALTH_URL):
        st.info(
            "The live dashboard isn't running. Start everything together with "
            "`uv run run.py`, or run the dashboard on its own with "
            "`uv run trading-dashboard/app.py`, then reload this tab."
        )
        return

    url = _browser_dashboard_url()
    components.iframe(url, height=900, scrolling=True)

    # Title + context live below the chart so the dashboard is front-and-center.
    section_header(
        title="Live charts",
        subtitle="Multi-pane live candlesticks — Yahoo Finance, Schwab, and "
                 "Hyperliquid — served by the trading dashboard.",
    )
    st.caption(
        f"Embedded from {url} — open it full-screen in a new tab: "
        f"[{url} ↗]({url})"
    )
