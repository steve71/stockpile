# Dashboard — SPEC

A standalone Streamlit app that serves as the entry point for all
stockpile tools, plus an AI agent tab that lets users make natural-
language requests to the options scanner.

Runs independently of the options-scanner Streamlit app (separate
process, separate port).

---

## 1. Dashboard App

### Entry point

```
uv run streamlit run dashboard/run_app.py
```

### Layout

Single-page app with a sidebar for navigation and a main content
area. Navigation items:

| Item | Description |
|------|-------------|
| Home | Tool cards (see below) |
| Scanner Agent | Natural-language options scanner |

### Home — Tool Cards

Four cards, each with a short description and one or more action
buttons.

**Options Scanner**
Opens the full scanner web UI. Button launches
`streamlit run options-scanner/run_app.py` in a subprocess (if not
already running) and navigates the browser to its port.

**Positions Tracker**
Runs the Google Sheets tracker for all configured accounts. Button
triggers `positions/run_tracker.py` and streams its log output into
an `st.expander` so the user can see progress without leaving the
dashboard.

**Cost Basis Charts**
Generates cost-basis-vs-price charts. Optional symbol filter.
Button runs `cost-basis-charts/run_charts.py`, then renders the
output HTMLs inline via `st.components.v1.html` or links to them.

**Portfolio Scan**
Runs a full portfolio options scan from a brokerage CSV. User
drags in a CSV (or picks from `input/`), clicks Scan, output
streams into the page.

---

## 2. Scanner Agent

### Overview

A Claude-powered chat interface that accepts natural-language
requests about options and fulfills them by calling the options
scanner CLI. Lives in the **Scanner Agent** navigation item.

The agent uses the Claude API (tool use) with a single primary
tool: `run_scanner`. The CLI's `--agent` flag (which implies
`--json --quiet`) is the stable contract between the agent and
the scanner.

### Conversation flow

1. User sends a free-text request.
2. Agent identifies what it has and what it still needs:
   - Ticker(s) — required, will ask if missing
   - Direction — calls, puts, or both (default: both)
   - Mode — sell (default) or buy
   - Data source — yahoo (default) or schwab
   - Filter overrides — top N, DTE range, min OI/vol, min delta,
     max delta, min IV+pp (all optional; defaults used if omitted)
3. If anything required is missing, agent asks a focused follow-up
   question (one question at a time).
4. Once it has enough, agent calls `run_scanner` and formats the
   JSON response into a readable reply with a table of candidates.
5. User can ask follow-up questions ("narrow it to 30–60 DTE",
   "show me puts instead", "what about MSFT?") and the agent
   re-runs or refines.

### Example exchanges

> "Show me the best 3 covered calls for ADBE"
→ Runs `run_scanner ADBE --calls --top 3 --agent`, returns table.

> "Find IV-cheap LEAPS to buy on NVDA, at least 180 DTE"
→ Runs `run_scanner NVDA --buy --min-dte 180 --agent`.

> "Scan AAPL and MSFT for put-selling candidates with delta
>  under 0.30 and only strong signals"
→ Runs `run_scanner AAPL MSFT --puts --max-delta 0.30
>  --min-ivpp 5 --agent`.

> "Same thing but use Schwab data"
→ Re-runs previous command with `--data-source schwab`.

### Tool definition

```
run_scanner(
  tickers:     list[str],       # one or more tickers
  mode:        "calls"|"puts"|"both",
  buy:         bool,            # false = sell candidates (default)
  top:         int,             # default 10
  min_dte:     int | None,
  max_dte:     int | None,
  min_oi:      int | None,
  min_vol:     int | None,
  min_delta:   float | None,
  max_delta:   float | None,
  min_ivpp:    float | None,
  data_source: "yahoo"|"schwab"|None,
  roll:        bool,
  roll_type:   "call"|"put"|None,
  roll_strike: float | None,
  roll_exp:    str | None,      # YYYY-MM-DD
) → dict                        # parsed JSON from CLI --agent output
```

Implementation shells out to `run_scanner.py` with `--agent`,
captures stdout, parses JSON. Stderr (suppressed by `--quiet`) is
discarded. Non-zero exit code surfaces as an error message in chat.

### File layout

```
dashboard/
  SPEC.md            ← this file
  run_app.py         ← streamlit entry point
  home.py            ← tool cards page
  agent/
    __init__.py
    chat.py          ← st.chat_input UI + message rendering
    runner.py        ← shells out to CLI, parses JSON
    tools.py         ← Claude tool definitions
    prompt.py        ← system prompt
```

---

## 3. Open Questions

- **Scanner port management** — if the options scanner is already
  running, the dashboard should link to it rather than launch a
  second instance. Need a lightweight port-check before launching.
- **Schwab auth in agent context** — if the user asks for Schwab
  data and the refresh token is expired, the agent needs to surface
  a clear error ("re-run `schwab_auth.py`") rather than a raw
  exception.
- **Streaming vs. one-shot** — should the agent stream Claude's
  reply token-by-token (better UX) or wait for the full response?
  Streamlit's `st.write_stream` supports streaming; worth doing
  from the start.
- **Multi-turn context** — how many prior turns to include in the
  Claude API call. Start simple (last 10 messages); tune if needed.
- **Portfolio scan agent** — out of scope for now; scanner agent
  only covers single-ticker and multi-ticker scans. Roll mode is
  in scope (maps directly to `--roll` flags).
