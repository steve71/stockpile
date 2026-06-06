#!/usr/bin/env python3
"""Launch the options scanner (Streamlit) and the trading dashboard (Flask)
together, so the dashboard appears in the scanner's "Live Charts" tab.

    uv run run.py

Starts the Flask dashboard on http://localhost:5000 (also reachable
directly), waits for it to come up, then runs the Streamlit scanner on
http://localhost:8501. Both apps' logs stream to this one terminal,
prefixed `[scanner]` and `[dashboard]` so you can tell them apart. Ctrl+C
stops both. If a dashboard is already running on :5000, it is reused (not
restarted), and its logs stay in its own terminal.

To run either app on its own instead:
    uv run streamlit run options-scanner/run_app.py
    uv run trading-dashboard/app.py
"""

from __future__ import annotations

import subprocess
import sys
import threading
import time
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent
DASHBOARD_HEALTH = "http://127.0.0.1:5000/api/health"

_print_lock = threading.Lock()


def _pump(stream, prefix: str) -> None:
    """Echo a child process's combined output line-by-line, tagged with a
    prefix. The lock keeps the two apps' lines from interleaving mid-line."""
    for line in iter(stream.readline, ""):
        with _print_lock:
            sys.stdout.write(f"{prefix} {line}")
            sys.stdout.flush()
    stream.close()


def _start_logged(argv: list[str], prefix: str, **popen_kwargs) -> subprocess.Popen:
    """Start a child with its stdout+stderr captured and pumped through
    `_pump` on a daemon thread."""
    proc = subprocess.Popen(
        argv, cwd=REPO_ROOT,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, bufsize=1, encoding="utf-8", errors="replace",
        **popen_kwargs,
    )
    threading.Thread(target=_pump, args=(proc.stdout, prefix),
                     daemon=True).start()
    return proc


def _probe(timeout: float = 1.0) -> bool:
    """Single health probe of the dashboard."""
    try:
        with urllib.request.urlopen(DASHBOARD_HEALTH, timeout=timeout) as resp:
            return resp.status == 200
    except Exception:
        return False


def _wait_for_dashboard(timeout: float = 15.0) -> bool:
    """Poll until the dashboard answers or we time out."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if _probe():
            return True
        time.sleep(0.4)
    return False


def main() -> int:
    dashboard = None  # only set if WE started it (so we only stop ours)

    if _probe():
        print("[run] Trading dashboard already running on "
              "http://localhost:5000 — reusing it (its logs stay in its own "
              "terminal).")
    else:
        # On Windows, put Flask in a new process group so the console's Ctrl+C
        # doesn't kill it before our own cleanup runs.
        kw = {}
        if sys.platform == "win32":
            kw["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
        print("[run] Starting trading dashboard (Flask) on "
              "http://localhost:5000 ...")
        dashboard = _start_logged(
            [sys.executable, "trading-dashboard/app.py"], "[dashboard]", **kw,
        )
        if _wait_for_dashboard():
            print("[run] Trading dashboard is up.")
        else:
            print("[run] Warning: dashboard did not become ready in time — "
                  "the Live Charts tab will show a start hint until it is.")

    print("[run] Starting options scanner (Streamlit) on "
          "http://localhost:8501 ...")
    scanner = _start_logged(
        [sys.executable, "-m", "streamlit", "run", "options-scanner/run_app.py"],
        "[scanner]",
    )
    try:
        scanner.wait()  # blocks until Streamlit exits (or Ctrl+C)
    except KeyboardInterrupt:
        scanner.terminate()
    finally:
        if dashboard is not None:
            print("[run] Shutting down trading dashboard ...")
            dashboard.terminate()
            try:
                dashboard.wait(timeout=5)
            except subprocess.TimeoutExpired:
                dashboard.kill()
    return 0


if __name__ == "__main__":
    sys.exit(main())
