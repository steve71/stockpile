"""Black-Scholes pricing and greeks — the single implementation.

Consolidates the copies that previously lived in
`stocks_shared.yahoo`, `options_scanner.chain`, and
`options_scanner.spreads`. Those modules now import from here
(keeping their historical names as aliases), so behavior is pinned by
the existing test suites.

Conventions shared by every function:
  - S spot, K strike, T years to expiration, r continuously
    compounded risk-free rate, sigma annualized IV.
  - `opt_type` accepts "call"/"put" in any capitalization.
  - Degenerate inputs (T <= 0, sigma below the 0.001 noise floor, or
    non-positive S/K where the math needs them) fall back to the
    intrinsic/limit value instead of raising or returning inf/NaN.
"""

from __future__ import annotations

import math


def norm_cdf(x: float) -> float:
    """Standard normal CDF."""
    return 0.5 * math.erfc(-x / math.sqrt(2))


def norm_pdf(x: float) -> float:
    """Standard normal PDF."""
    return math.exp(-0.5 * x * x) / math.sqrt(2 * math.pi)


def _is_call(opt_type: str) -> bool:
    return opt_type.lower() == "call"


def d1_d2(S: float, K: float, T: float, r: float,
          sigma: float) -> tuple[float, float]:
    """The Black-Scholes d1/d2 pair. Caller guards degenerate inputs."""
    d1 = (math.log(S / K) + (r + 0.5 * sigma ** 2) * T) \
        / (sigma * math.sqrt(T))
    return d1, d1 - sigma * math.sqrt(T)


def bs_price(S: float, K: float, T: float, r: float, sigma: float,
             opt_type: str) -> float:
    """European option price; intrinsic value when T or sigma degenerate."""
    if T <= 0 or sigma < 0.001:
        return max(0.0, S - K) if _is_call(opt_type) else max(0.0, K - S)
    d1, d2 = d1_d2(S, K, T, r, sigma)
    if _is_call(opt_type):
        return S * norm_cdf(d1) - K * math.exp(-r * T) * norm_cdf(d2)
    return K * math.exp(-r * T) * norm_cdf(-d2) - S * norm_cdf(-d1)


def bs_delta(S: float, K: float, T: float, r: float, sigma: float,
             opt_type: str) -> float:
    """Delta; intrinsic-payoff indicator when T or sigma degenerate."""
    if T <= 0 or sigma < 0.001:
        if _is_call(opt_type):
            return 1.0 if S > K else 0.0
        return -1.0 if S < K else 0.0
    d1, _ = d1_d2(S, K, T, r, sigma)
    return norm_cdf(d1) if _is_call(opt_type) else norm_cdf(d1) - 1.0


def bs_gamma(S: float, K: float, T: float, r: float,
             sigma: float) -> float:
    """Gamma (same for calls and puts)."""
    if T <= 0 or sigma < 0.001 or S <= 0:
        return 0.0
    d1, _ = d1_d2(S, K, T, r, sigma)
    return norm_pdf(d1) / (S * sigma * math.sqrt(T))


def bs_theta(S: float, K: float, T: float, r: float, sigma: float,
             opt_type: str) -> float:
    """Daily theta per share (negative = long holder loses value daily)."""
    if T <= 0 or sigma < 0.001 or S <= 0:
        return 0.0
    d1, d2 = d1_d2(S, K, T, r, sigma)
    term1 = -(S * norm_pdf(d1) * sigma) / (2 * math.sqrt(T))
    if _is_call(opt_type):
        return (term1 - r * K * math.exp(-r * T) * norm_cdf(d2)) / 365
    return (term1 + r * K * math.exp(-r * T) * norm_cdf(-d2)) / 365


def bs_vega(S: float, K: float, T: float, r: float,
            sigma: float) -> float:
    """Vega per 1-point IV move (same for calls and puts)."""
    if T <= 0 or sigma < 0.001 or S <= 0:
        return 0.0
    d1, _ = d1_d2(S, K, T, r, sigma)
    return S * norm_pdf(d1) * math.sqrt(T)


def prob_above(S: float, K: float, T: float, r: float,
               sigma: float) -> float:
    """Risk-neutral P(S_T > K) = N(d2)."""
    if T <= 0 or sigma < 0.001 or S <= 0 or K <= 0:
        return 1.0 if S > K else 0.0
    _, d2 = d1_d2(S, K, T, r, sigma)
    return norm_cdf(d2)


def implied_vol(price: float, S: float, K: float, T: float, r: float,
                opt_type: str, *, lo: float = 1e-3, hi: float = 5.0,
                tol: float = 1e-6, iters: int = 100) -> float | None:
    """Implied volatility for an observed option `price`, by bisection.

    Returns the sigma that reprices the option to `price` under `bs_price`,
    or None when the inputs are degenerate or `price` sits below intrinsic
    (not representable by any non-negative vol). `bs_price` is monotone
    increasing in sigma, so a bracketed bisection converges reliably; `lo`/`hi`
    bound the search (0.1%–500% vol) and a price at or beyond a bound clamps
    to it.
    """
    if price is None or price <= 0 or T <= 0 or S <= 0 or K <= 0:
        return None
    intrinsic = max(0.0, S - K) if _is_call(opt_type) else max(0.0, K - S)
    if price < intrinsic - 1e-9:
        return None
    if price <= bs_price(S, K, T, r, lo, opt_type):
        return lo
    if price >= bs_price(S, K, T, r, hi, opt_type):
        return hi
    for _ in range(iters):
        mid = 0.5 * (lo + hi)
        p = bs_price(S, K, T, r, mid, opt_type)
        if abs(p - price) < tol:
            return mid
        if p < price:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)
