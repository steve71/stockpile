"""Fidelity CSV parser."""

import re
import csv
from collections import defaultdict

# Matches Fidelity OCC-compact option symbols: -OXY281215C65, -MOH241220P280
# Groups: (ticker, YY, MM, DD, C/P, strike)
_OPT_SYM_RE = re.compile(r"^-([A-Z]+\d*)(\d{2})(\d{2})(\d{2})([CP])([\d.]+)$")

_TICKER_RE = re.compile(r"^[A-Z]{1,6}(\.[A-Z]{1,2})?$")


def parse_dollar(s):
    if not s:
        return None
    s = re.sub(r"[$,\s]", "", s)
    try:
        return float(s)
    except ValueError:
        return None


def _parse_option_symbol(symbol):
    """Parse a Fidelity OCC-compact option symbol.

    '-OXY281215C65' → ('OXY', '12/15/2028', 65.0, 'Call', 'OXY 12/15/2028 65.00 C')
    Returns (ticker, expiration, strike, opt_type, schwab_symbol) or None.
    """
    m = _OPT_SYM_RE.match(symbol)
    if not m:
        return None
    ticker, yy, mm, dd, cp, strike_s = m.groups()
    expiration = f"{mm}/{dd}/20{yy}"
    strike = float(strike_s)
    opt_type = "Call" if cp == "C" else "Put"
    schwab_symbol = f"{ticker} {expiration} {strike:.2f} {cp}"
    return ticker, expiration, strike, opt_type, schwab_symbol


def _map_action(action_text):
    """Map Fidelity long action text to internal action name."""
    a = action_text.upper()
    if "DIVIDEND RECEIVED" in a:
        return "Dividend"
    if "EXPIRED" in a:
        return "Expired"
    if "ASSIGNED" in a:
        return "Assigned"
    if "OPENING TRANSACTION" in a:
        return "Sell to Open" if "YOU SOLD" in a else "Buy to Open"
    if "CLOSING TRANSACTION" in a:
        return "Buy to Close" if "YOU BOUGHT" in a else "Sell to Close"
    if "YOU BOUGHT" in a:
        return "Buy"
    if "YOU SOLD" in a:
        return "Sell"
    return action_text


def _parse_rows_to_transactions(rows):
    """Convert Fidelity CSV rows to internal 11-element transaction lists."""
    transactions = []
    for row in rows:
        date_str = row.get("Run Date", "").strip()
        action_text = row.get("Action", "").strip()
        symbol = row.get("Symbol", "").strip()
        qty_s = row.get("Quantity", "").strip()
        price_s = row.get("Price ($)", "").strip()
        commission_s = row.get("Commission ($)", "").strip()
        fees_s = row.get("Fees ($)", "").strip()
        amount_s = row.get("Amount ($)", "").strip()

        if not date_str or not action_text:
            continue

        action = _map_action(action_text)
        price = parse_dollar(price_s)
        amount = parse_dollar(amount_s)
        commission = parse_dollar(commission_s)
        fees_val = parse_dollar(fees_s)
        if commission is None and fees_val is None:
            fees = ""
        else:
            fees = (commission or 0.0) + (fees_val or 0.0)

        if action == "Dividend":
            transactions.append([
                date_str, action, "Dividend", symbol,
                "", "", "", "", "",
                "" if amount is None else amount,
                "",
            ])
            continue

        if symbol.startswith("-"):
            parsed = _parse_option_symbol(symbol)
            if not parsed:
                continue
            ticker, expiration, strike, opt_type, schwab_symbol = parsed
            qty_raw = qty_s.replace(",", "")
            qty = abs(float(qty_raw)) if qty_raw and re.search(r"\d", qty_raw) else ""
            transactions.append([
                date_str, action, opt_type, schwab_symbol,
                strike, expiration, qty,
                "" if price is None else price,
                fees,
                "" if amount is None else amount,
                "",
            ])
            continue

        # Stock buy/sell
        qty_raw = qty_s.replace(",", "")
        qty = abs(float(qty_raw)) if qty_raw and re.search(r"\d", qty_raw) else ""
        transactions.append([
            date_str, action, "Stock", symbol,
            "", "", qty,
            "" if price is None else price,
            fees,
            "" if amount is None else amount,
            "",
        ])

    transactions.sort(key=lambda r: (r[0][6:], r[0][:2], r[0][3:5]))
    return transactions


def parse_all_transactions(filepath):
    """Parse a Fidelity all-transactions CSV.

    Returns (ticker_transactions, other_rows):
    - ticker_transactions: dict {ticker: [transaction rows]}
    - other_rows: list of raw row dicts that don't belong to any position
    """
    with open(filepath, newline="", encoding="utf-8-sig") as f:
        raw_text = f.read()

    # Fidelity prepends blank lines before the column header row
    lines = raw_text.splitlines()
    header_idx = next(
        (i for i, ln in enumerate(lines) if ln.strip().startswith("Run Date")),
        None,
    )
    if header_idx is None:
        raise ValueError("Fidelity CSV header row ('Run Date,...') not found")

    csv_text = "\n".join(lines[header_idx:])
    raw_rows = []
    for row in csv.DictReader(csv_text.splitlines()):
        cleaned = {k.strip(): (v or "").strip() for k, v in row.items() if k and k.strip()}
        raw_rows.append(cleaned)

    # Pass 1: collect tickers that have real positions (stocks or options)
    position_tickers = set()
    for row in raw_rows:
        symbol = row.get("Symbol", "")
        action_text = row.get("Action", "")
        if not symbol or not action_text:
            continue
        action = _map_action(action_text)
        if symbol.startswith("-"):
            parsed = _parse_option_symbol(symbol)
            if parsed:
                position_tickers.add(parsed[0])
        elif action in ("Buy", "Sell") and _TICKER_RE.match(symbol):
            position_tickers.add(symbol)

    # Pass 2: assign each row to a ticker bucket or other_rows
    ticker_raw = defaultdict(list)
    other_rows = []
    for row in raw_rows:
        symbol = row.get("Symbol", "")
        action_text = row.get("Action", "")
        if not symbol or not action_text:
            continue
        action = _map_action(action_text)

        if symbol.startswith("-"):
            parsed = _parse_option_symbol(symbol)
            if parsed:
                ticker_raw[parsed[0]].append(row)
            else:
                other_rows.append(row)
        elif action == "Dividend" and symbol in position_tickers:
            ticker_raw[symbol].append(row)
        elif action in ("Buy", "Sell") and _TICKER_RE.match(symbol):
            ticker_raw[symbol].append(row)
        else:
            other_rows.append(row)

    ticker_transactions = {
        t: _parse_rows_to_transactions(rows)
        for t, rows in ticker_raw.items()
    }
    return ticker_transactions, other_rows
