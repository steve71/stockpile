# Assisted put-selling — implementation plan

Feature behind the ep9 episode ("the scanner can place a trade"). This
doc is the build/design plan; the YouTube concept lives in the sibling
private repo at
`../stockpile-private/options-scanner/youtube/ep9-place-put-trades/script.md`.

## Hard guardrails (enforce in code, not just UI)

1. **Sell puts only.** Single-leg, sell-to-open, cash-secured puts. No
   buys, no calls, no multi-leg — reject anything else before it can
   reach the order builder, even if the Schwab API would accept it.
2. **Human approval always.** The scanner recommends; it never fires.
   Every order stops at a "Place Trade" button the user clicks.
3. **Schwab only.** Placing orders needs Schwab trading scope beyond the
   read-only quotes Yahoo/Schwab give us today. The whole flow is
   Schwab-gated.

## Scope today (what's stubbed — DONE)

- Per-row **investigate** control on the watchlist **Puts leaderboard**,
  gated to watchlist + Sell + Schwab (`allow_investigate` in
  `tabs/portfolio.py` → `display/leaderboard.py`).
  - Implemented as single-row selection on the existing `st.dataframe`
    (mirrors the spreads-tab pattern), so the per-row control reuses the
    styled table rather than rebuilding it.
- Selecting a put row opens `_investigate_put_dialog` (`@st.dialog`):
  shows the live snapshot (bid/ask/mid/last, IV, volume, OI) and a
  "Not implemented yet" notice previewing the planned go/no-go +
  recommended limit + Place Trade gate. A disabled **Place Trade**
  button marks where the gate will live.

Everything below is **not built yet**.

## Phase 1 — Fill-quality check (read-only, no order)

The "is this *executable* well right now?" judgment — distinct from the
IV+pp ranking, which already answers "is this a good trade?".

- **New module** `options_scanner/trade_actions.py` (or `assist.py`):
  - `assess_fill(contract) -> FillAssessment` taking bid, ask, last,
    mid, IV, volume, OI.
  - Signals to combine: bid/ask spread width (absolute **and** as % of
    mid), OI floor, today's-volume floor, last-vs-mid sanity. Output:
    `go | no-go` + `reason` + `suggested_limit`.
  - Limit-price policy: start with **mid**, optionally one tick inside
    the spread; expose an "aggressive vs. patient" choice later (open
    question). Round to the contract's tick size.
- **Live re-quote on click.** The leaderboard snapshot can be minutes
  old; re-fetch the single contract's quote from Schwab inside the
  dialog before assessing (reuse `stocks_shared.schwab_live`). Show the
  fetch time.
- **Dialog upgrade.** Replace the stub body with: the assessment verdict
  (color-coded go/no-go), the reasoning, the recommended limit price
  (editable `st.number_input`), and the contract collateral
  (`strike × 100`). Surface the "no-go" path explicitly (wide spread,
  thin OI → recommend waiting).
- **Tests.** Unit-test `assess_fill` over tight/wide/thin fixtures
  (golden go and no-go cases). Add to the options-scanner test backlog.

## Phase 2 — Place the order (the gate)

- **Schwab trading scope.** Confirm what the Schwab API requires to
  place an options order vs. read quotes: OAuth scope, account
  trading-enabled, the order-entry endpoint. Builds on the existing
  `schwab_auth.py` flow (7-day token TTL). Document the re-auth /
  permission steps the way ep2 did for quotes.
- **Paper/sandbox first.** Confirm a Schwab paper/sandbox order path
  exists; the ep9 demo and our own testing must use it. Add a clear
  **paper-mode indicator** in the UI and a config flag
  (`[schwab] paper = true`) so live orders are opt-in.
- **Put-selling capacity.** Pull the account's available cash (and
  margin available, if a margin account) from Schwab, and show **how
  much we could sell** — how many of this put the account can secure =
  available cash (or margin) ÷ (strike × 100). Surface it in the
  investigate dialog so sizing is informed before the order builder, and
  use it as the cap / default for the quantity input below.
- **Order builder** in `trade_actions.py`:
  - `build_put_sell_order(contract, limit, qty) -> order_payload` —
    single-leg SELL_TO_OPEN PUT, LIMIT, DAY (or GTC?), quantity.
  - **Validate before send:** type == put, action == sell-to-open,
    single leg, qty ≥ 1, limit > 0, and total collateral
    (qty × strike × 100) ≤ available cash / margin (the put-selling
    capacity above). Raise on anything else (guardrail #1 enforced here,
    not in the UI).
  - `place_order(client, account_hash, payload)` → return Schwab order
    id + status. Handle reject/error and surface it.
- **Approval-gate UI.** A **number-of-contracts input** (qty, default 1,
  capped at the put-selling capacity above) — the credit, collateral,
  and remaining capacity update live as qty changes. The Place Trade
  button becomes enabled only after a "go" assessment; clicking shows a
  final confirm with the exact order ("SELL 2 AAPL 2026-01-16 $180 PUT @
  $2.35 limit, collateral $36,000") and a paper/live badge. Record the
  result.

## Phase 3 — Trade tracker tab (P/L + closing)

A new top-level tab ("Trades") — **structural change, confirm with the
user before adding**.

- **Store.** Decide persistence (open question). Likely a local JSON
  (like watchlists, in a gitignored dir) recording each placed order:
  ticker, strike, expiration, qty, credit received, Schwab order id,
  placed-at, paper/live, status. Optionally reconcile against a live
  Schwab positions/orders pull each session (hybrid).
- **Per-position view:**
  - Live **cost-to-close** = current ask/mid to buy the put back
    (re-quote via Schwab).
  - Running **expected/unrealized P/L** = credit received − current
    close cost (× 100 × qty).
  - Status (open / expired / closed / assigned), DTE, LT-cap-gains
    qualifying date (reuse existing logic).
- **Closing flow:** "Suggest close limit" (mirror Phase 1 policy for a
  BUY_TO_CLOSE), let the user edit it, then a Place Closing Trade button
  → `build_put_close_order` (BUY_TO_CLOSE PUT, LIMIT) → `place_order`.
  Same guardrails and confirm gate.
- **Verify-at-broker caveat** shown throughout (numbers are estimates).

## Schwab API specifics to confirm

- Exact OAuth scope / account flag for order entry.
- Order-entry endpoint + payload schema for single-leg options.
- Paper/sandbox availability and how to target it.
- Account hash retrieval (already used for quotes? confirm).
- Account balances endpoint — available cash and margin available — to
  compute how much we can sell (capacity = cash / margin ÷ collateral)
  and to validate qty before sending.
- Tick-size / price-increment rules for the limit price.

## Open questions (from the concept)

- Recommendation surface — dialog (current stub) vs. inline expander vs.
  side panel. Stub uses a dialog; revisit if it feels cramped.
- Tracker persistence — local JSON, read-back from Schwab, or hybrid.
- Investigate per-row-on-click (current) vs. bulk auto-run across the
  whole leaderboard. Per-row keeps it deliberate.
- Limit-price opinionation — single suggested price vs. an
  aggressive/patient range.

## Touch points (current code)

- `options_scanner/display/leaderboard.py` — investigate control +
  dialog stub (Phase 1 UI grows here / into `trade_actions.py`).
- `options_scanner/tabs/portfolio.py` — `allow_investigate` gating
  (`_render_scan_tab`, watchlist branch).
- `stocks_shared/schwab_live.py` — Schwab client, quotes, chain fetch
  (extend for order entry / single-contract re-quote).
- `options_scanner/config.py` — `[schwab]` config (add paper flag).
- `run_app.py` — add the "Trades" tab (Phase 3, confirm first).
