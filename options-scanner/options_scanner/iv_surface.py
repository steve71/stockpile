"""Fit an IV surface and score each option's distance from it.

This orchestrates a three-stage, pluggable pipeline:

1. Filter   (iv_filters)    — which options feed the fit.
2. Algorithm (iv_algorithms) — produces iv_fitted for every row.
3. Score    (iv_scores)     — produces signal_score, the ranking key.

The defaults (global-polynomial fit + raw IV+pp score + OTM/spread/
delta filters) reproduce the original behavior exactly, so nothing
changes until the caller selects another algorithm or score.

Surface model (default algorithm):
IV ≈ a + b·m + c·m² + d·√T + e·m·√T + f·m²·√T
where m = log(K/S) and T = DTE/365 (the f·m²·√T term lets curvature
vary with maturity). Options sitting above the surface
are IV-rich — candidates to sell; below, IV-cheap.

Output is a screening heuristic, not a mispricing claim.
"""

import numpy as np
import pandas as pd

from options_scanner import iv_algorithms, iv_scores
from options_scanner.iv_filters import (
    DEFAULT_CONFIG, SurfaceFilterConfig, apply as _apply_filters,
)


def compute_iv_excess(
    df: pd.DataFrame,
    surface_filters: SurfaceFilterConfig | None = None,
    algo_config: iv_algorithms.AlgorithmConfig | None = None,
    score_config: iv_scores.ScoreConfig | None = None,
    ctx: iv_scores.ScoreContext | None = None,
) -> pd.DataFrame:
    """Add iv_fitted, iv_excess, signal_score and signal_kind columns.

    surface_filters / algo_config / score_config select the three
    pipeline stages; each defaults to the module's DEFAULT_CONFIG when
    None, reproducing the original surface and ranking. ctx carries
    ticker-level context (realized vol, history) some scores need.

    All rows receive iv_fitted / iv_excess / signal_score; only the
    surface fit itself is filtered.
    """
    if surface_filters is None:
        surface_filters = DEFAULT_CONFIG
    if algo_config is None:
        algo_config = iv_algorithms.DEFAULT_CONFIG
    if score_config is None:
        score_config = iv_scores.DEFAULT_CONFIG

    df = df.copy().reset_index(drop=True)

    # Stage 1 — which rows anchor the fit.
    valid = df[(df["iv"] > 0.02) & (df["dte"] > 0)]
    fit_subset = _apply_filters(valid, surface_filters)
    fit_mask = df.index.isin(fit_subset.index)
    # Expose fit membership so the chart/diagnostics can show which
    # contracts actually anchored the regression.
    df["in_fit"] = fit_mask

    # Stage 2 — fit the surface (None → flat fallback). `methods` labels
    # how each row was fit so the chart can warn on fallback expirations.
    iv_fitted, methods = iv_algorithms.fit(
        df, fit_mask, algo_config, return_methods=True)
    if iv_fitted is None:
        df["iv_fitted"] = df["iv"]
        df["iv_excess"] = 0.0
        df["fit_method"] = "none"
    else:
        df["iv_fitted"] = iv_fitted
        df["iv_excess"] = df["iv"] - df["iv_fitted"]
        df["fit_method"] = methods if methods is not None else "global"

    # Stage 3 — score each row relative to the surface.
    signal, kind = iv_scores.score(df, fit_mask, ctx, score_config)
    df["signal_score"] = signal
    df["signal_kind"] = kind
    return df
