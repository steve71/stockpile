#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────
# run.sh  —  Install dependencies and start the dashboard
#            Open http://localhost:5000 in your browser
# ─────────────────────────────────────────────────────────
set -e
cd "$(dirname "$0")"
echo "Installing dependencies..."
python3 -m pip install -r requirements.txt
echo ""
echo "Starting Trading Dashboard at http://localhost:5000"
python3 app.py
