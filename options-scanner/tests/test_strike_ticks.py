"""strike_tick_values forces axis ticks onto real strikes (issue #23).

Vega-Lite auto-ticks land on round steps, so fractional strikes (152.5,
7.5) never get a labeled tick. The helper returns the actual strikes so
the axis can pin ticks to them.
"""
from options_scanner.format import strike_tick_values


def test_keeps_fractional_strikes_when_few():
    strikes = [140 + 2.5 * i for i in range(11)]  # 140, 142.5, … 165
    vals = strike_tick_values(strikes)
    assert 142.5 in vals and 152.5 in vals
    assert vals == sorted(vals)
    assert len(vals) == 11


def test_domain_clip_keeps_endpoints_inclusive():
    strikes = [140 + 2.5 * i for i in range(11)]
    vals = strike_tick_values(strikes, lo=145, hi=155)
    assert min(vals) >= 145 and max(vals) <= 155
    assert 147.5 in vals and 152.5 in vals  # fractional strikes survive


def test_thins_dense_grid_but_keeps_real_strikes():
    strikes = [10 + 0.5 * i for i in range(60)]  # 60 strikes
    vals = strike_tick_values(strikes, max_ticks=16)
    assert len(vals) <= 16
    real = {round(s, 4) for s in strikes}
    assert set(vals).issubset(real)


def test_empty_inputs():
    assert strike_tick_values([]) == []
    assert strike_tick_values([None, None]) == []
