

Here's a conversation between me (Shuffles) and LGbengs about surface fit.
I'm trying to break it down into
1) a filter used to screen the data used to compute the IV surface
2) An algorithm that computes the surface from that filtered data
3) A computed signal or score that can rank how 'good' an contract is compared to others
based on where it is compared to the IV surface curve.

----- conversation

Shuffles:
[I read LGBengs critique below]
Lot of information there, and honestly, I'm not qualified to make a call on this.
I do have a thought/suggestion though.

Did you notice the new Surface Fit Filters on the scanner, just below the Min DTE row?
I was thinking of extending that idea, and allowing pluggable surface fit filters and algorithms there.
Would a configurable surface fit filter and algorithm satisfy your critique or your vision?
We could describe a few surface fit filters and algorithms to Claude, and have Claude
make them configurable and let the user select the one they want to use.

We'd need to make the surface fit algorithm compute a score or signal rather than IV+pp,
and it would need to describe what that score means.

LGbengs:
i agree with your thinking on pluggable filters. The question i keep asking myself is how
can i make the scanner more efficient in serving its users to make better decisions and make money.

----- snip, conversation continues...

Shuffles:
So my plan next week will be to tell Claude to make the surface filters and line fit pluggable,
and have Claude make a filter and fit for the current logic.  Then feed Claude your text and tell
him to make another filter and fit for it.  Is that doing a decent job capturing the initial
use case in your opinion?

LGbengs:
I will suggest you put it to claude like this, that one of the contributors critique the single ticker tab
with the below submission, do you agree? and how can i make the the surface filters and line fit pluggable
if the submission is valid . That way we are getting claude to think

----- LGbengs critique:

1. IV excess is absolute, not relative
Currently iv_excess = actual_IV − fitted_IV is in raw percentage points. A +5pp excess on a 15% IV stock (MSFT in a quiet patch) signals very differently from +5pp on a 60% IV stock (NVDA into earnings). You can't compare signals across tickers, and even within a ticker the signal doesn't scale with the baseline noise.

Fix: Normalize by either:

Relative excess: iv_excess / fitted_IV — "10% above surface" instead of "+3pp"
Z-score: iv_excess / std(residuals) — express excess in standard deviations from the surface. This is the most statistically honest framing — a +1.5σ signal means something regardless of ticker.

2. Earnings options contaminate the surface fit
Options spanning an upcoming earnings event carry a legitimate IV premium (the market is pricing the jump risk). The current model annotates them after fitting, but they're still included in the regression. A cluster of high-IV earnings-spanning contracts pulls the fitted surface upward, which undersells the excess of non-earnings options and oversells the excess of everything else.

Fix: Exclude options with earnings_count > 0 from the surface regression (they already have that column). They'd still receive iv_fitted and iv_excess values from the model, they just wouldn't define the model.

3. The regression is unweighted
A contract with OI = 10 gets the same influence on the surface as one with OI = 5,000. Illiquid options with stale or wide-spread quotes shouldn't anchor the model.

Fix: Use weighted least squares (np.linalg.lstsq doesn't do weights natively, but it's trivial to pre-multiply): weight by OI, or by 1 / (ask - bid) (tighter spread = more reliable quote = more weight).

4. No comparison to realized volatility
The scanner finds options that are rich relative to other options on the same chain. But it doesn't answer "is this ticker's overall IV level elevated vs. what the stock actually does?" — the volatility risk premium (VRP) question. You could sell an IV-rich option on a ticker where every option is fairly priced vs. historical vol, and vice versa.

Fix: Add a hv_20 (20-day realized vol) column and a vr_ratio = IV / hv_20 metric. This is orthogonal to iv_excess and lets you combine the two signals: strong candidates have high iv_excess and high vr_ratio.

5. The polynomial surface model is global and rigid
The current model fits one curve across the whole chain. Problems:

It doesn't handle skew discontinuities well (e.g., a steep put skew combined with a flat call side)
Deep OTM and long-DTE options often behave differently from the core ATM/near-DTE cluster
The polynomial can produce poor extrapolations at the edges
Better model options:

Per-expiration normalization: Fit one simple model per expiration (just vs. moneyness), then compute excess within that expiration. This eliminates term-structure noise entirely and is much simpler to reason about.
SVI (Stochastic Volatility Inspired): The industry-standard 5-parameter vol surface model. Calibrates to each expiration slice separately. More work to implement but produces arbitrage-free surfaces.

6. Ranking doesn't penalize execution cost
Two options with iv_excess = +8pp rank equally, even if one has a bid-ask spread of $0.05 and the other $1.20. The wide-spread option may be impossible to fill near mid.

Fix: Introduce a composite score like:

signal_score = iv_excess / max(spread_pct, 0.05)
where spread_pct = (ask - bid) / mid. Options you can't fill cleanly get discounted in the ranking, not just in the surface filter.

7. No historical percentile context
A +5pp excess on AAPL today might be extraordinary or routine — there's no baseline. Without knowing the historical distribution of iv_excess for this ticker, a single reading is hard to calibrate.

Fix: If you cache scan results (or pull a short history), you can express excess as a percentile rank: "this option is in the 92nd percentile of IV richness for this ticker over the past 30 days." That context turns a raw number into an actionable signal.