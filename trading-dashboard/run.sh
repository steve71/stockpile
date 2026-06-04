#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────
# run.sh  —  Start the dashboard via the shared uv workspace
#            Open http://localhost:5000 in your browser
# ─────────────────────────────────────────────────────────
set -e
cd "$(dirname "$0")"
echo "Starting Trading Dashboard at http://localhost:5000"
uv run app.py
