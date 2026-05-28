"""Robinhood CSV parser."""

import re
import csv
from collections import defaultdict

# Trans codes treated as position-forming (options)
_OPTION_CODES = {"STO", "BTC", "OEXP", "OASGN"}
# Trans codes treated as position-forming (stocks)
_STOCK_CODES = {"Buy", "Sell"}

# Matches option descriptions in two forms:
#   "MOH 1/15/2027 Call $200.00"
#   "Option Expiration for PYPL 3/20/2026 Call $95.00"
_OPT_DESC_RE = re.compile(
    r"(?:Option Expiration for\s+)?"
    r"([A-Z]+\d*)"                    # ticker (may have adjustment digit, e.g. RKT1)
    r"\s+(\d{1,2}/\d{1,2}/\d{4})"    # date M/D/YYYY
    r"\s+(Call|Put)"
    r"\s+\$?([\d.]+)"                 # strike
)


def parse_dollar(s):
    """Parse Robinhood dollar strings: '$1,234.56' and '($1,234.56)' → float."""
    if not s:
        return None
    s = s.strip()
    negative = s.startswith("(") and s.endswith(")")
    cleaned = re.sub(r"[$()\s,]", "", s)
    try:
        val = float(cleaned)
        return -val if negative else val
    except ValueError:
        return None


def _norm_date(d):
    """M/D/YYYY or MM/D/YYYY → MM/DD/YYYY."""
    parts = d.split("/")
    return f"{int(parts[0]):02d}/{int(parts[1]):02d}/{parts[2]}"


def parse_date(raw):
    """Extract and normalize a date from a Robinhood Activity Date field."""
    m = re.search(r"(\d{1,2}/\d{1,2}/\d{4})", raw)
    return _norm_date(m.group(1)) if m else raw.strip()


def _parse_opt_description(desc):
    """Parse option info from a description field.

    Returns (ticker, expiration_MM_DD_YYYY, opt_type, strike_float) or None.
    """
    desc = " ".join(desc.splitlines())  # flatten multiline descriptions
    m = _OPT_DESC_RE.search(desc)
    if not m:
        return None
    return (
        m.group(1),
        _norm_date(m.group(2)),
        m.group(3),           # "Call" or "Put"
        float(m.group(4)),
    )


def _parse_qty(raw):
    """Parse quantity, stripping S suffix (short-position marker in ACATI rows)."""
    if not raw or not re.search(r"\d", raw):
        return ""
    return abs(float(re.sub(r"[^\d.]", "", raw)))


def _build_opt_symbol(ticker, expiration, strike, opt_type):
    """Build a Schwab-style option symbol: 'MOH 01/15/2027 200.00 C'."""
    c_or_p = "C" if opt_type == "Call" else "P"
    return f"{ticker} {expiration} {strike:.2f} {c_or_p}"


def _parse_rows_to_transactions(rows):
    """Convert raw Robinhood CSV DictReader rows to internal transaction list format.

    Each transaction is a list of 11 elements matching the Schwab parser output:
    [date, action, opt_type, symbol, strike, expiration, qty, price, fees, amount, ""]
    """
    transactions = []
    for row in rows:
        code = (row.get("Trans Code") or "").strip()
        raw_date = (row.get("Activity Date") or "").strip()
        instrument = (row.get("Instrument") or "").strip()
        description = (row.get("Description") or "").strip()
        qty_s = (row.get("Quantity") or "").strip()
        price_s = (row.get("Price") or "").strip()
        amount_s = (row.get("Amount") or "").strip()

        if not code or not raw_date or not re.search(r"\d{1,2}/\d{1,2}/\d{4}", raw_date):
            continue

        date_str = parse_date(raw_date)
        price = parse_dollar(price_s)
        amount = parse_dollar(amount_s)

        # ── Dividends ────────────────────────────────────────────────────────
        if code == "CDIV":
            transactions.append([
                date_str, "Dividend", "Dividend", instrument,
                "", "", "", "", "",
                "" if amount is None else amount,
                "",
            ])
            continue

        # ── Stock buys / sells ───────────────────────────────────────────────
        if code in _STOCK_CODES:
            qty = _parse_qty(qty_s)
            transactions.append([
                date_str, code, "Stock", instrument,
                "", "", qty,
                "" if price is None else price,
                "",
                "" if amount is None else amount,
                "",
            ])
            continue

        # ── Option transactions ───────────────────────────────────────────────
        if code in _OPTION_CODES:
            parsed = _parse_opt_description(description)
            if not parsed:
                continue
            ticker, expiration, opt_type, strike = parsed
            symbol = _build_opt_symbol(ticker, expiration, strike, opt_type)
            qty = _parse_qty(qty_s)

            action_map = {
                "STO": "Sell to Open",
                "BTC": "Buy to Close",
                "OEXP": "Expired",
                "OASGN": "Assigned",
            }
            transactions.append([
                date_str, action_map[code], opt_type, symbol,
                strike, expiration, qty,
                "" if price is None else price,
                "",
                "" if amount is None else amount,
                "",
            ])
            continue

        # ── ACATI: transfer-in from another broker ────────────────────────────
        # Stock ACATI: establish position with no cost basis (price/amount = 0).
        # Option ACATI with "S" suffix: short position transferred in → Sell to Open.
        if code == "ACATI" and instrument and re.search(r"\d", qty_s):
            is_short = qty_s.strip().upper().endswith("S")
            qty = _parse_qty(qty_s)
            parsed = _parse_opt_description(description)
            if parsed:
                ticker, expiration, opt_type, strike = parsed
                symbol = _build_opt_symbol(ticker, expiration, strike, opt_type)
                action = "Sell to Open" if is_short else "Buy to Open"
                transactions.append([
                    date_str, action, opt_type, symbol,
                    strike, expiration, qty,
                    "", "", "", "",
                ])
            else:
                # Stock transfer-in — no cost basis available
                transactions.append([
                    date_str, "Buy", "Stock", instrument,
                    "", "", qty, "", "", "", "",
                ])

    transactions.sort(key=lambda r: (r[0][6:], r[0][:2], r[0][3:5]))
    return transactions


def parse_all_transactions(filepath):
    """Parse a Robinhood all-transactions CSV.

    Returns (ticker_transactions, other_rows):
    - ticker_transactions: dict {ticker: [transaction rows]}
    - other_rows: list of raw CSV dicts that don't belong to any position
    """
    raw_rows = []
    with open(filepath, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            raw_rows.append(row)

    # First pass: identify tickers that have real positions (buys/sells/options).
    position_tickers = set()
    for row in raw_rows:
        code = (row.get("Trans Code") or "").strip()
        instrument = (row.get("Instrument") or "").strip()
        raw_date = (row.get("Activity Date") or "").strip()
        if not instrument or not re.search(r"\d{1,2}/\d{1,2}/\d{4}", raw_date):
            continue
        if code in _OPTION_CODES or code in _STOCK_CODES:
            position_tickers.add(instrument)
        elif code == "ACATI" and re.search(r"\d", row.get("Quantity") or ""):
            position_tickers.add(instrument)

    # Second pass: assign rows to tickers or other_rows.
    ticker_raw = defaultdict(list)
    other_rows = []
    for row in raw_rows:
        code = (row.get("Trans Code") or "").strip()
        instrument = (row.get("Instrument") or "").strip()
        raw_date = (row.get("Activity Date") or "").strip()
        if not re.search(r"\d{1,2}/\d{1,2}/\d{4}", raw_date):
            continue

        if (code in _OPTION_CODES or code in _STOCK_CODES) and instrument:
            ticker_raw[instrument].append(row)
        elif code == "CDIV" and instrument in position_tickers:
            ticker_raw[instrument].append(row)
        elif code == "ACATI" and instrument in position_tickers:
            ticker_raw[instrument].append(row)
        elif code or instrument:
            other_rows.append(row)

    ticker_transactions = {
        t: _parse_rows_to_transactions(rows)
        for t, rows in ticker_raw.items()
    }
    return ticker_transactions, other_rows
