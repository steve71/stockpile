# Plan: Diagnose the at-the-money IV gap (real skew vs. artifact)

## Context

The volatility-surface chart (`options-scanner`, Single Ticker tab) shows
a step at the spot price: dots left of spot sit low, dots right sit high,
and the smooth fitted line appears to "miss" the dots near the money. This
looked like a fit bug and raised the question of whether to fit two
separate lines (one per side of spot).

A one-off Yahoo pull (MSFT, Jul 17 '26, 48 DTE, spot $450.24) shows the
"gap" is **two separate data artifacts, not a real smile feature** — and a
continuous smile is the correct truth, so two split lines would be wrong.
The user wants to **confirm the cause with numbers before changing any
code**. No code changes in this plan.

## Findings so far

- Put-call parity is violated in the raw provider IVs (same strike, same
  expiry should match): K455 call 31.4 / put 29.9; K470 31.8 / 30.3; K485
  31.5 / 31.5. The call-over-put offset that shrinks deep OTM is the
  fingerprint of a **forward/carry (dividend+rate) mismatch** in the IV
  inversion, not genuine skew.
- Using only clean OTM quotes, Yahoo still shows a ~2.5pp step at the
  money: OTM puts ~29%, OTM calls ~31.5%.
- Yahoo's ITM calls read high and smooth (34% -> 31.5% into spot), so a
  calls-only Yahoo chart has no big visual gap. Schwab's ITM calls read
  low (~28%), creating the cliff. => the big Schwab gap is **stale Schwab
  ITM marks** (weekend staleness), which the fit already ignores via
  `otm_only` (`iv_filters.py:29`).

Net: (A) big Schwab gap = stale ITM marks, display-only (fit unaffected);
(B) ~2.5pp OTM put/call step = forward/carry artifact, present even in
Yahoo and does feed the fit.

## Recommendation

**Diagnose only now.** The decision-relevant unknown is whether the carry
offset (B) actually moves the top-N picks. If it doesn't (expected), the
likely follow-up is a small display fix, not the heavy forward re-anchor.
Defer any code change until the numbers are in.

## Diagnosis steps (read-only; throwaway scripts, deleted after)

1. **Forward-parity test (Yahoo, now).** Per expiration, regress `C - P`
   on strike `K` to back out the parity-implied forward `F` and discount
   factor; compare `F` to spot. Re-center `log_moneyness` on `F` and check
   whether the OTM put/call step collapses. Proves and quantifies the
   carry artifact.
2. **Ranking-impact test (Yahoo, now).** Recompute the surface with
   moneyness centered on `F` (reusing `iv_surface.compute_iv_excess`) and
   compare the per-side top-N picks vs. the current spot-centered fit.
   This is the go/no-go for whether any fit change is worth it.
3. **Render check.** Confirm the chart already draws `in_fit == False`
   (ITM) dots hollow — `iv_chart.py:301-328` splits `bg_fit` (filled) from
   `bg_excl` (hollow); `in_fit` is set in `iv_surface.py:63`.
4. **Stale-Schwab confirmation (later — weekday + fresh token).** Re-pull
   the same expiration midweek; verify the low ITM marks were
   0-volume / wide-spread / stale `lastPrice`, and that the big gap shrinks
   on live data. Cannot run now (weekend + Schwab token 7-day TTL).

## Decision after diagnosis (no commitment now)

- **Carry offset small / rankings unchanged** -> display fix only:
  hide or unmistakably de-emphasize ITM dots on single-type charts
  (`iv_chart.py`) + a "marks may be stale (weekend/after-hours)" note for
  the Schwab provider. Cheapest, lowest-risk, resolves the confusion.
- **Carry offset materially distorts put vs. call rankings** -> scope a
  forward re-anchor separately: `log_moneyness` in `chain_common.py:87`
  plus ripple through `iv_surface` / `iv_scores` and the percentile-score
  history baseline. Heavy and risky; not part of this plan.
- **Stale-mark guard**: likely unnecessary (`otm_only` + `spread_pct`
  already cover the fit); revisit only if stale marks leak into the OTM
  side.

## Not recommended

Two fitted lines split at spot. It models the artifact as if real, injects
a discontinuity that put-call parity forbids, and feeds a misleading
surface into the IV+pp score.

## Verification

Diagnosis is complete when we can state: (a) the parity-implied forward
and how far it sits from spot, (b) whether re-anchoring on `F` collapses
the OTM step, (c) whether the per-side top-N picks change, (d) ITM dots
confirmed hollow. Then choose a follow-up (or none). Throwaway diagnostic
scripts are removed afterward; no repo files are modified by this plan.
