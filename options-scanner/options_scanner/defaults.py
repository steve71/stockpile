"""Shared UI defaults for the scanner tabs.

Per-direction default delta bands. The screen filters on absolute delta,
so calls and puts collapse to the same band within each direction — the
default depends only on Sell vs. Buy:

- **Selling** wants OTM, likely-to-expire-worthless strikes (low delta);
  too far OTM earns negligible premium. Sweet spot ~0.15-0.35.
- **Buying** pays a debit for direction, so it wants enough delta to
  participate in the move without overpaying for deep-ITM (which behaves
  like stock with less leverage). ATM-centered ~0.35-0.65.
"""

from __future__ import annotations

SELL_DELTA_RANGE: tuple[float, float] = (0.15, 0.35)
BUY_DELTA_RANGE: tuple[float, float] = (0.35, 0.65)


def default_delta_range(buy: bool) -> tuple[float, float]:
    """Default (min, max) absolute-delta band for the given direction."""
    return BUY_DELTA_RANGE if buy else SELL_DELTA_RANGE
