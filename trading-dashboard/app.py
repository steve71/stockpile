import time, hashlib
from flask import Flask, jsonify, request, render_template
from flask_cors import CORS
from data_source import fetch_ohlcv, _DATASOURCE_REGISTRY
app = Flask(__name__)
CORS(app, resources={r"/api/*": {"origins": ["http://localhost:5000", "http://127.0.0.1:5000"]}})
_CACHE = {}
_CACHE_TTL = {"1m":20,"3m":30,"5m":45,"15m":90,"30m":150,"1h":300,"4h":600,"1d":900,"1w":1800,"1M":3600}
_PRICE_TTL = 300

def _key(source,symbol,interval,limit): return hashlib.md5(f"{source}:{symbol}:{interval}:{limit}".encode()).hexdigest()

def _get(key,ttl):
    e = _CACHE.get(key)
    return e["data"] if e and time.time() - e["ts"] < ttl else None
def _put(key,data): _CACHE[key] = {"ts":time.time(),"data":data}

@app.route('/api/health')
def health(): return jsonify({"status":"ok","sources":list(_DATASOURCE_REGISTRY.keys())})

@app.route('/api/ohlcv')
def ohlcv():
    source = request.args.get('source','yfinance'); symbol = request.args.get('symbol','AVGO'); interval = request.args.get('interval','1d'); limit = int(request.args.get('limit',200))
    ckey = _key(source,symbol,interval,limit); ttl = _CACHE_TTL.get(interval,300); cached = _get(ckey,ttl)
    if cached is not None: return jsonify({"ok":True,"data":cached,"cached":True})
    try:
        candles = fetch_ohlcv(source,symbol,interval,limit); _put(ckey,candles); return jsonify({"ok":True,"data":candles,"cached":False})
    except Exception as e:
        return jsonify({"ok":False,"error":str(e)}), 400

@app.route('/api/price')
def price():
    source = request.args.get('source','yfinance'); symbol = request.args.get('symbol','AVGO'); ckey = _key(source,symbol,'1d',2); candles = _get(ckey,_PRICE_TTL)
    if candles is None:
        try:
            candles = fetch_ohlcv(source,symbol,'1d',2); _put(ckey,candles)
        except Exception as e:
            return jsonify({"ok":False,"error":str(e)}), 400
    if len(candles) >= 2:
        prev, last = candles[-2]['close'], candles[-1]['close']; chg = last - prev; chgp = (chg/prev*100) if prev else 0
    elif candles:
        last, chg, chgp = candles[0]['close'], 0.0, 0.0
    else:
        return jsonify({"ok":False,"error":f"No data for '{symbol}'"}), 404
    return jsonify({"ok":True,"symbol":symbol,"price":last,"change":round(chg,4),"change_pct":round(chgp,2)})

@app.route('/')
def index(): return render_template('index.html')

@app.route('/api/sources')
def sources():
    return jsonify(
        status='ok',
        symbols={
            'hyperliquid': ['ETH'],
            'yfinance': ['AVGO'],
        }
    )

if __name__ == '__main__': app.run(debug=False, host='0.0.0.0', port=5000, threaded=True)
