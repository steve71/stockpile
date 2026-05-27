"""Tests for the SQLite scan-history store behind the percentile score.

Uses a throwaway DB via the OSC_IV_HISTORY_DB env var so the real
cache is never touched.
"""

from datetime import date, timedelta

import numpy as np
import pandas as pd
import pytest

from options_scanner import iv_history


@pytest.fixture(autouse=True)
def _temp_db(tmp_path, monkeypatch):
    monkeypatch.setenv("OSC_IV_HISTORY_DB", str(tmp_path / "h.db"))


def _snapshot(n: int, base: float = 0.0) -> pd.DataFrame:
    return pd.DataFrame({
        "type": ["call"] * n,
        "strike": [100.0 + i for i in range(n)],
        "expiration": ["2026-06-19"] * n,
        "dte": [30] * n,
        "iv_excess": [base + 0.001 * i for i in range(n)],
    })


def test_record_is_idempotent_per_day():
    df = _snapshot(10)
    iv_history.record_scan("AMD", df, scan_day=date(2026, 5, 26))
    iv_history.record_scan("AMD", df, scan_day=date(2026, 5, 26))
    pool = iv_history._pool("AMD", window_days=365)
    assert pool.size == 10  # not 20 — same-day rerun replaced, not appended


def test_percentile_cold_start_returns_nan():
    iv_history.record_scan("AMD", _snapshot(5), scan_day=date.today())
    pct = iv_history.percentile_for("AMD", pd.Series([0.0, 0.1]))
    assert np.isnan(pct).all()


def test_percentile_ranks_against_pool():
    # Seed ≥30 observations across several recent days.
    today = date.today()
    for d in range(5):
        iv_history.record_scan(
            "AMD", _snapshot(10, base=0.0),
            scan_day=today - timedelta(days=d + 1),
        )
    pool = iv_history._pool("AMD", window_days=30)
    assert pool.size >= 30

    lo, hi = float(pool.min()), float(pool.max())
    pct = iv_history.percentile_for(
        "AMD", pd.Series([lo - 1.0, hi + 1.0]), window_days=30)
    assert pct[0] <= 5.0       # below the whole pool
    assert pct[1] >= 99.0      # above the whole pool


def test_record_noop_when_columns_missing():
    # Missing iv_excess → silently skipped, no crash, nothing stored.
    iv_history.record_scan("AMD", pd.DataFrame({"type": ["call"]}),
                           scan_day=date.today())
    assert iv_history._pool("AMD", window_days=365).size == 0


def test_percentile_for_empty_ticker_is_nan():
    pct = iv_history.percentile_for("NOPE", pd.Series([0.1, 0.2, 0.3]))
    assert np.isnan(pct).all()
