# CLAUDE.md — positions

Claude Code instructions for the Google Sheets position tracker.

## Purpose

Turn a brokerage transaction CSV into a fully formatted Google Sheet —
stock positions, covered calls, sold puts, dividends, a P&L breakdown,
and a cross-position summary — with live prices from Yahoo Finance.

## Running the tool

Always run from the **repo root** using `uv run`:

```bash
uv run positions/run_tracker.py                       # all configured accounts
uv run positions/run_tracker.py --brokerage schwab    # one brokerage only
uv run positions/run_tracker.py --csv input/OTHER.csv # override the CSV path
```

Reads `positions/config.toml` (per-account Google Sheet IDs + CSV
paths). Supported brokerages: **Schwab, Robinhood, Fidelity, Merrill
Edge** — set `brokerage` in config to match the export. CSV parsers
come from the `stocks-shared` package (`shared/stocks_shared/parsers/`).

## Credentials & auth

Google Sheets OAuth client at `~/.config/google-sheets-oauth.json`
(setup steps in `../google-sheets-setup/`). The first run opens a
browser to authorize; subsequent runs are silent.

## Behavior notes

- The script deletes and recreates each ticker tab on every run; the
  Summary tabs are preserved.
- Multiple accounts run **serially**, not in parallel — the Google
  Sheets API quota and Yahoo's rate limit are per-project / per-IP, so
  serial avoids 429s. Prices and option chains are cached in memory
  across accounts, so each ticker is fetched once per run.
- Option market values use the Yahoo `(bid + ask) / 2` midpoint.

## Brokerage CSV input

Place exports in the repo-root `input/` directory (gitignored). Config
CSV paths resolve relative to the repo root. For a hand-written manual
format (when you lack a supported export), see
[../docs/stockpile-format.md](../docs/stockpile-format.md).
