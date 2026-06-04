"""Persist recent single-ticker scan parameters for quick re-entry.

Stores up to _MAX_ENTRIES entries in a JSON file next to config.toml.
Both "find new options" and "roll an existing position" flows are
supported; each entry carries a `flow` key that controls which
session-state keys get pre-filled on recall.

Entry schema
------------
Common to both flows:
  ts          ISO-8601 timestamp (for display order, not dedup)
  flow        "find" | "roll"
  ticker      e.g. "AMD"
  label       human-readable string for the selectbox

Find-flow only:
  buy         bool
  option_type "Calls" | "Puts" | "Both"
  min_dte     int
  max_dte     int
  min_oi      int
  min_vol     int
  delta_min   float
  delta_max   float
  top_n       int

Roll-flow only:
  roll_type   "call" | "put"
  roll_strike float
  roll_exp    "YYYY-MM-DD"
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from options_scanner.format import fmt_strike

_PATH = Path(__file__).parents[1] / "recent_scans.json"
_MAX_ENTRIES = 12


def load() -> list[dict]:
    """Return saved entries newest-first. Returns [] on missing or corrupt file.

    Entries missing required fields (e.g. saved before a schema change)
    are silently skipped so stale files never break the UI.
    """
    try:
        entries = json.loads(_PATH.read_text(encoding="utf-8"))
    except Exception:
        return []
    valid = []
    for e in entries:
        try:
            # Minimum viable entry: must have flow and ticker.
            # Back-fill shared filter fields missing from older entries.
            if not e.get("flow") or not e.get("ticker"):
                continue
            e.setdefault("min_dte",   30)
            e.setdefault("max_dte",   90)
            e.setdefault("min_oi",    25)
            e.setdefault("min_vol",   10)
            e.setdefault("delta_min", 0.10)
            e.setdefault("delta_max", 0.75)
            e.setdefault("top_n",     10)
            valid.append(e)
        except Exception:
            continue
    return valid


def save(entry: dict) -> None:
    """Prepend entry, dedup, cap at _MAX_ENTRIES, write to disk."""
    entry = {**entry, "ts": datetime.now().isoformat(timespec="seconds")}
    existing = load()
    # Dedup: if an entry with identical non-ts fields exists, remove the old one.
    def _key(e: dict) -> tuple:
        return tuple(
            sorted((k, v) for k, v in e.items() if k not in ("ts", "label"))
        )
    new_key = _key(entry)
    deduped = [e for e in existing if _key(e) != new_key]
    merged = [entry] + deduped
    _PATH.write_text(
        json.dumps(merged[:_MAX_ENTRIES], indent=2),
        encoding="utf-8",
    )


def build_label(entry: dict) -> str:
    """Human-readable selectbox label for an entry."""
    ticker = entry.get("ticker", "?")
    min_oi = entry.get("min_oi", 0)
    oi_str = f" · OI≥{min_oi}" if min_oi else ""
    if entry.get("flow") == "roll":
        rtype = entry.get("roll_type", "call").upper()
        strike = entry.get("roll_strike", 0.0)
        exp = entry.get("roll_exp", "")
        try:
            exp_fmt = datetime.strptime(exp, "%Y-%m-%d").strftime("%b %d '%y")
        except ValueError:
            exp_fmt = exp
        return f"{ticker} [Roll] · {rtype} {fmt_strike(strike)} · {exp_fmt}{oi_str}"
    else:
        otype = entry.get("option_type", "Calls").upper()
        direction = "BUY" if entry.get("buy") else "SELL"
        min_dte = entry.get("min_dte", 30)
        max_dte = entry.get("max_dte", 90)
        dte_str = f"DTE {min_dte}–{max_dte}" if max_dte else f"DTE ≥{min_dte}"
        return f"{ticker} [Find] · {otype} · {direction} · {dte_str}{oi_str}"
