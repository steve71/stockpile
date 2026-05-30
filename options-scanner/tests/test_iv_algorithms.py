"""Tests for the pluggable surface-fit algorithm registry.

Covers:
  - global_poly recovers a global quadratic-in-moneyness surface
  - per_expiration fits each expiration slice independently (and beats
    the global fit when slices have genuinely different curves)
  - per_expiration falls back to the slice mean when a slice is too small
  - WLS weighting pulls the fit toward heavily-weighted points
  - the <5-row / insufficient-data fallback returns None
"""

import math

import numpy as np
import pandas as pd

from options_scanner import iv_algorithms


def _chain(spot, slices, strikes, iv_fn, **extra):
    """slices: list of (dte, expiration) pairs."""
    rows = []
    for dte, exp in slices:
        for K in strikes:
            row = {
                "strike": float(K), "dte": int(dte), "expiration": exp,
                "iv": float(iv_fn(K, dte)), "log_moneyness": math.log(K / spot),
            }
            row.update({k: (v(K, dte) if callable(v) else v)
                        for k, v in extra.items()})
            rows.append(row)
    return pd.DataFrame(rows)


def _all(df):
    return np.ones(len(df), dtype=bool)


def test_global_poly_recovers_quadratic_exactly():
    spot = 100.0
    df = _chain(spot, [(30, "A"), (60, "B"), (90, "C")],
                [80, 85, 90, 95, 100, 105, 110, 115, 120],
                lambda K, t: 0.25 + 0.30 * math.log(K / spot) ** 2)
    fitted = iv_algorithms.fit(df, _all(df), ("global_poly", frozenset()))
    assert np.abs(df["iv"].to_numpy() - fitted).max() < 1e-8


def test_global_poly_requires_residual_dof():
    """global_poly needs > params rows so the fit is a genuine regression,
    not an exact interpolant. The 6-term model has 6 params; with only 6
    rows there are 0 residual DOF, so it falls back rather than report a
    fake-perfect (residual ≡ 0) surface. With 8 rows (2 residual DOF) it
    fits."""
    spot = 100.0
    three = _chain(spot, [(30, "A")], [95, 100, 105], lambda K, t: 0.30)
    assert iv_algorithms.fit(three, _all(three),
                             ("global_poly", frozenset())) is None
    six = _chain(spot, [(30, "A")], [80, 90, 100, 110, 120, 130],
                 lambda K, t: 0.30)
    assert iv_algorithms.fit(six, _all(six),
                             ("global_poly", frozenset())) is None
    eight = _chain(spot, [(30, "A")],
                   [70, 80, 90, 100, 110, 120, 130, 140], lambda K, t: 0.30)
    fitted = iv_algorithms.fit(eight, _all(eight),
                               ("global_poly", frozenset()))
    assert fitted is not None and len(fitted) == len(eight)


def test_per_expiration_recovers_distinct_slice_curves():
    """Two expirations with different smiles — each slice fit exactly."""
    spot = 100.0
    def iv_fn(K, t):
        m = math.log(K / spot)
        return (0.20 + 0.50 * m ** 2) if t == 30 else (0.35 - 0.10 * m)
    df = _chain(spot, [(30, "A"), (60, "B")],
                [80, 85, 90, 95, 100, 105, 110, 115, 120], iv_fn)
    fitted = iv_algorithms.fit(df, _all(df), ("per_expiration", frozenset()))
    assert np.abs(df["iv"].to_numpy() - fitted).max() < 1e-8


def test_per_expiration_beats_global_on_divergent_slices():
    # global_poly's m²·√T term makes curvature affine in √T, so it can fit
    # any TWO slices' curvatures exactly. To show per-expiration still wins,
    # use THREE slices whose curvature is non-monotonic in √T (0.80 → 0.15
    # → 0.70) — no line in √T passes through all three, so the global
    # surface must compromise while per-expiration fits each slice's own.
    spot = 100.0
    curv = {30: 0.80, 60: 0.15, 90: 0.70}
    def iv_fn(K, t):
        m = math.log(K / spot)
        return 0.30 + curv[t] * m ** 2
    df = _chain(spot, [(30, "A"), (60, "B"), (90, "C")],
                [80, 85, 90, 95, 100, 105, 110, 115, 120], iv_fn)
    per = iv_algorithms.fit(df, _all(df), ("per_expiration", frozenset()))
    glob = iv_algorithms.fit(df, _all(df), ("global_poly", frozenset()))
    per_resid = np.abs(df["iv"].to_numpy() - per).max()
    glob_resid = np.abs(df["iv"].to_numpy() - glob).max()
    assert per_resid < glob_resid


def test_per_expiration_fully_excluded_slice_uses_global_not_iv():
    """Regression for the earnings-excluded bug: an expiration whose rows
    are all excluded from the fit must be measured against the global
    surface, not left at iv_fitted = iv (excess 0)."""
    spot = 100.0
    strikes = [80, 85, 90, 95, 100, 105, 110, 115, 120]
    # Slices A1/A2 (flat 0.30) are in the fit and pin the global surface
    # across two expirations. Slice B (rich 0.55) is fully excluded.
    dfa = _chain(spot, [(30, "A1"), (90, "A2")], strikes, lambda K, t: 0.30)
    dfb = _chain(spot, [(60, "B")], strikes, lambda K, t: 0.55)
    df = pd.concat([dfa, dfb], ignore_index=True)
    mask = df["expiration"].isin(["A1", "A2"]).to_numpy()  # B excluded
    fitted = iv_algorithms.fit(df, mask, ("per_expiration", frozenset()))
    b = (df["expiration"] == "B").to_numpy()
    # B is fit against the non-event surface (~0.30), NOT its own iv.
    assert not np.allclose(fitted[b], df.loc[b, "iv"].to_numpy())
    assert np.allclose(fitted[b], 0.30, atol=0.03)
    # so B's premium shows up as large positive excess
    assert (df.loc[b, "iv"].to_numpy() - fitted[b]).mean() > 0.05


def test_per_expiration_mean_fallback_when_global_unavailable():
    """When the whole chain is too small for a global fit, a thin slice
    falls back to its own mean (still non-zero residuals, no crash)."""
    spot = 100.0
    df = _chain(spot, [(30, "A")], [95, 100, 105], lambda K, t: 0.40)
    fitted = iv_algorithms.fit(df, _all(df), ("per_expiration", frozenset()))
    assert np.allclose(fitted, df["iv"].mean())


def test_oi_weighting_pulls_fit_toward_high_oi_point():
    """A high-IV spike with huge OI should bend the weighted fit toward
    it, shrinking its residual vs. the unweighted fit."""
    spot = 100.0
    rich_K = 110.0
    df = _chain(
        spot, [(30, "A")],
        [80, 85, 90, 95, 100, 105, 110, 115, 120],
        lambda K, t: 0.30 + (0.20 if K == rich_K else 0.0),
        open_interest=lambda K, t: 100000 if K == rich_K else 10,
    )
    base = iv_algorithms.fit(df, _all(df), ("global_poly", frozenset()))
    wtd = iv_algorithms.fit(
        df, _all(df), ("global_poly", frozenset({("weights", "oi")})))
    i = int(df.index[df["strike"] == rich_K][0])
    resid_base = abs(df["iv"].iloc[i] - base[i])
    resid_wtd = abs(df["iv"].iloc[i] - wtd[i])
    assert resid_wtd < resid_base


def test_per_expiration_does_not_interpolate_thin_slice():
    """Regression: slices with too few rows for a local curve must NOT be
    interpolated (the old 3-param quadratic through 3 points drove
    residuals to zero and flattened the z-score). They borrow the global
    fit, which keeps real scatter in the residuals."""
    spot = 100.0
    rng = np.random.default_rng(7)
    # 3 strikes × 3 expirations: every slice is thin → global fallback.
    df = _chain(spot, [(30, "A"), (60, "B"), (90, "C")], [90, 100, 110],
                lambda K, t: 0.30 + 0.40 * math.log(K / spot) ** 2)
    df["iv"] = df["iv"] + rng.normal(0, 0.015, len(df))
    fitted = iv_algorithms.fit(df, _all(df), ("per_expiration", frozenset()))
    resid = df["iv"].to_numpy() - fitted
    assert np.abs(resid).max() > 1e-4          # genuine residuals, not interpolated
    assert not np.allclose(fitted, df["iv"].to_numpy())


def test_per_expiration_uses_quadratic_with_enough_points():
    """With ≥5 fit rows the slice gets a genuine quadratic fit (residuals
    present, not interpolated)."""
    spot = 100.0
    rng = np.random.default_rng(1)
    df = _chain(spot, [(30, "A")], [80, 88, 96, 104, 112, 120],
                lambda K, t: 0.30 + 0.40 * math.log(K / spot) ** 2)
    df["iv"] = df["iv"] + rng.normal(0, 0.01, len(df))
    fitted = iv_algorithms.fit(df, _all(df), ("per_expiration", frozenset()))
    resid = df["iv"].to_numpy() - fitted
    assert 0 < np.abs(resid).max() < 0.05      # fit, with real residuals


def test_fit_returns_methods_when_requested():
    spot = 100.0
    df = _chain(spot, [(30, "A")],
                [80, 85, 90, 95, 100, 105, 110, 115, 120], lambda K, t: 0.30)
    fitted, methods = iv_algorithms.fit(
        df, _all(df), ("global_poly", frozenset()), return_methods=True)
    assert methods is not None and len(methods) == len(df)
    assert set(methods) == {"global"}


def test_per_expiration_methods_flag_local_vs_fallback():
    """The fit-method labels distinguish a genuine per-expiry fit from a
    fallback — the chart warns on the latter."""
    spot = 100.0
    strikes = [80, 85, 90, 95, 100, 105, 110, 115, 120]
    dfa = _chain(spot, [(30, "A1"), (90, "A2")], strikes, lambda K, t: 0.30)
    dfb = _chain(spot, [(60, "B")], strikes, lambda K, t: 0.55)
    df = pd.concat([dfa, dfb], ignore_index=True)
    mask = df["expiration"].isin(["A1", "A2"]).to_numpy()  # B excluded
    _, methods = iv_algorithms.fit(
        df, mask, ("per_expiration", frozenset()), return_methods=True)
    methods = np.asarray(methods)
    assert set(methods[(df["expiration"] == "A1").to_numpy()]) == {"per_expiry"}
    assert set(methods[(df["expiration"] == "B").to_numpy()]) == {"fallback"}


def test_inv_spread_weighting_runs():
    spot = 100.0
    df = _chain(
        spot, [(30, "A"), (60, "B")],
        [80, 90, 100, 110, 120], lambda K, t: 0.30,
        bid=1.00, ask=lambda K, t: 1.05 if K != 100 else 2.00,
    )
    fitted = iv_algorithms.fit(
        df, _all(df), ("global_poly", frozenset({("weights", "inv_spread")})))
    assert fitted is not None and np.isfinite(fitted).all()
