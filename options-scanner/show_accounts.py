#!/usr/bin/env python3
"""Read-only Schwab account snapshot — lists every linked account and its
key trading balances. No order entry; nothing is written.

    uv run options-scanner/show_accounts.py

Useful for confirming which linked account is which (the put-selling code
currently assumes nums[0]) and reading available trading balance. Account
numbers and hashes are masked to their last 4 chars so the output is safe
to screen-share.
"""

from options_scanner.config import load_config, get_schwab_config
from stocks_shared.schwab_live import get_client


def _mask(s: str | None) -> str:
    s = str(s or "")
    return ("..." + s[-4:]) if len(s) > 4 else (s or "-")


def _money(v) -> str:
    return f"${float(v):,.2f}" if v is not None else "-"


def main() -> None:
    cfg = get_schwab_config(load_config())
    client = get_client(
        cfg["app_key"], cfg["app_secret"],
        cfg["callback_url"], cfg["token_file"],
    )

    resp = client.get_account_numbers()
    data = resp.json()
    # The Accounts & Trading product is authorized separately from Market Data.
    # Until it's active for this app/account, Schwab returns an error payload
    # ({"errors":[...]}) instead of the list of accounts.
    if resp.status_code != 200 or isinstance(data, dict):
        errs = data.get("errors") if isinstance(data, dict) else None
        detail = errs[0].get("detail") if errs else data
        print(f"Accounts & Trading API not available "
              f"(HTTP {resp.status_code}): {detail}\n")
        print("Market-data quotes work with this same token, so it's not the")
        print("token - the Accounts & Trading product isn't authorized yet.")
        print("On developer.schwab.com, confirm the app has 'Accounts and")
        print("Trading Production' in 'Ready For Use' status with the account")
        print("linked. Newly granted access can take until the next day.")
        return

    nums = data
    print(f"{len(nums)} linked account(s):\n")

    for entry in nums:
        acct_hash = entry["hashValue"]
        acct = client.get_account(acct_hash).json().get("securitiesAccount", {})
        bal = acct.get("currentBalances", {})
        print(f"Account {_mask(entry.get('accountNumber'))} "
              f"(hash {_mask(acct_hash)}) - type {acct.get('type', '-')}")
        # Field names differ by account type (cash vs margin), so print every
        # numeric balance Schwab returns rather than guessing a fixed set.
        width = max((len(k) for k in bal), default=0)
        for key in sorted(bal):
            val = bal[key]
            if isinstance(val, (int, float)):
                print(f"  {key:<{width}} : {_money(val)}")
        print()


if __name__ == "__main__":
    main()
