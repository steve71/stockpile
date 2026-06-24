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
# average that sits below the steeper near-dated wings. The term is
# only included when the fit subset spans ≥3 distinct expirations —
# below that it's knife-edged (two maturities can't pin curvature-vs-T)
# and the surface degrades to the 5-term model. Require ≥2 residual
# degrees of freedom — params + 2 — so the fit is a genuine regression,
# never an exact interpolant; below that we'd rather fall back to the
# honest flat surface than report a fake-perfect fit.
_GLOBAL_PARAMS = 6
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
      "vega"       — weight by vega (IV noise from price discreteness
                     scales as 1/vega, so high-vega quotes carry the
                     most reliable IV; naturally downweights far-OTM
                     wings)
    """
    if weights == "oi" and "open_interest" in rows.columns:
        w = rows["open_interest"].to_numpy(dtype=float)
        w = np.where(np.isfinite(w) & (w > 0), w, 0.0)
        return w if w.sum() > 0 else None
    if weights == "inv_spread" and {"ask", "bid"} <= set(rows.columns):
        spread = (rows["ask"] - rows["bid"]).to_numpy(dtype=float)
        spread = np.where(np.isfinite(spread), spread, np.inf)
        return 1.0 / np.maximum(spread, 0.01)
    if weights == "vega" and "vega" in rows.columns:
        w = rows["vega"].abs().to_numpy(dtype=float)
        w = np.where(np.isfinite(w) & (w > 0), w, 0.0)
        return w if w.sum() > 0 else None
    return None


def _wls(X: np.ndarray, y: np.ndarray, w: np.ndarray | None) -> np.ndarray:
    """Least-squares coefficients, weighted by w via √w pre-multiplication."""
    if w is not None:
        sw = np.sqrt(w)[:, None]
        X = X * sw
        y = y * sw[:, 0]
    coeffs, _, _, _ = np.linalg.lstsq(X, y, rcond=None)
    return coeffs


# IRLS tuning constants — the textbook values giving ~95% efficiency
# under normal errors. Huber downweights outliers; Tukey rejects them
# entirely beyond c, which is aggressive on thin chains.
_HUBER_K = 1.345
_TUKEY_C = 4.685
_IRLS_MAX_ITERS = 5


def _robust_wls(X: np.ndarray, y: np.ndarray, w: np.ndarray | None,
                robust: str = "none") -> np.ndarray:
    """`_wls` hardened against outliers via IRLS.

    Plain least squares lets the very outliers the scanner hunts for
    bend the surface toward themselves (a stale 80%-IV print shrinks
    its own measured excess). With robust="huber"/"tukey" the fit is
    re-solved a few times, each pass downweighting rows by their
    residual relative to a robust scale (MAD), so the surface settles
    on the *typical* IV and genuine outliers stand fully above it.
    Robustness weights multiply the base weights `w`, composing with
    oi / inv_spread / vega weighting. robust="none" is plain `_wls`.
    """
    coeffs = _wls(X, y, w)
    if robust not in ("huber", "tukey"):
        return coeffs
    for _ in range(_IRLS_MAX_ITERS):
        resid = y - X @ coeffs
        # MAD scaled to estimate σ under normality.
        scale = float(np.median(np.abs(resid - np.median(resid)))) * 1.4826
        if scale < 1e-9:
            break   # (near-)perfect fit — nothing to downweight
        u = np.abs(resid) / scale
        if robust == "huber":
            rw = np.minimum(1.0, _HUBER_K / np.maximum(u, 1e-12))
        else:
            rw = np.where(u < _TUKEY_C, (1.0 - (u / _TUKEY_C) ** 2) ** 2, 0.0)
        cw = rw if w is None else rw * w
        if cw.sum() <= 0:
            break   # everything rejected — keep the previous fit
        new_coeffs = _wls(X, y, cw)
        converged = np.allclose(new_coeffs, coeffs, rtol=1e-6, atol=1e-12)
        coeffs = new_coeffs
        if converged:
            break
    return coeffs


# ── Algorithms ──────────────────────────────────────────────────────────────────

def _global_poly(df: pd.DataFrame, fit_mask: np.ndarray, weights: str = "none",
                 robust: str = "none"):
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

    # Curvature gate: with fewer than 3 distinct expirations in the
    # fit subset, the f·m²·√T term is knife-edged — two maturities
    # can't pin how curvature varies with T, so the column trades a
    # plausible smile for a wild frown (seen on NVTS). Drop it and fit
    # the 5-term surface instead.
    exp_key = "expiration" if "expiration" in fit.columns else "dte"
    with_curv_term = fit[exp_key].nunique() >= 3
    n_params = _GLOBAL_PARAMS if with_curv_term else _GLOBAL_PARAMS - 1
    if len(fit) < n_params + 2:
        return None, None

    def design(frame: pd.DataFrame) -> np.ndarray:
        m = frame["log_moneyness"].to_numpy(dtype=float)
        sqrt_T = np.sqrt(frame["dte"].to_numpy(dtype=float) / 365.0)
        cols = [np.ones_like(m), m, m ** 2, sqrt_T, m * sqrt_T]
        if with_curv_term:
            cols.append(m ** 2 * sqrt_T)
        return np.column_stack(cols)

    try:
        coeffs = _robust_wls(design(fit), fit["iv"].to_numpy(dtype=float),
                             _row_weights(fit, weights), robust)
    except np.linalg.LinAlgError:
        return None, None
    iv_fitted = design(df) @ coeffs
    return iv_fitted, np.full(len(df), "global", dtype=object)


def _poly_design(frame: pd.DataFrame, degree: int) -> np.ndarray:
    """Vandermonde-style design matrix in log-moneyness up to `degree`."""
    m = frame["log_moneyness"].to_numpy(dtype=float)
    return np.column_stack([m ** p for p in range(degree + 1)])


def _per_expiration(df: pd.DataFrame, fit_mask: np.ndarray,
                    weights: str = "none", robust: str = "none"):
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
                coeffs = _robust_wls(_poly_design(fit, degree),
                                     fit["iv"].to_numpy(dtype=float),
                                     _row_weights(fit, weights), robust)
                iv_fitted[positions] = _poly_design(sel, degree) @ coeffs
                methods[positions] = "per_expiry"
                fitted_any = True
                continue
            except np.linalg.LinAlgError:
                pass  # fall through to the global/mean fallback

        # Too few (or zero) fit rows for a local curve — borrow the
        # global surface; if that's unavailable, use the slice mean.
        if not global_done:
            global_arr, _ = _global_poly(df, fit_mask, weights, robust)
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


def _earnings_segmented(df: pd.DataFrame, fit_mask: np.ndarray,
                        weights: str = "none", robust: str = "none"):
    """Fit a separate global-poly surface per earnings regime — exclude nothing.

    Earnings inject a *step* into the term structure: an expiration that
    crosses the next print carries a fixed extra jump variance its just-
    before neighbour doesn't, which a single smooth surface can't represent
    (and excluding the spanners just fits the rest on a thinner slice). Here
    rows are grouped by ``earnings_count`` — the number of prints inside each
    option's [now, expiration] window: 0 = pre-earnings, 1 = spans the next
    print, 2 = spans two, … Each group spans a *smooth* term structure (a
    constant jump count), so ``_global_poly`` fits it cleanly, and every
    option is scored against *its own* regime — so the common earnings
    premium becomes that regime's baseline rather than a per-option signal.

    Intended to pair with a filter set that does NOT include
    ``exclude_earnings`` (nothing is dropped for spanning a print); with
    exclude_earnings still on, a spanning regime has no fit rows and falls
    back to the all-rows surface, degrading to the current behaviour.

    Thin regimes (too few rows for even the 5-term surface — e.g. a lone
    pre-earnings weekly) borrow the all-rows global surface, then the
    regime's mean IV, mirroring ``_per_expiration``'s fallback.

    Returns (iv_fitted, methods): "global" for an own-regime fit, "fallback"
    for borrowed, "none" for an unfittable regime. (None, None) if nothing fit.
    """
    if "earnings_count" not in df.columns:
        return _global_poly(df, fit_mask, weights, robust)

    seg = df["earnings_count"].fillna(0).astype(int)
    iv_fitted = df["iv"].to_numpy(dtype=float).copy()
    methods = np.full(len(df), "none", dtype=object)
    fitted_any = False
    global_arr = None
    global_done = False

    for _, idx in df.groupby(seg).groups.items():
        positions = df.index.get_indexer(idx)
        sub = df.loc[idx]
        sub_mask = fit_mask[positions]

        seg_fitted, _ = _global_poly(sub, sub_mask, weights, robust)
        if seg_fitted is not None:
            iv_fitted[positions] = seg_fitted
            methods[positions] = "global"
            fitted_any = True
            continue

        # Regime too thin for its own surface — borrow the all-rows global
        # fit, then the regime's mean IV (same fallback ladder as per_expiry).
        if not global_done:
            global_arr, _ = _global_poly(df, fit_mask, weights, robust)
            global_done = True
        if global_arr is not None:
            iv_fitted[positions] = global_arr[positions]
            methods[positions] = "fallback"
            fitted_any = True
        elif sub_mask.any():
            iv_fitted[positions] = float(
                sub["iv"].to_numpy(dtype=float)[sub_mask].mean())
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
        "defaults": {"weights": "none", "robust": "none"},
        "label":    "Global polynomial (current)",
        "enabled":  True,
    },
    "per_expiration": {
        "fn":       _per_expiration,
        "defaults": {"weights": "none", "robust": "none"},
        "label":    "Per-expiration polynomial",
        "enabled":  True,
    },
    "earnings_segmented": {
        "fn":       _earnings_segmented,
        "defaults": {"weights": "none", "robust": "none"},
        "label":    "Earnings-segmented (per-regime, no exclusion)",
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
