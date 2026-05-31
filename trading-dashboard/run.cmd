@echo on

cd /d "%~dp0"
call .venv\Scripts\activate

echo "Starting Trading Dashboard at http://localhost:5000"
python3 app.py

pause