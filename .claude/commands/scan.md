---
description: Scan an option chain and rank options by IV vs. a fitted surface (sell or buy candidates)
---

Run the options scanner for the provided ticker and any extra flags:
`$ARGUMENTS`.

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
| Find covered call candidates for AAPL | `run_scanner.py AAPL --calls` |
| Scan AAPL MSFT NVDA for IV-rich puts | `run_scanner.py AAPL MSFT NVDA --puts` |
| Find IV-cheap LEAPS to buy on SPY | `run_scanner.py SPY --buy --min-dte 180` |
| Only show strong signals (≥ 5 pp) | `run_scanner.py AAPL --min-ivpp 5` |
| Scan 30–60 DTE via Schwab | `run_scanner.py AAPL --min-dte 30 --max-dte 60 --data-source schwab` |
| Roll an existing short call | `run_scanner.py AAPL --roll --type call --strike S --expiration DATE` |

## Execution

Execute from the repo root:

```
uv run options-scanner/run_scanner.py $ARGUMENTS
```

Common flags: `--calls`, `--puts`, `--buy`, `--min-dte N`, `--max-dte N`,
`--min-oi N`, `--min-delta D`, `--max-delta D`, `--top N`, `--html`,
`--browser`, `--roll --type call --strike S --expiration YYYY-MM-DD`.

If `$ARGUMENTS` is empty, ask for a ticker before running. Show the
scanner's stdout to the user. If `--html` or `--browser` was passed,
surface the output path so they can open it.
