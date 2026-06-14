"""Ticker normalization — index prefixes and class-share separators.

Both providers accept any of the three class-share notations (NYSE tape
dot, Yahoo dash, Schwab slash) and rewrite to their own form, so a
watchlist ticker normalized for Yahoo still re-normalizes correctly when
the Schwab fetch path runs it through normalize_ticker_schwab.
"""

import pytest

from stocks_shared.schwab_live import normalize_ticker_schwab
from stocks_shared.yahoo import normalize_ticker


# ── Yahoo ────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("raw, expected", [
    ("AAPL", "AAPL"),
    ("aapl", "AAPL"),
    (" amd ", "AMD"),
    ("SPX", "^SPX"),          # index → ^NAME
    ("^VIX", "^VIX"),
    ("$NDX", "^NDX"),
    ("SPX!", "SPX"),          # trailing ! escapes normalization
    ("BRK.B", "BRK-B"),       # class shares: dot / dash / slash → dash
    ("BRK-B", "BRK-B"),
    ("BRK/B", "BRK-B"),
    ("bf.a", "BF-A"),
])
def test_normalize_ticker_yahoo(raw, expected):
    assert normalize_ticker(raw) == expected


# ── Schwab ───────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("raw, expected", [
    ("AAPL", "AAPL"),
    ("SPX", "$SPX"),          # index → $NAME
    ("^RUT", "$RUT"),
    ("SPX!", "SPX"),          # trailing ! escapes normalization
    ("BRK.B", "BRK/B"),       # class shares: dot / dash / slash → slash
    ("BRK-B", "BRK/B"),
    ("BRK/B", "BRK/B"),
    ("bf.a", "BF/A"),
])
def test_normalize_ticker_schwab(raw, expected):
    assert normalize_ticker_schwab(raw) == expected


def test_yahoo_form_renormalizes_for_schwab():
    """Watchlist tickers are Yahoo-normalized first, then hit the Schwab
    normalizer inside the fetch path — the chain must end at slash form."""
    assert normalize_ticker_schwab(normalize_ticker("BRK.B")) == "BRK/B"


@pytest.mark.parametrize("raw", [
    "AB.CD",     # multi-letter suffix: not class-share notation
    "BRK.",      # dangling separator
    ".B",        # no root
])
def test_non_class_share_forms_pass_through(raw):
    assert normalize_ticker(raw.upper()) == raw.upper()
    assert normalize_ticker_schwab(raw.upper()) == raw.upper()
