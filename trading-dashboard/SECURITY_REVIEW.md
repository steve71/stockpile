# Security review — Trading Dashboard

Reviewed: 2026-05-31. Scope: the "Trading Dashboard" subproject (Flask
backend + vanilla-JS frontend serving public market data from Yahoo
Finance / Hyperliquid).

**Verdict: No HIGH or MEDIUM-confidence exploitable vulnerabilities
found.**

## What was checked and cleared

| Area | Finding |
|------|---------|
| `app.py` debug mode | `app.run(debug=False, …)` — debugger not exposed. ✅ |
| SSRF | No proxy / fetch-by-URL endpoint. `symbol` only flows into a path/query against fixed hosts (Yahoo, `api.hyperliquid.xyz`) — no host/protocol control. ✅ |
| Injection (Python) | No `eval`/`exec`/`pickle`/`yaml.load`/`subprocess`/`os.system`/`render_template_string`. `symbol` goes to `yf.Ticker()` and a JSON POST body, not a shell/SQL. ✅ |
| Secrets | None hardcoded. ✅ |
| DOM XSS | All `innerHTML` sinks in `indicators-render.js` interpolate numeric values (`.toFixed()`) or static strings. ✅ |

## Low-severity / informational — RESOLVED 2026-05-31

### 1. Unescaped symbol in `innerHTML` — self-XSS only ✅ fixed

The ticker chip and the pane error message previously interpolated
`ps.symbol` / `err.message` into `innerHTML`. These were only self-XSS
(no attacker delivery path; symbol is `.toUpperCase()`'d), but both are
now built with `document.createElement` + `textContent` in
`dashboard.js`, so no user input reaches `innerHTML`.

### 2. Wildcard CORS ✅ tightened

`CORS(app, …)` in `app.py` was `{"origins": "*"}`. The frontend is
served same-origin, so cross-origin access is not needed; origins are now
scoped to `http://localhost:5000` / `http://127.0.0.1:5000`.

## Dependency advisories (Dependabot) — RESOLVED 2026-05-31

- `Flask` bumped `3.1.0 -> 3.1.3` (session `Vary: Cookie` and fallback
  signing-key advisories).
- `flask-cors` bumped `5.0.0 -> 6.0.0` (improper regex path matching,
  case-sensitivity handling, inconsistent CORS matching).
- `requests` floor raised to `>=2.32.4` as general hygiene.

## Bottom line

Safe to merge. All review items and the Dependabot advisories have been
addressed.
