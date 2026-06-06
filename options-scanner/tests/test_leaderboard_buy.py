"""Buy-mode ranking for the cross-ticker leaderboard.

Sell mode ranks the richest IV+pp first; buy mode must flip so the
cheapest (most-negative IV+pp) floats to the top — both for each
ticker's guaranteed #1 pick and for the final table order.
"""
import pandas as pd

from options_scanner.display.leaderboard import build_leaderboard


def _row(opt_type, strike, iv_excess, oi=500, volume=100, dte=45):
    return {
        "type": opt_type,
        "strike": strike,
        "expiration": "2026-08-21",
        "dte": dte,
        "bid": 1.0,
        "ask": 1.2,
        "mid": 1.1,
        "iv": 0.5,
        "iv_excess": iv_excess,
        "delta": -0.40,
        "ann_yield_pct": 25.0,
        "open_interest": oi,
        "volume": volume,
        "earnings_count": 0,
        "last": 1.1,
        "spot": 150.0,
    }


def _results():
    """Two tickers, each with a rich and a cheap put."""
    return [
        {"error": None, "position": {"ticker": "AAA"},
         "df": pd.DataFrame([_row("put", 140, 0.05),    # rich
                             _row("put", 130, -0.06)])},  # cheapest overall
        {"error": None, "position": {"ticker": "BBB"},
         "df": pd.DataFrame([_row("put", 90, 0.02),
                             _row("put", 80, -0.03)])},
    ]


def test_sell_ranks_richest_put_first():
    board = build_leaderboard(_results(), "put", min_oi=25, top_n=5,
                              min_vol=10, buy=False)
    assert round(board.iloc[0]["iv_excess"], 4) == 0.05


def test_buy_ranks_cheapest_put_first():
    board = build_leaderboard(_results(), "put", min_oi=25, top_n=5,
                              min_vol=10, buy=True)
    assert round(board.iloc[0]["iv_excess"], 4) == -0.06


def test_buy_flips_each_ticker_top_pick():
    board = build_leaderboard(_results(), "put", min_oi=25, top_n=5,
                              min_vol=10, buy=True)
    tops = board[board["_is_ticker_top"]].set_index("ticker")["iv_excess"]
    # each ticker's guaranteed #1 is its cheapest contract
    assert round(tops["AAA"], 4) == -0.06
    assert round(tops["BBB"], 4) == -0.03
