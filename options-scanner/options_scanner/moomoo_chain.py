"""Fetch option chain from Moomoo OpenD gateway and return normalized DataFrame.

Returns the same 17-column shape as chain.py:fetch_chain() so all
downstream code (iv_surface, earnings, display, report) is unchanged.
Uses Moomoo's native Greeks instead of Black-Scholes estimates.

Two-step Moomoo workflow
------------------------
1. ``get_option_expiration_date`` → list of expiry dates filtered by DTE.
2. ``get_option_chain``           → option codes + basic metadata per expiry
                                   (strike, type — no market data).
3. ``get_market_snapshot``        → bid/ask/last/IV/Greeks for each code
                                   (columns prefixed ``option_``).

``get_option_chain`` alone returns no market data; the snapshot is
required to populate bid/ask/IV/Greeks.

Prerequisites
-------------
- Moomoo desktop app **or** the standalone OpenD daemon must be running
  on the local machine before any scan is triggered.
- Default connection: host='127.0.0.1', port=11111.
- The Moomoo account must have a US Level 2 market data subscription
  for real-time quotes and options Greeks.

Install the SDK
---------------
    uv sync   (moomoo-api is listed in pyproject.toml dependencies)

OpenD download: https://www.moomoo.com/download/openD
"""

from __future__ import annotations

import logging
from datetime import date, datetime

import pandas as pd

from options_scanner.chain_common import build_option_row, safe_float, safe_int

log = logging.getLogger(__name__)

# Moomoo snapshot batch limit (SDK accepts up to ~400; 200 is safe)
_SNAPSHOT_BATCH = 200


def fetch_chain_moomoo(
    ticker: str,
    opt_type: str = "both",
    min_dte: int = 30,
    max_dte: int | None = 90,
    moomoo_config: dict | None = None,
) -> pd.DataFrame:
    """Fetch Moomoo option chain and return normalized DataFrame.

    Args:
        ticker:        Underlying ticker symbol (e.g. "AAPL").
        opt_type:      "both", "calls", or "puts".
        min_dte:       Minimum days-to-expiration (inclusive).
        max_dte:       Maximum DTE (inclusive); None = no limit.
        moomoo_config: Dict with optional keys ``host`` and ``port``.
                       Defaults to host='127.0.0.1', port=11111.

    Returns:
        DataFrame with the same 17-column schema as ``_fetch_chain_yahoo``.
        Empty DataFrame if no matching options are found.

    Raises:
        ValueError: If spot price, expirations, or option codes cannot be
                    fetched (surfaced as st.error in the UI via fetch.py).
    """
    import moomoo as ft  # noqa: PLC0415 — lazy import keeps cold-start fast

    cfg = moomoo_config or {}
    host = cfg.get("host", "127.0.0.1")
    port = int(cfg.get("port", 11111))

    # Moomoo uses "US.TICKER" format for US-listed securities
    code = f"US.{ticker.strip().upper()}"

    ctx = ft.OpenQuoteContext(host=host, port=port)
    try:
        return _fetch(ctx, ft, code, ticker, opt_type, min_dte, max_dte)
    finally:
        ctx.close()


def _fetch(ctx, ft, code: str, ticker: str,
           opt_type: str, min_dte: int, max_dte: int | None) -> pd.DataFrame:
    """Inner fetch — called inside the open context so ctx.close() is guaranteed."""

    # ── 1. Spot price (underlying) ────────────────────────────────────────
    ret, snap = ctx.get_market_snapshot([code])
    if ret != ft.RET_OK or snap.empty:
        raise ValueError(
            f"Could not fetch live price for {ticker} from Moomoo OpenD "
            f"({code}): {snap if isinstance(snap, str) else 'empty response'}. "
            "Ensure OpenD is running and the ticker is valid."
        )
    spot = float(snap["last_price"].iloc[0])
    if not spot:
        raise ValueError(
            f"Moomoo returned a zero price for {ticker}. "
            "Ensure markets are open or the ticker symbol is correct."
        )

    # ── 2. Expiration dates ───────────────────────────────────────────────
    ret, exp_data = ctx.get_option_expiration_date(code=code)
    if ret != ft.RET_OK:
        raise ValueError(
            f"Could not fetch option expirations for {ticker}: {exp_data}"
        )

    today = date.today()
    expirations: list[tuple[str, int]] = []
    for exp_raw in exp_data["strike_time"].tolist():
        # Moomoo timestamps like "2026-05-23 00:00:00"; take date part
        exp_str = str(exp_raw)[:10]
        try:
            exp_date = datetime.strptime(exp_str, "%Y-%m-%d").date()
        except ValueError:
            log.warning("Unrecognised expiration format: %r — skipping", exp_raw)
            continue
        dte = (exp_date - today).days
        if dte >= min_dte and (max_dte is None or dte <= max_dte):
            expirations.append((exp_str, dte))

    if not expirations:
        raise ValueError(
            f"No option expirations found for {ticker} with "
            f"DTE {min_dte}–{max_dte or '∞'}. "
            "Check that the ticker has listed options and OpenD has "
            "US market data access."
        )
    log.info("  %d expirations with DTE %s–%s",
             len(expirations), min_dte, max_dte or "∞")

    # ── 3. Option metadata (codes + strike + type) per expiry ─────────────
    # get_option_chain returns metadata only (no bid/ask/IV/Greeks).
    # We collect the option *codes* here, then batch-fetch market data.
    opt_meta: list[dict] = []
    for exp_str, dte in expirations:
        ret, chain = ctx.get_option_chain(
            code=code,
            start=exp_str,
            end=exp_str,
            option_type=ft.OptionType.ALL,
        )
        if ret != ft.RET_OK or chain.empty:
            log.warning("get_option_chain failed for %s %s: %s",
                        ticker, exp_str, chain if isinstance(chain, str) else "empty")
            continue

        for _, row in chain.iterrows():
            # option_type values from Moomoo: "CALL" or "PUT"
            side_raw = str(row.get("option_type", "")).upper()
            if side_raw == "CALL":
                side = "call"
            elif side_raw == "PUT":
                side = "put"
            else:
                continue
            if opt_type == "calls" and side != "call":
                continue
            if opt_type == "puts" and side != "put":
                continue

            opt_code = str(row.get("code", ""))
            K = safe_float(row.get("strike_price"))
            if K <= 0 or not opt_code:
                continue

            opt_meta.append({
                "code":    opt_code,
                "side":    side,
                "strike":  K,
                "exp_str": exp_str,
                "dte":     dte,
            })

    if not opt_meta:
        raise ValueError(
            f"No option contracts found for {ticker} in the DTE "
            f"{min_dte}–{max_dte or '∞'} range. The chain may be unavailable "
            "or require a different market data subscription."
        )
    log.info("  %d option contracts collected", len(opt_meta))

    # ── 4. Market data via get_market_snapshot (bid/ask/IV/Greeks) ─────────
    # Batch in groups of _SNAPSHOT_BATCH to stay inside Moomoo's per-call limit.
    all_codes = [m["code"] for m in opt_meta]
    snap_lookup: dict[str, object] = {}
    for i in range(0, len(all_codes), _SNAPSHOT_BATCH):
        batch = all_codes[i : i + _SNAPSHOT_BATCH]
        ret, snap_df = ctx.get_market_snapshot(batch)
        if ret != ft.RET_OK or snap_df.empty:
            log.warning("Snapshot batch %d–%d failed: %s",
                        i, i + len(batch), snap_df if isinstance(snap_df, str) else "empty")
            continue
        for _, srow in snap_df.iterrows():
            snap_lookup[str(srow["code"])] = srow
    log.info("  %d snapshot records fetched", len(snap_lookup))

    # ── 5. Build normalized rows ──────────────────────────────────────────
    # Moomoo option snapshot column reference:
    #   bid_price / ask_price / last_price / volume
    #   option_open_interest
    #   option_implied_volatility  — stored as percentage (28.45 = 28.45 %)
    #   option_delta / option_gamma / option_vega / option_theta
    rows: list[dict] = []
    for meta in opt_meta:
        srow = snap_lookup.get(meta["code"])
        if srow is None:
            continue

        bid   = safe_float(srow.get("bid_price"))
        ask   = safe_float(srow.get("ask_price"))
        last  = safe_float(srow.get("last_price"))
        vol   = safe_int(srow.get("volume"))
        oi    = safe_int(srow.get("option_open_interest"))
        delta = safe_float(srow.get("option_delta"))
        gamma = safe_float(srow.get("option_gamma"))
        # Theta and vega come from Moomoo natively — no BS needed
        theta = safe_float(srow.get("option_theta"))
        vega  = safe_float(srow.get("option_vega"))

        # IV: Moomoo returns percentage (e.g. 28.45); convert to ratio (0.2845)
        iv_pct = safe_float(srow.get("option_implied_volatility"))
        iv = iv_pct / 100.0

        built = build_option_row(
            side=meta["side"],
            strike=meta["strike"],
            expiration=meta["exp_str"],
            dte=meta["dte"],
            spot=spot,
            bid=bid,
            ask=ask,
            mid=0.0,
            last=last,
            iv=iv,
            delta=delta,
            gamma=gamma,
            theta=theta,
            vega=vega,
            open_interest=oi,
            volume=vol,
        )
        if built is not None:
            rows.append(built)

    return pd.DataFrame(rows) if rows else pd.DataFrame()
