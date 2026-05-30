"""Surface-fit algorithm registry for iv_surface.compute_iv_excess.

An algorithm turns the chain plus a boolean fit-mask (which rows the
filter pipeline kept) into an `iv_fitted` value for *every* row. The
orchestrator then derives `iv_excess = iv - iv_fitted`.

AlgorithmConfig is a single (name, frozenset-of-kwargs) pair. The
frozenset makes it hashable for Streamlit's st.cache_data, mirroring
iv_filters.SurfaceFilterConfig.

Each algorithm:  fn(df, fit_mask, **kwargs) -> (iv_fitted, methods)
  - iv_fitted: array aligned to df row order, or None for "insufficient
    data" → the orchestrator falls back to a flat surface (iv_fitted =
    iv, iv_excess = 0).
  - methods: per-row array of fit-method labels ("global", "per_expiry",
    "fallback", ...) the chart uses to warn when an expiration was fit
    by fallback rather than its own data. None when iv_fitted is None.

Adding a new algorithm
----------------------
1. Write fn(df, fit_mask, **kwargs) -> (iv_fitted, methods)
2. Add an entry to REGISTRY with fn, defaults, and label
3. It appears automatically in the UI Algorithm dropdown
"""

from __future__ import annotations

import numpy as np
import pandas as pd

# Hashable single-algorithm config: (name, frozenset({(kwarg, val), ...}))
AlgorithmConfig = tuple[str, frozenset]

# global_poly fits a 6-term surface:
#   IV ≈ a + b·m + c·m² + d·√T + e·m·√T + f·m²·√T
# The f·m²·√T term lets the smile's CURVATURE vary with maturity (sharp
# near-dated smiles, flat long-dated) instead of forcing one shared
# curvature c across all expirations — a single c is a maturity-weighted
# average that sits below the steeper near-dated wings. Require ≥2
# residual degrees of freedom — params + 2 = 8 — so the fit is a genuine
# regression, never an exact interpolant; below 8 we'd rather fall back
# to the honest flat surface than report a fake-perfect fit.
_GLOBAL_PARAMS = 6
_MIN_GLOBAL_ROWS = _GLOBAL_PARAMS + 2   # = 8
# per_expiration picks the highest polynomial degree that still leaves
# ≥2 residual degrees of freedom, so a slice is FIT, never interpolated
# (a degree-d polynomial passes exactly through d+1 points). Below the
# linear threshold a slice gets a flat reference (its mean IV).
_MIN_QUAD_ROWS = 5     # quadratic (3 params) → need ≥5 points
_MIN_LINEAR_ROWS = 4   # linear (2 params)   → need ≥4 points


# ── Weighting ──────────────────────────────────────────────────────────────────

def _row_weights(rows: pd.DataFrame, weights: str) -> np.ndarray | None:
    """Per-row regression weights for WLS, or None for ordinary least squares.

    weights:
      "none"       — equal weight (OLS)
      "oi"         — weight by open interest (liquid quotes anchor the fit)
      "inv_spread" — weight by 1 / (ask - bid) (tight quotes are more reliable)
    """
    if weights == "oi" and "open_interest" in rows.columns:
        w = rows["open_interest"].to_numpy(dtype=float)
        w = np.where(np.isfinite(w) & (w > 0), w, 0.0)
        return w if w.sum() > 0 else None
    if weights == "inv_spread" and {"ask", "bid"} <= set(rows.columns):
        spread = (rows["ask"] - rows["bid"]).to_numpy(dtype=float)
        spread = np.where(np.isfinite(spread), spread, np.inf)
        return 1.0 / np.maximum(spread, 0.01)
    return None


def _wls(X: np.ndarray, y: np.ndarray, w: np.ndarray | None) -> np.ndarray:
    """Least-squares coefficients, weighted by w via √w pre-multiplication."""
    if w is not None:
        sw = np.sqrt(w)[:, None]
        X = X * sw
        y = y * sw[:, 0]
    coeffs, _, _, _ = np.linalg.lstsq(X, y, rcond=None)
    return coeffs


# ── Algorithms ──────────────────────────────────────────────────────────────────

def _global_poly(df: pd.DataFrame, fit_mask: np.ndarray, weights: str = "none"):
    """One surface across the whole chain:
    IV ≈ a + b·m + c·m² + d·√T + e·m·√T + f·m²·√T.

    The f·m²·√T term lets curvature vary with maturity; at a single
    expiration the three √T columns collapse onto their non-√T twins
    (1, m, m²), so the slice is still fit by a plain quadratic in m
    (lstsq handles the rank deficiency, returning the same fitted values).

    Returns (iv_fitted, methods) — methods is a per-row array of fit-method
    labels — or (None, None) when there are too few points to fit.
    """
    fit = df[fit_mask]
    if len(fit) < _MIN_GLOBAL_ROWS:
        return None, None

    def design(frame: pd.DataFrame) -> np.ndarray:
        m = frame["log_moneyness"].to_numpy(dtype=float)
        sqrt_T = np.sqrt(frame["dte"].to_numpy(dtype=float) / 365.0)
        return np.column_stack(
            [np.ones_like(m), m, m ** 2, sqrt_T, m * sqrt_T, m ** 2 * sqrt_T])

    try:
        coeffs = _wls(design(fit), fit["iv"].to_numpy(dtype=float),
                      _row_weights(fit, weights))
    except np.linalg.LinAlgError:
        return None, None
    iv_fitted = design(df) @ coeffs
    return iv_fitted, np.full(len(df), "global", dtype=object)


def _poly_design(frame: pd.DataFrame, degree: int) -> np.ndarray:
    """Vandermonde-style design matrix in log-moneyness up to `degree`."""
    m = frame["log_moneyness"].to_numpy(dtype=float)
    return np.column_stack([m ** p for p in range(degree + 1)])


def _per_expiration(df: pd.DataFrame, fit_mask: np.ndarray, weights: str = "none"):
    """Fit a low-order IV smile independently per expiration slice.

    Eliminates term-structure noise: each expiration's excess is
    measured against its own slice. The degree adapts to the number of
    fit rows so the slice is genuinely fit, not interpolated —
    quadratic with ≥5 points, linear with ≥4. This keeps residuals
    non-zero (so the z-score has a meaningful scale) and the chart line
    a fit, not a dot-connector.

    Slices that can't be fit locally — too few fit rows, or *zero*
    because every contract was filtered out (e.g. an earnings-spanning
    expiration under exclude_earnings) — fall back to the global
    surface fitted on the available rows and evaluated at that slice.
    That borrows cross-expiration shape rather than leaving iv_fitted =
    iv, so an earnings expiration is correctly measured against the
    non-event surface (its premium shows up as positive excess).

    Returns (iv_fitted, methods). methods labels each row "per_expiry"
    (genuine local fit) or "fallback" (borrowed the global surface /
    slice mean — the chart warns on these, since the line won't reflect
    that expiry's own smile). Returns (None, None) if nothing was fit.
    """
    group_key = "expiration" if "expiration" in df.columns else "dte"
    iv_fitted = df["iv"].to_numpy(dtype=float).copy()
    methods = np.full(len(df), "none", dtype=object)
    fitted_any = False
    global_arr = None
    global_done = False

    for _, idx in df.groupby(group_key).groups.items():
        positions = df.index.get_indexer(idx)
        sel = df.loc[idx]
        fit = sel[fit_mask[positions]]
        n = len(fit)

        degree = (2 if n >= _MIN_QUAD_ROWS
                  else 1 if n >= _MIN_LINEAR_ROWS
                  else None)

        if degree is not None:
            try:
                coeffs = _wls(_poly_design(fit, degree),
                              fit["iv"].to_numpy(dtype=float),
                              _row_weights(fit, weights))
                iv_fitted[positions] = _poly_design(sel, degree) @ coeffs
                methods[positions] = "per_expiry"
                fitted_any = True
                continue
            except np.linalg.LinAlgError:
                pass  # fall through to the global/mean fallback

        # Too few (or zero) fit rows for a local curve — borrow the
        # global surface; if that's unavailable, use the slice mean.
        if not global_done:
            global_arr, _ = _global_poly(df, fit_mask, weights)
            global_done = True
        if global_arr is not None:
            iv_fitted[positions] = global_arr[positions]
            methods[positions] = "fallback"
            fitted_any = True
        elif n > 0:
            iv_fitted[positions] = float(fit["iv"].mean())
            methods[positions] = "fallback"
            fitted_any = True

    return (iv_fitted, methods) if fitted_any else (None, None)


def _svi(df: pd.DataFrame, fit_mask: np.ndarray, **kwargs) -> np.ndarray | None:
    """Stochastic-Volatility-Inspired surface — extension point, not yet built.

    SVI calibrates a 5-parameter arbitrage-free slice per expiration.
    Implementing it means nonlinear calibration (parameter bounds,
    initial guesses, failure handling); registered here as the seam so
    the UI can advertise it. Replace this body to implement.
    """
    raise NotImplementedError("SVI surface is not implemented yet")


# ── Registry ──────────────────────────────────────────────────────────────────

REGISTRY: dict[str, dict] = {
    "global_poly": {
        "fn":       _global_poly,
        "defaults": {"weights": "none"},
        "label":    "Global polynomial (current)",
        "enabled":  True,
    },
    "per_expiration": {
        "fn":       _per_expiration,
        "defaults": {"weights": "none"},
        "label":    "Per-expiration polynomial",
        "enabled":  True,
    },
    "svi": {
        "fn":       _svi,
        "defaults": {},
        "label":    "SVI (coming soon)",
        "enabled":  False,
    },
}

# Default: the current global polynomial, unweighted.
DEFAULT_CONFIG: AlgorithmConfig = ("global_poly", frozenset())


# ── Dispatch ────────────────────────────────────────────────────────────────────

def fit(df: pd.DataFrame, fit_mask: np.ndarray, config: AlgorithmConfig,
        return_methods: bool = False):
    """Run the configured algorithm.

    Returns iv_fitted (len df) or None. With return_methods=True, returns
    (iv_fitted, methods) where methods is the per-row fit-method labels
    (or None when iv_fitted is None).
    """
    name, kwargs_fs = config
    entry = REGISTRY.get(name, REGISTRY["global_poly"])
    kwargs = {**entry["defaults"], **dict(kwargs_fs)}
    iv_fitted, methods = entry["fn"](df, fit_mask, **kwargs)
    return (iv_fitted, methods) if return_methods else iv_fitted
