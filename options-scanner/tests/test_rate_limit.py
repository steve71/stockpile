"""Yahoo rate-limit detection and propagation.

A throttled fetch must surface as RateLimitError (so the portfolio scan
can wait and retry) rather than being swallowed as a generic per-ticker
failure or a skipped expiration.
"""

import pytest

from options_scanner import chain
from stocks_shared.yahoo import RateLimitError, is_rate_limit_error


class _FakeYFRateLimit(Exception):
    pass


_FakeYFRateLimit.__name__ = "YFRateLimitError"


@pytest.mark.parametrize("exc, expected", [
    (_FakeYFRateLimit("anything"), True),          # matched by type name
    (Exception("429 Client Error: Too Many Requests"), True),
    (Exception("Yahoo rate limit exceeded"), True),
    (Exception("No data found for ticker"), False),
    (ValueError("Could not fetch live price for X"), False),
])
def test_is_rate_limit_error(exc, expected):
    assert is_rate_limit_error(exc) is expected


def test_spot_rate_limit_propagates(monkeypatch):
    """A throttled spot lookup raises RateLimitError out of the chain
    fetch instead of the generic could-not-fetch ValueError."""
    def _throttled(t, **kw):
        raise RateLimitError(f"Yahoo rate limit hit fetching {t}")
    monkeypatch.setattr(chain, "fetch_live_price", _throttled)
    monkeypatch.setattr(chain, "normalize_ticker", lambda t: t)
    with pytest.raises(RateLimitError):
        chain._fetch_chain_yahoo("AAPL", min_dte=0, max_dte=60)


def test_degraded_chain_raises(monkeypatch):
    """Yahoo's soft throttle serves HTTP-200 chains with every bid/ask
    zeroed and IV at the 0.00001 placeholder. That must surface as
    RateLimitError, not as an empty (or nearly empty) result."""
    import datetime
    import pandas as pd
    import yfinance as yf
    from types import SimpleNamespace

    exp = (datetime.date.today() + datetime.timedelta(days=30)).isoformat()
    degraded = pd.DataFrame({
        "strike": [90.0 + i for i in range(12)],
        "bid": [0.0] * 12,
        "ask": [0.0] * 12,
        "lastPrice": [1.0] * 12,
        "impliedVolatility": [0.00001] * 12,
        "openInterest": [10] * 12,
        "volume": [0] * 12,
    })

    class _Ticker:
        def __init__(self, t):
            self.options = (exp,)

        def option_chain(self, e):
            return SimpleNamespace(calls=degraded, puts=degraded.copy())

    monkeypatch.setattr(chain, "fetch_live_price", lambda t, **kw: 100.0)
    monkeypatch.setattr(chain, "normalize_ticker", lambda t: t)
    monkeypatch.setattr(yf, "Ticker", _Ticker)
    with pytest.raises(RateLimitError, match="degraded"):
        chain._fetch_chain_yahoo("AAPL", min_dte=0, max_dte=60)


def test_expiration_rate_limit_propagates(monkeypatch):
    """A throttle on a per-expiration chain call re-raises instead of
    being 'skipped' like an ordinary bad expiration."""
    import datetime
    import yfinance as yf

    exp = (datetime.date.today() + datetime.timedelta(days=30)).isoformat()

    class _Ticker:
        def __init__(self, t):
            self.options = (exp,)

        def option_chain(self, e):
            raise _FakeYFRateLimit("Too Many Requests. Rate limited.")

    monkeypatch.setattr(chain, "fetch_live_price", lambda t, **kw: 100.0)
    monkeypatch.setattr(chain, "normalize_ticker", lambda t: t)
    monkeypatch.setattr(yf, "Ticker", _Ticker)
    with pytest.raises(RateLimitError):
        chain._fetch_chain_yahoo("AAPL", min_dte=0, max_dte=60)
