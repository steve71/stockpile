# Trading Dashboard

Live Trading Dashboard — lightweight Flask app serving market data endpoints and a minimal UI.

Key features
- Flask API providing OHLCV and latest-price endpoints
- Pluggable data-source registry (yfinance, hyperliquid) in data_source.py
- In-memory caching with per-interval TTLs and md5-based keys
- Shared requests.Session with retries and lock-based rate-limiting

Table of contents
- Quickstart
- API Endpoints
- Data sources
- Caching & rate limiting
- Contributing
- License

Quickstart
Prerequisites: Python 3.9+, pip.

POSIX (macOS / Linux):
1. ./run.sh

Windows:
1. run.cmd

Manual (virtualenv):
1. python -m venv .venv
2. .\\.venv\\Scripts\\activate   (Windows) or source .venv/bin/activate  (POSIX)
3. python -m pip install -r requirements.txt
4. python app.py

The app listens on 0.0.0.0:5000 by default.

API Endpoints
- GET /api/ohlcv?source={source}&symbol={symbol}&interval={interval}&limit={n}
  - Returns OHLCV arrays for the requested source/symbol/interval. Response JSON: {ok: true, data: [...]}
- GET /api/price?source={source}&symbol={symbol}
  - Returns latest price JSON
- GET /api/sources
  - Lists available data sources
- GET /api/health
  - Health check (200 OK)
- GET /
  - Serves templates/index.html (basic UI)

Data sources (data_source.py)
- Implement fetch_{source}(symbol, interval, limit) and register it in _DATASOURCE_REGISTRY.
- Use the shared _SESSION (requests.Session with Retry) for external HTTP calls.
- Call _rate_limit() before outbound requests to respect provider limits.
- Interval mappings are provided (_YF_INTERVAL/_YF_PERIOD/_HL_INTERVAL/_HL_MINS). Follow those conventions.

Caching & rate limiting
- Cache keys are md5(source:symbol:interval:limit). TTLs are configured in _CACHE_TTL and _PRICE_TTL.
- Rate limiting uses _RATE_LOCK, _LAST_CALL, and _MIN_INTERVAL to avoid provider throttling.

Developer notes
- Entry point: app.py
- Core logic: data_source.py
- Defaults: source="hyperliquid", default symbol 'ETH'
- No unit test suite currently; add pytest tests under tests/ if desired.

Contributing
- Open issues or PRs for bugs and features.
- When adding a new data source, reuse _SESSION, call _rate_limit(), and register it in _DATASOURCE_REGISTRY.

License
This project is licensed under the MIT License — see the LICENSE file for details.

Maintainer
- Repo: trading-dashboard
- For questions, open an issue on this repository.
