# CLAUDE.md

## Purpose

YouTube tutorial project: build charts showing stock cost basis over time, overlaid
on Yahoo Finance historical price data, using brokerage transaction CSV exports and
Claude Code.

## Core idea

Parse a brokerage transaction CSV (Schwab or Robinhood) to compute running cost basis
per share over time as buys, sells, and covered call premiums are applied. Fetch
historical OHLC price data from Yahoo Finance (yfinance). Plot both on a chart so the
viewer can see how their adjusted cost basis compares to the stock price at each point.

## Data sources

- Brokerage CSV exports (parsers from the `stocks-shared` package:
  `shared/stocks_shared/parsers/`)
- Yahoo Finance historical prices via `yfinance` (`Ticker.history()`)

## Chart ideas

- Stock price vs. adjusted cost basis over time (line chart)
- Cumulative option premium collected over time (area chart)
- P&L over time: (price - cost basis) * shares held

## Tech stack

- Python, yfinance, matplotlib or plotly
- Possibly output to Google Sheets charts or as standalone HTML/PNG

## YouTube angle

Show the full Claude Code workflow: describe what you want, let Claude write the
parsing and charting code, iterate on the output visually.

## Running the tool

Always run from the **repo root** (`stockpile/`), not from this
subdirectory. Use `uv run` so the shared `.venv` and `stocks-shared`
package are available:

```bash
uv run cost-basis-charts/run_charts.py
uv run cost-basis-charts/run_charts.py --symbol SCHW
```

Never use `python` or `python3` directly — they won't have the
project's dependencies. Run `uv sync` from the repo root after any
`pyproject.toml` change.

## Output

HTML (and optional PNG) files are written to
`cost-basis-charts/output/` by default. Override with
`--output-dir`. The output directory is gitignored.
