"""Shared number-formatting helpers.

Leaf module — no internal imports, safe to import anywhere (display,
tabs, report, CLI). Centralizes strike formatting so 2.5-/0.25-wide
strikes (NVDA, TSLA, AAPL, SOFI, …) render their decimals everywhere
instead of being rounded to the nearest dollar.
"""

from __future__ import annotations

# d3-format string for option strikes on Altair/Vega and Plotly
# charts. The `~` trims trailing zeros so whole strikes render as
# "$145" while fractional strikes keep their decimals ("$142.5",
# "$12.75"). Mirrors `fmt_strike` below for f-string call sites.
STRIKE_D3_FORMAT = "$,.2~f"


def fmt_strike(strike) -> str:
    """Format an option strike as a dollar string.

    Shows decimals only when the strike isn't a whole number:
    145 -> "$145", 142.5 -> "$142.5", 12.75 -> "$12.75". Keeps
    big-ticker integer strikes clean while preserving fractional
    strikes. Mirrors `STRIKE_D3_FORMAT` used on the charts.
    """
    x = float(strike)
    if x.is_integer():
        return f"${x:,.0f}"
    return f"${x:,.2f}".rstrip("0").rstrip(".")
