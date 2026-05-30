"""Tests for the surface-fit filter registry.

Focused on the exclude_earnings filter (the LGbengs critique #2
addition); the older filters are exercised indirectly through the
surface-fit and chain tests.
"""

import pandas as pd

from options_scanner import iv_filters


def _df():
    return pd.DataFrame({
        "type": ["call", "call", "put", "put"],
        "strike": [105.0, 110.0, 95.0, 90.0],
        "spot": [100.0] * 4,
        "bid": [1.0, 1.0, 1.0, 1.0],
        "ask": [1.05, 1.05, 1.05, 1.05],
        "delta": [0.4, 0.3, -0.4, -0.3],
        "open_interest": [500, 500, 500, 500],
        "iv": [0.30, 0.30, 0.30, 0.30],
        "earnings_count": [0, 2, 0, 1],
    })


def test_exclude_earnings_drops_earnings_spanning_rows():
    out = iv_filters.apply(_df(), (("exclude_earnings", frozenset()),))
    assert list(out["earnings_count"]) == [0, 0]
    assert len(out) == 2


def test_exclude_earnings_noop_without_column():
    df = _df().drop(columns=["earnings_count"])
    out = iv_filters.apply(df, (("exclude_earnings", frozenset()),))
    assert len(out) == len(df)


def test_exclude_earnings_registered_and_labeled():
    assert "exclude_earnings" in iv_filters.REGISTRY
    assert iv_filters.REGISTRY["exclude_earnings"]["label"]


def test_empty_config_is_identity():
    df = _df()
    assert len(iv_filters.apply(df, ())) == len(df)


# ── funnel ────────────────────────────────────────────────────────────────────

def test_funnel_final_remaining_matches_apply():
    df = _df()
    config = (("otm_only", frozenset()),
              ("delta_range", frozenset({("lo", 0.0), ("hi", 0.35)})))
    stages = iv_filters.funnel(df, config)
    assert stages[-1][1] == len(iv_filters.apply(df, config))


def test_funnel_labels_from_registry():
    stages = iv_filters.funnel(_df(), (("otm_only", frozenset()),))
    assert stages[0][0] == iv_filters.REGISTRY["otm_only"]["label"]


def test_funnel_remaining_and_dropped_reconcile():
    df = _df()
    config = (("otm_only", frozenset()),
              ("spread_pct", frozenset({("max_pct", 0.50)})),
              ("delta_range", frozenset({("lo", 0.0), ("hi", 0.35)})))
    prev = len(df)
    for _label, remaining, dropped in iv_filters.funnel(df, config):
        assert remaining + dropped == prev
        prev = remaining


def test_funnel_skips_unknown_filter():
    stages = iv_filters.funnel(
        _df(), (("nope", frozenset()), ("otm_only", frozenset())))
    assert len(stages) == 1
    assert stages[0][0] == iv_filters.REGISTRY["otm_only"]["label"]


def test_funnel_empty_config_has_no_stages():
    assert iv_filters.funnel(_df(), ()) == []
