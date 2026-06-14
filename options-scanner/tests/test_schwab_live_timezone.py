import pandas as pd
import pytest

from stocks_shared.schwab_live import _parse_schwab_candles, _to_unix_seconds

_EPOCH = int(pd.Timestamp("2026-06-12T20:00:00Z").timestamp())


def test_parse_schwab_candles_normalizes_timezone_aware_strings_to_utc_epoch():
    rows = _parse_schwab_candles({
        "candles": [
            {
                "datetime": "2026-06-12T16:00:00-04:00",
                "open": 1.0,
                "high": 2.0,
                "low": 0.5,
                "close": 1.5,
                "volume": 100,
            }
        ]
    })

    assert len(rows) == 1
    assert rows[0]["time"] == _EPOCH


def test_parse_schwab_candles_handles_integer_millisecond_epoch():
    """Schwab's price-history API returns datetime as epoch milliseconds —
    the actual production path the dashboard relies on."""
    rows = _parse_schwab_candles({
        "candles": [
            {
                "datetime": _EPOCH * 1000,
                "open": 1.0,
                "high": 2.0,
                "low": 0.5,
                "close": 1.5,
                "volume": 100,
            }
        ]
    })

    assert len(rows) == 1
    assert rows[0]["time"] == _EPOCH


def test_to_unix_seconds_integer_milliseconds():
    assert _to_unix_seconds(_EPOCH * 1000) == _EPOCH


def test_to_unix_seconds_old_date_milliseconds():
    """Regression: pre-2001 dates have ms epochs below 1e12. They must
    still be read as ms, not left as far-future seconds. 999666000000 ms
    is 2001-09-05; a 1e12 threshold mis-read it as year 33645."""
    assert _to_unix_seconds(999666000000) == 999666000
    assert _to_unix_seconds(473493600000) == 473493600  # 1985


def test_to_unix_seconds_integer_seconds():
    assert _to_unix_seconds(_EPOCH) == _EPOCH


def test_to_unix_seconds_numeric_string_milliseconds():
    assert _to_unix_seconds(str(_EPOCH * 1000)) == _EPOCH


@pytest.mark.parametrize("bad", ["not-a-date", True, None, float("nan")])
def test_to_unix_seconds_rejects_invalid(bad):
    with pytest.raises(ValueError):
        _to_unix_seconds(bad)
