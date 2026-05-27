"""Merrill Edge CSV parser.

Handles the Merrill Edge all-transactions CSV export as well as the PDF-
converted CSV produced by tools/extract_merrill_pdf.py. Both share the
same column layout; only the encoding differs (utf-8-sig vs utf-8).

Merrill option symbol format: TICKER#MONTH_CODE DAY2 YEAR2 SIZE_CODE STRIKE6
  e.g. ETSY#C1927D750000 = ETSY Mar 19 2027 Call $75.00
  Call months: A=Jan … L=Dec
  Put  months: M=Jan … X=Dec
  Size code C → strike = value / 1000   (strike ≥ 100)
  Size code D → strike = value / 10000  (10 ≤ strike < 100)
  Size code E → strike = value / 100000 (strike < 10, e.g. after special-dividend adjustment)
"""

import re
import csv
from collections import defaultdict

_MERRILL_OPT_RE = re.compile(r"^([A-Z0-9]+)#([A-Z])(\d{2})(\d{2})([CDE])(\d+)$")
_CALL_MONTH = dict(zip("ABCDEFGHIJKL", range(1, 13)))
_PUT_MONTH  = dict(zip("MNOPQRSTUVWX", range(1, 13)))
_TICKER_RE  = re.compile(r"^[A-Z]{1,6}(\.[A-Z]{1,2})?$")

# Rows whose descriptions start with these prefixes carry no position data
# (money-market fund activity, ADR fees, DRIP bookkeeping, symbol changes).
_SKIP_DESC = (
    "Interest ",
    "Depository Bank",
    "Reinvestment Program",
    "Reinvestment Share",
    "Subscription ",
    "Redemption ",
    "Exchange ",
    "Dividend BLF",
)

# Money-market symbols to exclude entirely
_SKIP_SYMS = {"TFDXX", "IIAXX"}

_STOCK_ACTIONS = {"Purchase", "Sale", "Sale-Option Assigned"}
_OPT_ACTIONS   = {"Option Sale", "Option Purchase", "Option Expired", "Option Assigned"}


def parse_dollar(s):
    if not s:
        return None
    s = re.sub(r"[$,\s]", "", s)
    try:
        return float(s)
    except ValueError:
        return None


def _parse_option_symbol(sym):
    """ETSY#C1927D750000 → (ticker, expiration MM/DD/YYYY, strike, opt_type, schwab_symbol)
    Returns None for unrecognised / adjusted-strike symbols.
    """
    m = _MERRILL_OPT_RE.match(sym)
    if not m:
        return None
    ticker, mc, day_s, yr_s, size, strike_s = m.groups()

    if mc in _CALL_MONTH:
        mm, opt_type = _CALL_MONTH[mc], "Call"
    elif mc in _PUT_MONTH:
        mm, opt_type = _PUT_MONTH[mc], "Put"
    else:
        return None

    if size == "C":
        strike = int(strike_s) / 1000.0
    elif size == "D":
        strike = int(strike_s) / 10000.0
    else:  # E — sub-$10 strikes (e.g. after special-dividend adjustment)
        strike = int(strike_s) / 100000.0
    year = 2000 + int(yr_s)
    expiration = f"{mm:02d}/{int(day_s):02d}/{year}"
    cp = "C" if opt_type == "Call" else "P"
    schwab_symbol = f"{ticker} {expiration} {strike:.2f} {cp}"
    return ticker, expiration, strike, opt_type, schwab_symbol


def _map_action(desc, signed_qty):
    """Return internal action name from description text and raw signed quantity."""
    if desc.startswith("Option Sale"):
        return "Sell to Open" if signed_qty <= 0 else "Sell to Close"
    if desc.startswith("Option Purchase"):
        return "Buy to Close" if signed_qty >= 0 else "Buy to Open"
    if desc.startswith("Option Expired"):
        return "Expired"
    if desc.startswith("Option Assigned"):
        return "Assigned"
    # Pending transactions use "Buy CALL/PUT ..." and "Sell CALL/PUT ..." instead
    # of "Option Purchase ..." / "Option Sale ..." before settlement clears.
    if desc.startswith("Buy ") and ("CALL" in desc or "PUT" in desc):
        return "Buy to Close" if signed_qty >= 0 else "Buy to Open"
    if desc.startswith("Sell ") and ("CALL" in desc or "PUT" in desc):
        return "Sell to Open" if signed_qty <= 0 else "Sell to Close"
    if desc.startswith("Purchase"):
        return "Buy"
    if desc.startswith("Sale"):      # covers "Sale" and "Sale-Option Assigned"
        return "Sell"
    if desc.startswith("Dividend") or desc.startswith("Foreign Dividend"):
        return "Dividend"
    return None


def _build_strike_remap(rows):
    """Return {new_schwab_sym: old_schwab_sym} from Exchange strike-adjustment pairs.

    When a company pays a special dividend the OCC adjusts outstanding option
    strikes.  Merrill records this as two Exchange rows on the same date:
      - qty < 0, "STRIKE ADJUSTMENT" in desc: the new adjusted symbol
      - qty > 0, "SYMBOL CHG NEW SYM" in desc: the old symbol, but with
        year=99 (e.g. 2099) as a Merrill placeholder

    We match each pair by option type and expiration month/day, then remap the
    new schwab_sym to the original so position tracking stays coherent.
    """
    by_date = defaultdict(list)
    for row in rows:
        desc = row.get("Description", "").strip()
        if not desc.startswith("Exchange "):
            continue
        sym = row.get("Symbol/ CUSIP", "").strip()
        qty_s = row.get("Quantity", "").strip().replace(",", "")
        try:
            signed_qty = int(float(qty_s)) if qty_s else 0
        except ValueError:
            signed_qty = 0
        parsed = _parse_option_symbol(sym)
        if not parsed:
            continue
        ticker, expiration, strike, opt_type, schwab_sym = parsed
        by_date[row.get("Trade Date", "").strip()].append({
            "ticker": ticker,
            "schwab_sym": schwab_sym,
            "expiration": expiration,
            "strike": strike,
            "opt_type": opt_type,
            "signed_qty": signed_qty,
            "desc": desc,
        })

    remap = {}
    for ex_rows in by_date.values():
        adjustments = [r for r in ex_rows if r["signed_qty"] < 0 and "STRIKE ADJUSTMENT" in r["desc"]]
        old_syms    = [r for r in ex_rows if r["signed_qty"] > 0 and "SYMBOL CHG"        in r["desc"]]
        for new in adjustments:
            mm_dd  = new["expiration"][:5]   # MM/DD
            year   = new["expiration"][6:]   # YYYY (real year)
            cp     = "C" if new["opt_type"] == "Call" else "P"
            for old in old_syms:
                if old["opt_type"] != new["opt_type"]:
                    continue
                if old["expiration"][:5] != mm_dd:
                    continue
                old_exp    = f"{mm_dd}/{year}"
                old_schwab = f"{new['ticker']} {old_exp} {old['strike']:.2f} {cp}"
                remap[new["schwab_sym"]] = old_schwab
    return remap


_SYM_RE = re.compile(r'^(\w+)\s+(\d{2}/\d{2}/\d{4})\s+([\d.]+)\s+([CP])$')


def _resolve_orphaned_closes(transactions, rows):
    """Fix closes that have no matching open, which fall into two cases:

    Case 1 — missing Exchange rows: the open and close share the same
    ticker/expiration/type but different strikes (special dividend changed the
    strike after the Exchange adjustment rows were not recorded).  We remap the
    close symbol to the open symbol.

    Case 2 — bare-ticker open: the Sell/Buy to Open was recorded with a bare
    ticker symbol (no # encoding) so it wasn't parsed as an option.  We
    synthesize the missing open from the raw row, using the close's symbol.
    """
    net = defaultdict(int)
    for t in transactions:
        _, action, opt_type, sym, _, _, qty, *_ = t
        if opt_type in ("Stock", "Dividend"):
            continue
        q = int(qty) if qty != "" else 1
        if action in ("Sell to Open", "Buy to Open"):
            net[sym] += q
        elif action in ("Buy to Close", "Sell to Close", "Expired", "Assigned"):
            net[sym] -= q

    orphaned  = {s for s, n in net.items() if n < 0}
    unmatched = {s for s, n in net.items() if n > 0}

    remap = {}
    synth = []

    for close_sym in orphaned:
        m = _SYM_RE.match(close_sym)
        if not m:
            continue
        c_ticker, c_exp, c_strike_s, c_cp = m.groups()
        c_strike = float(c_strike_s)
        c_type   = "Call" if c_cp == "C" else "Put"

        # Case 1: unmatched open, same ticker/expiration/type, adjacent strike
        candidates = [
            s for s in unmatched
            if (om := _SYM_RE.match(s)) and
               om.group(1) == c_ticker and
               om.group(2) == c_exp and
               om.group(4) == c_cp and
               abs(float(om.group(3)) - c_strike) < 1.0
        ]
        if len(candidates) == 1:
            remap[close_sym] = candidates[0]
            continue

        # Case 2: bare-ticker option row that was skipped during parsing
        for raw in rows:
            desc = raw.get("Description", "").strip()
            sym  = raw.get("Symbol/ CUSIP", "").strip()
            if "#" in sym or not desc.startswith("Option"):
                continue
            if sym != c_ticker:
                continue
            if (c_cp == "C") != ("CALL" in desc.upper()):
                continue
            nums = re.findall(r'\b(\d+\.\d+)', desc)
            if not nums or abs(float(nums[-1]) - c_strike) > 0.01:
                continue
            date_str = raw.get("Trade Date", "").strip()
            qty_s    = raw.get("Quantity", "").strip().replace(",", "")
            amount_s = raw.get("Amount", "").strip()
            try:
                signed_qty = int(float(qty_s)) if qty_s else 0
            except ValueError:
                signed_qty = 0
            action = _map_action(desc, signed_qty)
            amount = parse_dollar(amount_s)
            if action in ("Sell to Open", "Buy to Open"):
                synth.append([
                    date_str, action, c_type, close_sym,
                    c_strike, c_exp, abs(signed_qty),
                    "", "",
                    "" if amount is None else amount,
                    "",
                ])
            break

    if not remap and not synth:
        return transactions

    fixed = []
    for t in transactions:
        row = list(t)
        row[3] = remap.get(row[3], row[3])
        fixed.append(row)
    fixed.extend(synth)
    return fixed


def _parse_rows_to_transactions(rows):
    """Convert a list of cleaned Merrill row dicts to 11-element transaction lists."""
    remap = _build_strike_remap(rows)
    transactions = []
    for row in rows:
        date_str = row.get("Trade Date", "").strip()
        desc     = row.get("Description", "").strip()
        sym      = row.get("Symbol/ CUSIP", "").strip()
        qty_s    = row.get("Quantity", "").strip().replace(",", "")
        price_s  = row.get("Price", "").strip()
        amount_s = row.get("Amount", "").strip()

        if not date_str or not desc:
            continue
        if any(desc.startswith(p) for p in _SKIP_DESC):
            continue
        if sym in _SKIP_SYMS:
            continue

        try:
            signed_qty = int(float(qty_s)) if qty_s and re.search(r"\d", qty_s) else 0
        except ValueError:
            signed_qty = 0

        action = _map_action(desc, signed_qty)
        if action is None:
            continue

        price  = parse_dollar(price_s)
        amount = parse_dollar(amount_s)
        qty    = abs(signed_qty) if signed_qty else ""

        if "#" in sym:
            parsed = _parse_option_symbol(sym)
            if not parsed:
                continue
            ticker, expiration, strike, opt_type, schwab_sym = parsed
            schwab_sym = remap.get(schwab_sym, schwab_sym)
            transactions.append([
                date_str, action, opt_type, schwab_sym,
                strike, expiration, qty,
                "" if price is None else price,
                "",
                "" if amount is None else amount,
                "",
            ])
            # Merrill omits the stock purchase row for put assignments.
            # Synthesize it so share counts and cost basis are correct.
            if action == "Assigned" and opt_type == "Put" and qty != "":
                shares = int(qty) * 100
                buy_amount = -(shares * strike)
                transactions.append([
                    date_str, "Buy", "Stock", ticker,
                    "", "", shares, strike, "", buy_amount, "",
                ])
        elif desc.startswith("Option"):
            # Bare-ticker option row (no # symbol) — skip here; the post-pass
            # _resolve_orphaned_closes will synthesize the open from this raw row.
            continue
        elif action == "Dividend":
            transactions.append([
                date_str, action, "Dividend", sym,
                "", "", "", "", "",
                "" if amount is None else amount,
                "",
            ])
        else:
            transactions.append([
                date_str, action, "Stock", sym,
                "", "", qty,
                "" if price is None else price,
                "",
                "" if amount is None else amount,
                "",
            ])

    transactions = _resolve_orphaned_closes(transactions, rows)
    transactions.sort(key=lambda r: (r[0][6:], r[0][:2], r[0][3:5]))
    return transactions


def parse_all_transactions(filepath):
    """Parse a Merrill Edge all-transactions CSV.

    Returns (ticker_transactions, other_rows):
    - ticker_transactions: dict {ticker: [transaction rows]}
    - other_rows: list of raw row dicts that don't belong to any position
    """
    raw_rows = []
    with open(filepath, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            cleaned = {
                k.strip(): (v or "").strip()
                for k, v in row.items()
                if k and k.strip()
            }
            if any(cleaned.values()):
                raw_rows.append(cleaned)

    # Pass 1: collect tickers that have real stock / option positions
    position_tickers = set()
    for row in raw_rows:
        desc = row.get("Description", "")
        sym  = row.get("Symbol/ CUSIP", "")
        if not sym or not desc:
            continue
        if "#" in sym:
            parsed = _parse_option_symbol(sym)
            if parsed:
                position_tickers.add(parsed[0])
        elif any(desc.startswith(a) for a in _STOCK_ACTIONS) and _TICKER_RE.match(sym):
            position_tickers.add(sym)

    # Pass 2: assign rows to tickers or other_rows
    ticker_raw = defaultdict(list)
    other_rows = []
    for row in raw_rows:
        desc = row.get("Description", "")
        sym  = row.get("Symbol/ CUSIP", "")
        if not desc:
            continue

        if sym in _SKIP_SYMS:
            continue

        if "#" in sym:
            parsed = _parse_option_symbol(sym)
            if parsed:
                ticker_raw[parsed[0]].append(row)
            else:
                other_rows.append(row)
        elif any(desc.startswith(a) for a in _STOCK_ACTIONS) and sym and _TICKER_RE.match(sym):
            ticker_raw[sym].append(row)
        elif desc.startswith("Option") and sym and _TICKER_RE.match(sym):
            # Bare-ticker option row (no # symbol) — route so _resolve_orphaned_closes can use it
            ticker_raw[sym].append(row)
        elif desc.startswith(("Dividend", "Foreign Dividend")) and sym in position_tickers:
            ticker_raw[sym].append(row)
        elif sym and sym not in _SKIP_SYMS:
            other_rows.append(row)

    ticker_transactions = {
        t: _parse_rows_to_transactions(rows)
        for t, rows in ticker_raw.items()
    }
    return ticker_transactions, other_rows
