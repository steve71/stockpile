---
name: options-scanner
description: "Rank option chain candidates by how far their implied
  volatility sits above or below a fitted surface (IV+pp). Use when
  asked to find IV-rich options to sell (covered calls, cash-secured
  puts), IV-cheap options to buy (protective puts, LEAPS), or to scan
  a watchlist for the strongest signals. Returns ticker, spot, and
  ranked candidates with IV+pp, delta, bid/ask, and annualized yield."
argument-hint: "TICKER [TICKER...] [--calls|--puts] [--buy]
  [--min-dte N] [--max-dte N] [--min-ivpp N]
  [--data-source yahoo|schwab] [--agent]"
allowed-tools: "Read Bash"
---

# Options Scanner

Ranks each option in a chain by how far its implied volatility (IV)
sits above or below a smoothly-fitted volatility surface. Options
sitting significantly above the surface (positive IV+pp) are
IV-rich — candidates to sell for premium. Options sitting below
(negative IV+pp) are IV-cheap — candidates to buy for leverage.

## Prerequisites

Run from the `stockpile/` repo root with `uv` installed:

```bash
uv sync
```

Entry points:

- `uv run python options-scanner/run_scanner.py` — single or
  multi-ticker scan
- `uv run python options-scanner/run_portfolio.py` — scan all open
  stock positions from a brokerage CSV

## When to Use

Use when asked to:

- Find covered call or cash-secured put candidates for a ticker
- Find IV-cheap options to buy (protective puts, LEAPS)
- Scan a list of tickers and compare opportunities
- Roll an existing short option position

Do **not** use when:

- The user needs real-time bid/ask for live order entry (use broker)
- The user needs Greeks without IV surface context

## Command Mapping

| Question | Command |
|---|---|
| Find covered call candidates for AAPL | `run_scanner.py AAPL --calls --agent` |
| Scan AAPL MSFT NVDA for IV-rich puts | `run_scanner.py AAPL MSFT NVDA --puts --agent` |
| Find IV-cheap LEAPS to buy on SPY | `run_scanner.py SPY --buy --min-dte 180 --agent` |
| Only show strong signals (≥ 5 pp) | `run_scanner.py AAPL --min-ivpp 5 --agent` |
| Scan 30–60 DTE via Schwab | `run_scanner.py AAPL --min-dte 30 --max-dte 60 --data-source schwab --agent` |
| Scan a Schwab brokerage CSV | `run_portfolio.py positions.csv --brokerage schwab --agent` |

## Key Flags

| Flag | Default | Effect |
|---|---|---|
| `--agent` | off | Implies `--json` + `--quiet`. Always use from scripts and agents. |
| `--json` | off | Emit JSON instead of a formatted table |
| `--quiet` | off | Suppress progress log lines to stderr |
| `--calls` / `--puts` | both | Filter to one option type |
| `--buy` | off | Reverse ranking — surface IV-cheap (buy) candidates |
| `--min-dte` | 30 | Minimum days to expiration |
| `--max-dte` | 90 | Maximum days to expiration |
| `--min-oi` | 25 | Minimum open interest per contract |
| `--min-vol` | 10 | Minimum today's volume per contract |
| `--min-ivpp` | none | Only return options where abs(IV+pp) ≥ N pp |
| `--top` | 10 | Max candidates returned per option type |
| `--min-delta` | 0.10 | Exclude very far OTM options |
| `--max-delta` | 0.75 | Exclude deep ITM options |
| `--data-source` | config | `yahoo` (free, may be stale) or `schwab` (real-time) |
| `--no-legend` | off | Suppress the "how to read" footer in terminal output |
| `--preset` | current | Surface-fit preset: `current` (global poly + raw IV+pp) or `v2` (per-expiration spread-weighted, earnings excluded, z-score) |
| `--algorithm` | preset | Surface-fit algorithm: `global_poly` or `per_expiration` |
| `--fit-weights` | none | Fit weighting (with `--algorithm`): `none`, `oi`, or `inv_spread` |
| `--score` | preset | Ranking score: `raw_pp`, `zscore`, `relative`, `composite_exec`, `vrp`, `percentile` |

## JSON Output Schema (`--agent` or `--json`)

Single ticker returns an object; multiple tickers return an array of
objects.

```json
{
  "ticker": "AAPL",
  "spot": 175.50,
  "data_source": "schwab",
  "scan_time": "2026-05-22T14:30:00Z",
  "mode": "sell",
  "candidates": [
    {
      "type": "call",
      "strike": 185.0,
      "expiration": "2026-06-20",
      "dte": 29,
      "bid": 1.50,
      "ask": 1.55,
      "mid": 1.53,
      "iv_pct": 28.5,
      "iv_pp": 6.2,
      "signal_score": 0.062,
      "signal_kind": "IV+pp",
      "delta": 0.28,
      "ann_pct": 4.8,
      "open_interest": 1250,
      "earnings_before_exp": false,
      "hv_20": 0.241,
      "vr_ratio": 1.18
    }
  ]
}
```

- `signal_score` is the value the candidates are ranked by; `signal_kind`
  names the active score (defaults to `IV+pp`, where `signal_score`
  equals `iv_pp / 100`). With another `--score`, `signal_score` is in
  that score's own units (σ for z-score, ratio for VRP, 0–100 for
  percentile).
- `hv_20` is 20-day annualized realized vol; `vr_ratio = iv / hv_20`.
  Both are `null` when price history is unavailable. `vr_ratio` and
  `percentile` may be `null` during cold start.
- `net_credit` is added to each candidate when `--roll` is used.

## Reading IV+pp

| Value | Interpretation |
|---|---|
| < 3 pp | Roughly uniform chain — no strong surface deviation |
| 3–5 pp | Moderate signal |
| > 5 pp | Strong signal — option is meaningfully IV-rich |
| Negative (buy mode) | Option sits below surface — IV-cheap |

IV+pp is a screening signal, not a mispricing guarantee. Verify
bid/ask and Greeks with your broker before acting.

## Roll Mode

Find roll candidates for an existing short position. Adds
`net_credit` to each candidate showing net premium after closing.
Only valid for a single ticker.

```bash
uv run python options-scanner/run_scanner.py AAPL \
  --roll --type call --strike 185 --expiration 2026-06-20 --agent
```

## Data Sources

- **Yahoo Finance** (default) — free, no setup, but IV may be stale
  on thinly-traded strikes. See `SCHWAB_DATA_SOURCE.md` for the
  known limitations.
- **Schwab developer API** — real-time NBBO, live Greeks. Requires a
  Schwab brokerage account and one-time developer setup. See
  `SCHWAB_DATA_SOURCE.md`.
