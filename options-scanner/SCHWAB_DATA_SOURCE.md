# Schwab Data Source Integration

## Overview

The options scanner supports two data sources:

- **Yahoo Finance** (default) — no setup required, uses `yfinance`
- **Schwab** — real-time quotes, actual Greeks, full chain coverage;
  requires a Schwab account and a free Schwab developer API account

## Schwab referral program

https://www.schwab.com/refer-a-friend

Here's my referral code:
https://www.schwab.com/client-referral?refrid=REFERMJRE3UMB

If you don't have a Schwab brokerage account yet, you may be able to
earn a cash bonus by opening one through a referral link from an
existing Schwab customer.  Sadly I won't get anything for referring
you, but you may.  It depends on the amount you fund and type of account.

## How to configure Schwab

### 1. Get API credentials

Register at [developer.schwab.com](https://developer.schwab.com).
- follow the steps, it required an approval which took a couple of hours
  before I could create app (next step)

Create an app and note your **App Key** and **App Secret**.
Set the callback URL to `https://127.0.0.1:8182/`.
** MAKE SURE TO INCLUDE THE ENDING / to the above URL!!
- simple, just filling in some descriptive fields.
- after creating this app it also took a few hours before app
  was ready to use.

**When creating the app, request only the permissions this tool
actually needs: read-only market data and option chain access.
Do not grant trading or account management permissions — this
tool never places orders or reads account balances.**

> **Keep your App Key and App Secret private.** Anyone who has
> them can make API calls on your behalf. Never commit them to
> git, share them publicly, or store them in any file inside the
> repo directory. The `config.toml` file is gitignored for this
> reason — double-check with `git status` if you are ever unsure.

### 2. Create config.toml

```bash
cp options-scanner/config.toml.example options-scanner/config.toml
```

Edit `config.toml` and fill in your credentials:

```toml
[data_source]
provider = "schwab"

[schwab]
app_key      = "your-app-key"

app_secret   = "your-app-secret"

callback_url = "https://127.0.0.1:8182/"
token_file   = "~/.config/schwab-token.json"
```

### 3. Authenticate (initial setup, then re-run every 7 days)

```bash
uv run options-scanner/schwab_auth.py
```
- This won't work until app is ready.
- You may get key and secret before app is ready to be used.

This opens a browser, logs you in to Schwab, and saves an OAuth token.
- this will ask you to login
- it wants you to login to your schwab account, not the new developer acct.
- You will get an SSL warning since you're using a self-signed cert locally.
- You'll have to press the advanced button to continue

**You must re-run this command every 7 days.** Schwab issues two
tokens during OAuth: a short-lived **access token** (30 minutes) and
a longer-lived **refresh token** (7 days). The scanner refreshes the
access token automatically on every request, but the refresh token
itself has a **fixed 7-day TTL from the initial OAuth login** —
using it does *not* extend it. Once the 7 days are up, the next
scan fails silently and surfaces as:

```
Could not fetch live price for AAPL from Schwab
```

The fix is just to re-run `schwab_auth.py` (which wipes the old token
file and walks you through the login again). The scanner and the trading
dashboard pick up the refreshed token automatically on the next request —
no server restart needed.

### Headless / remote host (no browser)

On a remote or cloud host where `schwab_auth.py` can't open a browser,
use the manual flow:

```bash
uv run options-scanner/schwab_auth.py --manual
```

1. It prints a **login URL**. Open it in a browser on any machine and log
   in to your Schwab **brokerage** account (not the developer account),
   then approve access.
2. Your browser redirects to your callback URL
   (`https://127.0.0.1:8182/?code=…`) and shows a **connection error** —
   that's expected, since nothing is listening there.
3. Copy the **entire** URL from the address bar (it contains
   `?code=…&session=…`) and paste it at the `Redirect URL (hidden)>`
   prompt, then press Enter.

The paste is **hidden** (read with `getpass`), so the one-time code never
appears on screen or in a recording — you're pasting blind, which is
normal. The script then prints a leak-free confirmation (the URL's length
and whether it starts with your callback URL) so you know it registered.

Notes:
- Run it in a real console — **PowerShell or cmd on Windows, not Git Bash
  / mintty** — otherwise `getpass` can't hide the input.
- It removes the existing token first, so finish the login (or just
  re-run if you abort).
- Verify it worked by selecting Schwab as the data source and scanning a
  ticker, or by checking that the token file was freshly written.

**Caution:** a saved Schwab token grants access to your brokerage account
data. On a shared or cloud host, protect it accordingly — and prefer
running locally when you can. `schwab_auth.py` chmods both `config.toml`
and the token file to `0600` (owner-only) on POSIX hosts; on Windows that
is effectively a no-op (ACL-based). Keep the app's permissions read-only
(step 1) so the token can't place trades even if it leaks.

### What's stored, and where to secure it

Two files hold secrets, and they live **together on whichever single host
runs the scanner or dashboard**:

- `config.toml` — your **app key + app secret**
- the token file (`~/.config/schwab-token.json`) — the OAuth tokens

The app secret has to sit on that host because it's used to refresh the
30-minute access token on every request — so copying *only* the token to
another machine won't work (it would stop after the first refresh). Your
**browser is just a thin client**; it holds no secrets.

- **Running locally** (most setups): both files are on your machine —
  secure them there. The browser talks to `localhost`, nothing else to
  protect.
- **Running on a remote/cloud host** (the `--manual` case): the app key,
  app secret, and token **all** live on that host — secure them there.
  Your laptop only runs a browser for the login and stores nothing
  persistent.

## Usage

### CLI

```bash
# Use Schwab (reads from config.toml)
uv run options-scanner/run_scanner.py AMD --calls

# Override to Yahoo for one run
uv run options-scanner/run_scanner.py AMD --calls --data-source yahoo

# Override to Schwab for one run (without changing config.toml)
uv run options-scanner/run_scanner.py AMD --calls --data-source schwab
```

### Portfolio CLI

```bash
uv run options-scanner/run_portfolio.py --csv input/schwab028.csv
uv run options-scanner/run_portfolio.py --csv input/schwab028.csv \
    --data-source schwab
```

### Web UI

Open the sidebar (>> arrow) and select **Data source** from the
dropdown. The default is read from `config.toml`.

## What changes with Schwab

| Feature | Yahoo Finance | Schwab |
|---------|--------------|--------|
| Option chain data | Delayed/stale | Real-time |
| Bid / Ask | Last market refresh | Live NBBO |
| IV | Stale (hours old) | Current |
| Delta | Black-Scholes from stale IV | Real Greek |
| Earnings dates | Yahoo Finance | Yahoo Finance |

Earnings dates always come from Yahoo Finance — the Schwab API does
not provide this data. Everything else (chain, prices, roll close cost)
uses the selected provider.

## Architecture

```
chain.py:fetch_chain(provider="yahoo"|"schwab")
  ├── provider="yahoo"  → _fetch_chain_yahoo()   (existing yfinance code)
  └── provider="schwab" → schwab_chain.fetch_chain_schwab()

Roll close cost lookup:
  ├── provider="yahoo"  → stocks_shared.yahoo.fetch_option_chain()
  └── provider="schwab" → stocks_shared.schwab_live.fetch_option_chain_schwab()

Earnings (always Yahoo):
  └── earnings.fetch_earnings_dates()
```
