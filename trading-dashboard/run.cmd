@echo off

cd /d "%~dp0"

echo Starting Trading Dashboard at http://localhost:5000
uv run app.py

pause
