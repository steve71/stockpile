#!/usr/bin/env python3
"""
merge_csv_transactions.py

Collapse broker-split fills in every brokerage CSV under input/.
Rows that share the same key fields AND a non-empty Price are merged:
Quantity, Amount, and any fee columns are summed into one row.
Rows with a blank Price (dividends, expirations, etc.) are never merged.

Each file is backed up to input/<name>.bak before being changed.
Only files with at least one merge to perform are written.

Supported formats (auto-detected from header row):
  Robinhood  Activity Date | Process Date | Settle Date | Instrument |
             Description | Trans Code | Quantity | Price | Amount
  Merrill    Trade Date | Settlement Date | Account | Description |
             Type | Symbol/CUSIP | Quantity | Price | Amount | (blank)
  Schwab     Date | Action | Symbol | Description |
             Quantity | Price | Fees & Comm | Amount
  Fidelity   Run Date | Action | Symbol | Description | Type |
             Price ($) | Quantity | Commission ($) | Fees ($) |
             Accrued Interest ($) | Amount ($) | Cash Balance ($) |
             Settlement Date
"""
from __future__ import annotations

import csv
import shutil
from collections import OrderedDict
from pathlib import Path

INPUT_DIR = Path("input")
SKIP_FILES = {"test_stockpile.csv"}


# ── Number helpers ─────────────────────────────────────────────────────────

def to_float(s: str) -> float | None:
    """Parse a formatted number to float; None if blank or unparseable."""
    if not s or not s.strip():
        return None
    s = s.strip()
    neg = (s.startswith("(") and s.endswith(")")) or s.startswith("-")
    s = s.strip("()").lstrip("-+").replace("$", "").replace(",", "")
    try:
        return -float(s) if neg else float(s)
    except ValueError:
        return None


def fmt_like(v: float, sample: str) -> str:
    """Re-format v to visually match sample's style (dollar, parens, decimals)."""
    if not sample or not sample.strip():
        return "" if v == 0 else str(v)
    s = sample.strip()
    is_parens   = s.startswith("(") and s.endswith(")")
    has_dollar  = "$" in s
    has_neg_pfx = s.startswith("-") and has_dollar
    inner = s.strip("()").lstrip("-+$").replace(",", "")
    decimals = len(inner.split(".")[-1]) if "." in inner else 0

    if not has_dollar:
        # Plain number (qty-style or Fidelity amounts)
        if "." in inner:
            return f"{v:.{decimals}f}"
        absv = abs(int(round(v)))
        sign = "-" if v < 0 else ""
        if absv >= 1000 or "," in s:
            return f"{sign}{absv:,}"
        return f"{int(round(v))}"

    abs_s = f"{abs(v):,.{decimals}f}"
    if is_parens:
        return f"(${abs_s})" if v < 0 else f"${abs_s}"
    if has_neg_pfx:
        return f"-${abs_s}" if v < 0 else f"${abs_s}"
    return f"-${abs_s}" if v < 0 else f"${abs_s}"


# ── Generic merge engine ───────────────────────────────────────────────────

def merge_rows(
    rows: list[list[str]],
    *,
    price_col: int,
    key_cols: list[int],
    sum_cols: list[int],
    last_cols: list[int] | None = None,
) -> tuple[list[list[str]], int]:
    """
    Group rows by key_cols (only when price_col is non-empty), sum sum_cols,
    take last_cols from the final row of each group.  Non-priced rows pass
    through unchanged (each gets a unique sentinel key).

    Returns (merged_rows, n_eliminated).
    """
    buckets: OrderedDict[tuple, list[list[str]]] = OrderedDict()
    sentinel = [None]  # mutable so each non-priced row gets a fresh id

    for row in rows:
        price = row[price_col] if price_col < len(row) else ""
        if not price or not price.strip():
            key = (id(sentinel), id(row))   # unique — never merged
        else:
            key = tuple(row[c] if c < len(row) else "" for c in key_cols)
        buckets.setdefault(key, []).append(row)

    merged, saved = [], 0
    for group in buckets.values():
        if len(group) == 1:
            merged.append(group[0])
            continue
        out = list(group[0])
        for col in sum_cols:
            vals   = [to_float(r[col]) for r in group if col < len(r)]
            total  = sum(v for v in vals if v is not None)
            sample = next((r[col] for r in group if col < len(r) and r[col].strip()), "")
            if col < len(out):
                out[col] = fmt_like(total, sample)
        if last_cols:
            for col in last_cols:
                out[col] = group[-1][col] if col < len(group[-1]) else ""
        merged.append(out)
        saved += len(group) - 1

    return merged, saved


# ── Format-specific drivers ────────────────────────────────────────────────

def process_robinhood(path: Path) -> int:
    """
    Columns (0-indexed):
      0 Activity Date  1 Process Date  2 Settle Date  3 Instrument
      4 Description    5 Trans Code    6 Quantity      7 Price   8 Amount
    Merge key: 0,1,2,3,4,5,7  |  Sum: 6,8  |  Skip if Price(7) empty
    Preserves trailing blank/disclaimer rows.
    """
    raw_rows, footer = [], []
    header = None
    with open(path, newline="", encoding="utf-8") as fh:
        for row in csv.reader(fh):
            if header is None:
                header = row
                continue
            # Blank row or 10-field disclaimer row → footer
            if not any(row) or len(row) > 9:
                footer.append(row)
            else:
                raw_rows.append(row)

    merged, saved = merge_rows(
        raw_rows,
        price_col=7,
        key_cols=[0, 1, 2, 3, 4, 5, 7],
        sum_cols=[6, 8],
    )
    if saved == 0:
        return 0

    shutil.copy(path, path.with_suffix(".bak"))
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh, quoting=csv.QUOTE_ALL)
        w.writerow(header)
        for row in merged:
            w.writerow(row)
        for row in footer:
            w.writerow(row)
    return saved


def process_merrill(path: Path) -> int:
    """
    Columns (0-indexed, note trailing spaces in header names):
      0 Trade Date  1 Settlement Date  2 Account  3 Description
      4 Type        5 Symbol/CUSIP     6 Quantity  7 Price  8 Amount  9 (blank)
    Merge key: 0,1,2,3,4,5,7  |  Sum: 6,8  |  Skip if Price(7) empty
    """
    raw_rows = []
    header = None
    with open(path, newline="", encoding="utf-8") as fh:
        for row in csv.reader(fh):
            if header is None:
                header = row
                continue
            if not any(row):
                continue
            raw_rows.append(row)

    merged, saved = merge_rows(
        raw_rows,
        price_col=7,
        key_cols=[0, 1, 2, 3, 4, 5, 7],
        sum_cols=[6, 8],
    )
    if saved == 0:
        return 0

    shutil.copy(path, path.with_suffix(".bak"))
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh, quoting=csv.QUOTE_ALL)
        w.writerow(header)
        for row in merged:
            w.writerow(row)
    return saved


def process_schwab(path: Path) -> int:
    """
    Columns (0-indexed):
      0 Date  1 Action  2 Symbol  3 Description
      4 Quantity  5 Price  6 Fees & Comm  7 Amount
    Merge key: 0,1,2,3,5  |  Sum: 4,6,7  |  Skip if Price(5) empty
    """
    raw_rows = []
    header = None
    with open(path, newline="", encoding="utf-8-sig") as fh:
        for row in csv.reader(fh):
            if header is None:
                header = row
                continue
            if not any(row):
                continue
            raw_rows.append(row)

    merged, saved = merge_rows(
        raw_rows,
        price_col=5,
        key_cols=[0, 1, 2, 3, 5],
        sum_cols=[4, 6, 7],
    )
    if saved == 0:
        return 0

    shutil.copy(path, path.with_suffix(".bak"))
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh, quoting=csv.QUOTE_ALL)
        w.writerow(header)
        for row in merged:
            w.writerow(row)
    return saved


def process_fidelity(path: Path) -> int:
    """
    Columns (0-indexed):
      0 Run Date  1 Action  2 Symbol  3 Description  4 Type  5 Price ($)
      6 Quantity  7 Commission ($)  8 Fees ($)  9 Accrued Interest ($)
      10 Amount ($)  11 Cash Balance ($)  12 Settlement Date
    Merge key: 0,1,2,3,4,5,12  |  Sum: 6,7,8,9,10  |  Last: 11
    Skip if Price(5) empty.  Preserves leading/trailing blank lines.
    """
    leading_blanks = 0
    trailing_blank = False
    raw_rows = []
    header = None

    with open(path, newline="", encoding="utf-8-sig") as fh:
        for row in csv.reader(fh):
            if not any(row):
                if header is None:
                    leading_blanks += 1
                else:
                    trailing_blank = True
                continue
            if header is None:
                header = row
                continue
            raw_rows.append(row)

    merged, saved = merge_rows(
        raw_rows,
        price_col=5,
        key_cols=[0, 1, 2, 3, 4, 5, 12],
        sum_cols=[6, 7, 8, 9, 10],
        last_cols=[11],
    )
    if saved == 0:
        return 0

    shutil.copy(path, path.with_suffix(".bak"))
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        for _ in range(leading_blanks):
            fh.write("\n")
        w.writerow(header)
        for row in merged:
            w.writerow(row)
        if trailing_blank:
            fh.write("\n")
    return saved


# ── Format detection ───────────────────────────────────────────────────────

def detect_format(path: Path) -> str | None:
    """Return format name or None if unrecognised / should be skipped."""
    with open(path, newline="", encoding="utf-8-sig") as fh:
        for row in csv.reader(fh):
            if not any(row):
                continue
            joined = ",".join(row).lower()
            if "activity date" in joined and "trans code" in joined:
                return "robinhood"
            if "trade date" in joined and "symbol/ cusip" in joined:
                return "merrill"
            if "fees & comm" in joined:
                return "schwab"
            if "cash balance" in joined and "commission" in joined:
                return "fidelity"
            return None   # first non-blank row didn't match anything
    return None


PROCESSORS = {
    "robinhood": process_robinhood,
    "merrill":   process_merrill,
    "schwab":    process_schwab,
    "fidelity":  process_fidelity,
}


# ── Main ───────────────────────────────────────────────────────────────────

def main() -> None:
    csvs = sorted(INPUT_DIR.glob("*.csv"))
    total_saved = 0

    for path in csvs:
        if path.name in SKIP_FILES:
            print(f"  skip  {path.name}")
            continue
        fmt = detect_format(path)
        if fmt is None:
            print(f"  ??    {path.name}  (unrecognised format — skipped)")
            continue
        processor = PROCESSORS[fmt]
        saved = processor(path)
        if saved:
            print(f"  merge {path.name}  [{fmt}]  -{saved} rows")
            total_saved += saved
        else:
            print(f"  ok    {path.name}  [{fmt}]  nothing to merge")

    print(f"\nDone. {total_saved} row(s) eliminated across all files.")


if __name__ == "__main__":
    main()
