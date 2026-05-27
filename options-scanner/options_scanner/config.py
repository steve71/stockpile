"""Load options-scanner/config.toml."""

import tomllib
from pathlib import Path

_CONFIG_PATH = Path(__file__).parents[1] / "config.toml"


def load_config() -> dict:
    """Return config dict; empty dict if config.toml is missing."""
    if not _CONFIG_PATH.exists():
        return {}
    with open(_CONFIG_PATH, "rb") as f:
        return tomllib.load(f)


def get_provider(cfg: dict) -> str:
    """Return 'yahoo', 'schwab', or 'moomoo' from config, defaulting to 'yahoo'."""
    return cfg.get("data_source", {}).get("provider", "yahoo")


def get_schwab_config(cfg: dict) -> dict:
    """Return the [schwab] section with defaults filled in."""
    s = cfg.get("schwab", {})
    return {
        "app_key":      s.get("app_key", ""),
        "app_secret":   s.get("app_secret", ""),
        "callback_url": s.get("callback_url", "https://127.0.0.1:8182/"),
        "token_file":   s.get("token_file", "~/.config/schwab-token.json"),
    }


def get_moomoo_config(cfg: dict) -> dict:
    """Return the [moomoo] section with defaults filled in.

    Keys:
        host: IP address of the OpenD gateway (default '127.0.0.1').
        port: TCP port of the OpenD gateway (default 11111).
    """
    m = cfg.get("moomoo", {})
    return {
        "host": m.get("host", "127.0.0.1"),
        "port": int(m.get("port", 11111)),
    }
