# app.py – SUPER BOT v4 (Merged v3 + v4) – ENHANCED HISTORICAL OHLCV FETCHING
from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
import mysql.connector
import ccxt
import pandas as pd
import pandas_ta as ta
from datetime import datetime, timedelta
import math
import time
import json
import websocket
import threading
from io import BytesIO

# Assuming rotation.py exists with the function
from rotation import get_rotation_candidates_from_gainers

app = Flask(__name__)
CORS(app)

# Global real-time data
real_time_data = {
    "current_symbol": "BTC/USDT",
    "order_book": {
        "binance": {"bids": [], "asks": []},
        "bybit": {"bids": [], "asks": []},
        "okx": {"bids": [], "asks": []},
        "gateio": {"bids": [], "asks": []}
    },
    "trades": [],
    "vwap": None,
    "current_price": 0.0,
    "last_update": 0,
    "total_buy_volume": 0.0,
    "total_sell_volume": 0.0,
    "order_flow_imbalance": 0.0,
    "predicted_price": 0.0
}

# Global WS objects
binance_ws = None
bybit_ws = None
okx_ws = None
gateio_ws = None

# ========= DB CONNECTION =========
def get_conn():
    return mysql.connector.connect(
        host="localhost",
        user="root",
        password="toor",
        database="crypto_data"
    )

def init_tables():
    conn = get_conn()
    cur = conn.cursor()
    # OHLCV
    cur.execute("""
CREATE TABLE IF NOT EXISTS ohlcv_data (
    id INT AUTO_INCREMENT PRIMARY KEY,
    symbol VARCHAR(50),
    timeframe VARCHAR(20),
    time_utc DATETIME,
    open DOUBLE,
    high DOUBLE,
    low DOUBLE,
    close DOUBLE,
    volume DOUBLE,
    UNIQUE KEY uniq_candle (symbol, timeframe, time_utc)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)
    # Gainers/Losers
    cur.execute("""
CREATE TABLE IF NOT EXISTS daily_gainers_losers (
    id INT AUTO_INCREMENT PRIMARY KEY,
    symbol VARCHAR(50) NOT NULL,
    price DOUBLE,
    price_change_percent DOUBLE,
    volume_24h DOUBLE,
    fetched_at DATETIME DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)
    # Exchange Symbols
    cur.execute("""
CREATE TABLE IF NOT EXISTS exchange_symbols (
    id INT AUTO_INCREMENT PRIMARY KEY,
    exchange VARCHAR(50) NOT NULL,
    symbol VARCHAR(100) NOT NULL,
    base VARCHAR(30),
    quote VARCHAR(30),
    active BOOLEAN,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uniq_exchange_symbol (exchange, symbol)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)
    # Indexes
    try:
        cur.execute("CREATE INDEX IF NOT EXISTS idx_ohlcv_symbol_tf ON ohlcv_data(symbol, timeframe)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_gainers_symbol ON daily_gainers_losers(symbol)")
    except:
        pass
    conn.commit()
    cur.close()
    conn.close()

# ========= DB HELPERS =========
def save_ohlcv(df, symbol, timeframe):
    conn = get_conn()
    cur = conn.cursor()
    sql = """
INSERT IGNORE INTO ohlcv_data
(symbol, timeframe, time_utc, open, high, low, close, volume)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
    """
    rows = []
    for _, r in df.iterrows():
        t = r["Time (UTC)"]
        if isinstance(t, pd.Timestamp):
            t = t.to_pydatetime()
        rows.append((
            symbol, timeframe, t,
            float(r["Open"]), float(r["High"]), float(r["Low"]),
            float(r["Close"]), float(r["Volume"])
        ))
    if rows:
        cur.executemany(sql, rows)
        conn.commit()
    cur.close()
    conn.close()

def save_daily_gainers_losers(data_list):
    conn = get_conn()
    cur = conn.cursor()
    sql = """
INSERT INTO daily_gainers_losers (symbol, price, price_change_percent, volume_24h)
VALUES (%s, %s, %s, %s)
    """
    rows = [
        (d['symbol'], float(d['lastPrice']), float(d['priceChangePercent']), float(d['quoteVolume']))
        for d in data_list if d.get('lastPrice') is not None and d.get('priceChangePercent') is not None
    ]
    if rows:
        cur.executemany(sql, rows)
        conn.commit()
    cur.close()
    conn.close()

def get_existing_symbols(exchange_name: str):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT symbol FROM exchange_symbols WHERE exchange=%s", (exchange_name,))
    existing = {row[0] for row in cur.fetchall()}
    cur.close()
    conn.close()
    return existing

def save_new_symbols(exchange_name: str, symbols: list):
    if not symbols:
        return
    conn = get_conn()
    cur = conn.cursor()
    sql = """
INSERT IGNORE INTO exchange_symbols
(exchange, symbol, base, quote, active)
VALUES (%s, %s, %s, %s, %s)
    """
    rows = [
        (exchange_name, s["symbol"], s.get("base"), s.get("quote"), s.get("active", True))
        for s in symbols
    ]
    cur.executemany(sql, rows)
    conn.commit()
    cur.close()
    conn.close()

# ========= EXCHANGE =========
def get_exchange():
    return ccxt.binance({"enableRateLimit": True})

# ========= REAL-TIME WEBSOCKETS =========
def close_websockets():
    global binance_ws, bybit_ws, okx_ws, gateio_ws
    if binance_ws:
        try: binance_ws.close()
        except: pass
    if bybit_ws:
        try: bybit_ws.close()
        except: pass
    if okx_ws:
        try: okx_ws.close()
        except: pass
    if gateio_ws:
        try: gateio_ws.close()
        except: pass
    binance_ws = bybit_ws = okx_ws = gateio_ws = None

def start_websockets():
    global binance_ws, bybit_ws, okx_ws, gateio_ws
    close_websockets()
    symbol = real_time_data["current_symbol"]
    binance_pair = symbol.replace('/', '').lower()
    bybit_pair = symbol.replace('/', '').upper()
    okx_pair = symbol.replace('/', '-').upper()
    gateio_pair = symbol.replace('/', '_').upper()

    def ws_thread(url, on_open=None, on_message=None, exchange=''):
        while True:
            try:
                ws = websocket.WebSocketApp(url, on_open=on_open, on_message=on_message)
                if exchange == 'binance':
                    global binance_ws
                    binance_ws = ws
                elif exchange == 'bybit':
                    global bybit_ws
                    bybit_ws = ws
                elif exchange == 'okx':
                    global okx_ws
                    okx_ws = ws
                elif exchange == 'gateio':
                    global gateio_ws
                    gateio_ws = ws
                ws.run_forever(ping_interval=20)
            except Exception as e:
                print(f"{exchange} WS error: {e}")
                time.sleep(5)

    # Binance
    binance_url = f"wss://stream.binance.com:9443/stream?streams={binance_pair}@depth20@100ms/{binance_pair}@trade"
    threading.Thread(target=ws_thread, args=(binance_url, None, on_message_binance, 'binance'), daemon=True).start()

    # Bybit
    bybit_url = "wss://stream.bybit.com/v5/public/spot"
    def bybit_open(ws):
        ws.send(json.dumps({"op": "subscribe", "args": [f"orderbook.50.{bybit_pair}", f"publicTrade.{bybit_pair}"]}))
    threading.Thread(target=ws_thread, args=(bybit_url, bybit_open, on_message_bybit, 'bybit'), daemon=True).start()

    # OKX
    okx_url = "wss://ws.okx.com:8443/ws/v5/public"
    def okx_open(ws):
        ws.send(json.dumps({"op": "subscribe", "args": [{"channel": "books5", "instId": okx_pair}, {"channel": "trades", "instId": okx_pair}]}))
    threading.Thread(target=ws_thread, args=(okx_url, okx_open, on_message_okx, 'okx'), daemon=True).start()

    # Gate.io
    gateio_url = "wss://api.gateio.ws/ws/v4/"
    def gateio_open(ws):
        timestamp = int(time.time())
        ws.send(json.dumps({"time": timestamp, "channel": "spot.order_book", "event": "subscribe", "payload": [gateio_pair, "20", "100ms"]}))
        ws.send(json.dumps({"time": timestamp, "channel": "spot.trades", "event": "subscribe", "payload": [gateio_pair]}))
    threading.Thread(target=ws_thread, args=(gateio_url, gateio_open, on_message_gateio, 'gateio'), daemon=True).start()

def on_message_binance(ws, message):
    data = json.loads(message)
    if 'stream' in data:
        if data['stream'].endswith('@depth20@100ms'):
            book = data['data']
            update_order_book("binance", book['bids'], book['asks'])
        elif data['stream'].endswith('@trade'):
            trade = data['data']
            side = 'b' if not trade.get('m') else 's'
            process_trade("binance", {
                "price": float(trade['p']),
                "volume": float(trade['q']),
                "timestamp": trade['T'] / 1000,
                "side": side
            })

def on_message_bybit(ws, message):
    data = json.loads(message)
    if 'topic' in data:
        if data['topic'].startswith('orderbook.50.'):
            update_order_book("bybit", data['data']['b'], data['data']['a'])
        elif data['topic'].startswith('publicTrade.'):
            for t in data['data']:
                side = 'b' if t['S'] == 'Buy' else 's'
                process_trade("bybit", {
                    "price": float(t['p']),
                    "volume": float(t['v']),
                    "timestamp": t['ts'] / 1000,
                    "side": side
                })

def on_message_okx(ws, message):
    data = json.loads(message)
    if 'arg' in data and 'data' in data:
        channel = data['arg']['channel']
        if channel == 'books5':
            book = data['data'][0]
            update_order_book("okx", book['bids'], book['asks'])
        elif channel == 'trades':
            for t in data['data']:
                side = 'b' if t['side'] == 'buy' else 's'
                process_trade("okx", {
                    "price": float(t['px']),
                    "volume": float(t['sz']),
                    "timestamp": int(t['ts']) / 1000,
                    "side": side
                })

def on_message_gateio(ws, message):
    data = json.loads(message)
    if 'event' in data and data['event'] == 'update':
        channel = data['channel']
        if channel == 'spot.order_book':
            book = data['result']
            update_order_book("gateio", book['b'], book['a'])
        elif channel == 'spot.trades':
            for t in data['result']:
                side = 'b' if t['side'] == 'buy' else 's'
                process_trade("gateio", {
                    "price": float(t['price']),
                    "volume": float(t['amount']),
                    "timestamp": t['create_time_ms'] / 1000 if 'create_time_ms' in t else t['create_time'],
                    "side": side
                })

def process_trade(exchange, trade):
    price = trade.get('price', 0)
    volume = trade.get('volume', 0)
    timestamp = trade.get('timestamp', time.time())
    side = trade.get('side', 'b')
    real_time_data["trades"].append([price, volume, timestamp, side, exchange])
    if len(real_time_data["trades"]) > 1000:
        real_time_data["trades"] = real_time_data["trades"][-1000:]
    calculate_realtime_metrics()

def update_order_book(exchange, bids, asks):
    formatted_bids = [[float(p), float(q)] for p, q in bids]
    formatted_asks = [[float(p), float(q)] for p, q in asks]
    real_time_data["order_book"][exchange]["bids"] = sorted(formatted_bids, reverse=True)[:20]
    real_time_data["order_book"][exchange]["asks"] = sorted(formatted_asks)[:20]
    calculate_realtime_metrics()

def calculate_realtime_metrics():
    total_buy = 0
    total_sell = 0
    for ex_book in real_time_data["order_book"].values():
        total_buy += sum(q for _, q in ex_book["bids"])
        total_sell += sum(q for _, q in ex_book["asks"])
    real_time_data["total_buy_volume"] = total_buy
    real_time_data["total_sell_volume"] = total_sell
    total = total_buy + total_sell + 1e-8
    real_time_data["order_flow_imbalance"] = (total_buy - total_sell) / total
    recent_trades = [t for t in real_time_data["trades"] if time.time() - t[2] < 300]
    if recent_trades:
        vwap_sum = sum(t[0] * t[1] for t in recent_trades)
        vol_sum = sum(t[1] for t in recent_trades)
        real_time_data["vwap"] = vwap_sum / vol_sum if vol_sum > 0 else None
        real_time_data["current_price"] = recent_trades[-1][0]
    real_time_data["predicted_price"] = real_time_data["current_price"] * (1 + 0.005 * real_time_data["order_flow_imbalance"]) if real_time_data["current_price"] else 0.0
    real_time_data["last_update"] = time.time()

# ========= ENDPOINTS =========
@app.route('/realtime_data')
def realtime_data():
    return jsonify(real_time_data)

@app.route('/set_symbol', methods=['POST'])
def set_symbol():
    data = request.json
    new_symbol = data.get('symbol', 'BTC/USDT').upper()
    if new_symbol != real_time_data["current_symbol"]:
        real_time_data["current_symbol"] = new_symbol
        for ex in real_time_data["order_book"]:
            real_time_data["order_book"][ex] = {"bids": [], "asks": []}
        real_time_data["trades"].clear()
        start_websockets()
    return jsonify({"success": True})

@app.route("/sync_binance_symbols", methods=["POST"])
def sync_binance_symbols():
    ex = get_exchange()
    exchange_name = "binance"
    try:
        markets = ex.load_markets()
        existing = get_existing_symbols(exchange_name)
        new_symbols = []
        processed = 0
        for symbol, m in markets.items():
            processed += 1
            if symbol in existing:
                continue
            new_symbols.append({
                "symbol": symbol,
                "base": m.get("base"),
                "quote": m.get("quote"),
                "active": m.get("active", True),
            })
            if processed % 50 == 0:
                time.sleep(0.2)
        save_new_symbols(exchange_name, new_symbols)
        return jsonify({
            "success": True,
            "exchange": exchange_name,
            "total_markets": len(markets),
            "already_existing": len(existing),
            "newly_added": len(new_symbols),
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/fetch_gainers_losers", methods=["GET"])
def fetch_gainers_losers():
    ex = get_exchange()
    try:
        tickers = ex.fetch_tickers()
        usdt_pairs = {s: d for s, d in tickers.items() if s.endswith("/USDT") and d.get("quoteVolume")}
        all_data = []
        for sym, d in usdt_pairs.items():
            pct = d.get("percentage")
            if pct is None:
                continue
            all_data.append({
                "symbol": sym,
                "lastPrice": d["last"],
                "priceChangePercent": pct,
                "quoteVolume": d["quoteVolume"],
            })
        gainers = sorted(all_data, key=lambda x: x["priceChangePercent"], reverse=True)[:50]
        losers = sorted(all_data, key=lambda x: x["priceChangePercent"])[:50]
        save_daily_gainers_losers(gainers + losers)
        return jsonify({
            "success": True,
            "message": f"Fetched {len(gainers)} gainers & {len(losers)} losers.",
            "gainers": len(gainers),
            "losers": len(losers)
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/get_gainers", methods=["GET"])
def get_gainers():
    conn = get_conn()
    cur = conn.cursor(dictionary=True)
    cur.execute("""
        SELECT symbol, price, price_change_percent, volume_24h, fetched_at
        FROM daily_gainers_losers
        WHERE DATE(fetched_at) = CURDATE()
          AND price_change_percent IS NOT NULL
        ORDER BY price_change_percent DESC
        LIMIT 50
    """)
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return jsonify({"data": rows})

@app.route("/get_losers", methods=["GET"])
def get_losers():
    conn = get_conn()
    cur = conn.cursor(dictionary=True)
    cur.execute("""
        SELECT symbol, price, price_change_percent, volume_24h, fetched_at
        FROM daily_gainers_losers
        WHERE DATE(fetched_at) = CURDATE()
          AND price_change_percent IS NOT NULL
        ORDER BY price_change_percent ASC
        LIMIT 50
    """)
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return jsonify({"data": rows})

@app.route("/fetch_data", methods=["POST"])
def fetch_data():
    payload = request.get_json() or {}
    symbol = payload.get("symbol", "BTC/USDT").upper()
    timeframe = payload.get("timeframe", "4h")
    from_year = payload.get("from_year")
    to_year = payload.get("to_year")
    ex = get_exchange()
    try:
        # Set initial 'since' (earliest possible if no from_year)
        if from_year:
            from_year = int(from_year)
            since = int(datetime(from_year, 1, 1).timestamp() * 1000)
        else:
            since = None  # ccxt will fetch from the beginning if None

        # Set 'until' if to_year provided
        params = {}
        if to_year:
            to_year = int(to_year)
            until = int(datetime(to_year, 12, 31, 23, 59, 59).timestamp() * 1000)
            params["until"] = until
        else:
            until = None

        all_ohlcv = []
        total_fetched = 0
        while True:
            print(f"Fetching chunk for {symbol} {timeframe} from {since if since else 'start'}")
            ohlcv = ex.fetch_ohlcv(symbol, timeframe=timeframe, since=since, limit=1000, params=params)
            if not ohlcv:
                break
            # Filter if until is set
            if until:
                ohlcv = [c for c in ohlcv if c[0] < until]
            if not ohlcv:
                break
            all_ohlcv.extend(ohlcv)
            total_fetched += len(ohlcv)
            # Save chunk immediately
            df_chunk = pd.DataFrame(ohlcv, columns=["Timestamp", "Open", "High", "Low", "Close", "Volume"])
            df_chunk["Time (UTC)"] = pd.to_datetime(df_chunk["Timestamp"], unit="ms")
            save_ohlcv(df_chunk, symbol, timeframe)
            # Next chunk
            since = ohlcv[-1][0] + 1
            time.sleep(0.5)
            if total_fetched > 1_000_000:
                break

        if not all_ohlcv:
            return jsonify({"success": False, "error": "No data from exchange"}), 400

        df = pd.DataFrame(all_ohlcv, columns=["Timestamp", "Open", "High", "Low", "Close", "Volume"])
        df["Time (UTC)"] = pd.to_datetime(df["Timestamp"], unit="ms")
        return jsonify({
            "success": True,
            "message": f"Fetched and saved {total_fetched} candles for {symbol} (all available in range)",
            "data": df[["Time (UTC)", "Open", "High", "Low", "Close", "Volume"]].to_dict(orient="records")
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/fetch_from_db", methods=["POST"])
def fetch_from_db():
    payload = request.get_json() or {}
    symbol = payload.get("symbol", "BTC/USDT").upper()
    timeframe = payload.get("timeframe", "4h")
    conn = get_conn()
    cur = conn.cursor(dictionary=True)
    cur.execute("""
        SELECT time_utc, open, high, low, close, volume
        FROM ohlcv_data
        WHERE symbol=%s AND timeframe=%s
        ORDER BY time_utc DESC
        LIMIT 500
    """, (symbol, timeframe))
    rows = cur.fetchall()
    cur.close()
    conn.close()
    if not rows:
        return jsonify({"success": False, "error": "No data in database"}), 404
    data = [{
        "time_utc": r["time_utc"].strftime("%Y-%m-%d %H:%M:%S") if isinstance(r["time_utc"], datetime) else r["time_utc"],
        "open": float(r["open"]),
        "high": float(r["high"]),
        "low": float(r["low"]),
        "close": float(r["close"]),
        "volume": float(r["volume"])
    } for r in rows]
    return jsonify({"success": True, "data": data})

def add_all_indicators(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    out = df.copy()
    close = out["Close"]
    high = out["High"]
    low = out["Low"]
    volume = out["Volume"]
    # RSI
    out["RSI"] = ta.rsi(close, length=14)
    # StochRSI
    stochrsi = ta.stochrsi(close, length=14, rsi_length=14, k=3, d=3)
    if stochrsi is not None and not stochrsi.empty:
        out["STOCHRSI_K"] = stochrsi.iloc[:, 0]
        out["STOCHRSI_D"] = stochrsi.iloc[:, 1]
    # MACD
    macd = ta.macd(close, fast=12, slow=26, signal=9)
    if macd is not None and not macd.empty:
        out["MACD"] = macd.iloc[:, 0]
        out["MACD_SIGNAL"] = macd.iloc[:, 1]
        out["MACD_HIST"] = macd.iloc[:, 2]
    # EMAs
    out["EMA20"] = ta.ema(close, length=20)
    out["EMA50"] = ta.ema(close, length=50)
    out["EMA100"] = ta.ema(close, length=100)
    out["EMA200"] = ta.ema(close, length=200)
    # Bollinger Bands
    bb = ta.bbands(close, length=20, std=2)
    if bb is not None and not bb.empty:
        out["BB_LOW"] = bb.iloc[:, 0]
        out["BB_MID"] = bb.iloc[:, 1]
        out["BB_UPPER"] = bb.iloc[:, 2]
        out["BB_WIDTH"] = (out["BB_UPPER"] - out["BB_LOW"]) / out["BB_MID"]
    # ADX
    adx = ta.adx(high, low, close, length=14)
    if adx is not None and not adx.empty:
        out["ADX"] = adx.iloc[:, 0]
    # CCI
    out["CCI"] = ta.cci(high, low, close, length=20)
    # OBV
    out["OBV"] = ta.obv(close, volume)
    # ATR
    out["ATR"] = ta.atr(high, low, close, length=14)
    # Candle patterns
    try:
        cdl = ta.cdl_pattern(out["Open"], high, low, close,
                             name=["engulfing", "doji", "hammer", "shootingstar"])
        if cdl is not None and not cdl.empty:
            for col in cdl.columns:
                out[col] = cdl[col]
    except Exception:
        pass
    # VWAP
    try:
        out["VWAP"] = ta.vwap(high, low, close, volume)
    except Exception:
        pass
    # SuperTrend
    try:
        st = ta.supertrend(high, low, close, length=10, multiplier=3)
        if st is not None and not st.empty:
            out["SUPERTREND"] = st.iloc[:, 0]
            out["SUPERTREND_DIR"] = st.iloc[:, 1]
    except Exception:
        pass
    # Donchian Channels
    try:
        dc = ta.donchian(high, low, lower_length=20, upper_length=20)
        if dc is not None and not dc.empty:
            out["DONCHIAN_LOW"] = dc.iloc[:, 0]
            out["DONCHIAN_HIGH"] = dc.iloc[:, 2]
    except Exception:
        pass
    # Volume SMA
    try:
        out["VOL_SMA20"] = ta.sma(volume, length=20)
    except Exception:
        pass
    return out

def detect_divergence(price: pd.Series, indicator: pd.Series, lookback: int = 20):
    if len(price) < lookback + 2 or len(indicator) < lookback + 2:
        return None
    p = price.tail(lookback + 2)
    ind = indicator.tail(lookback + 2)
    p_prev_high = p.iloc[-2]
    p_curr_high = p.iloc[-1]
    ind_prev = ind.iloc[-2]
    ind_curr = ind.iloc[-1]
    if p_curr_high > p_prev_high and ind_curr < ind_prev:
        return "bearish"
    p_prev_low = p.iloc[-2]
    p_curr_low = p.iloc[-1]
    if p_curr_low < p_prev_low and ind_curr > ind_prev:
        return "bullish"
    return None

def generate_signal_summary(df: pd.DataFrame):
    last = df.iloc[-1]
    close = float(last["Close"])
    last_volume = float(last["Volume"])
    def get(name, default=None):
        v = last.get(name, default)
        return None if pd.isna(v) else float(v)
    rsi = get("RSI")
    macd = get("MACD")
    macd_sig = get("MACD_SIGNAL")
    macd_hist = get("MACD_HIST")
    ema20 = get("EMA20")
    ema50 = get("EMA50")
    ema100 = get("EMA100")
    ema200 = get("EMA200")
    bb_up = get("BB_UPPER")
    bb_low = get("BB_LOW")
    adx = get("ADX")
    cci = get("CCI")
    stoch_k = get("STOCHRSI_K")
    atr = get("ATR")
    vwap = get("VWAP")
    supertrend_dir = get("SUPERTREND_DIR")
    don_high = get("DONCHIAN_HIGH")
    vol_sma = get("VOL_SMA20")
    reasons = []
    score = 50 # neutral base
    if rsi is not None:
        if rsi < 25:
            reasons.append(f"RSI {rsi:.1f} very oversold")
            score += 10
        elif rsi < 30:
            reasons.append(f"RSI {rsi:.1f} oversold")
            score += 7
        elif rsi > 75:
            reasons.append(f"RSI {rsi:.1f} very overbought")
            score -= 10
        elif rsi > 70:
            reasons.append(f"RSI {rsi:.1f} overbought")
            score -= 7
    if macd is not None and macd_sig is not None:
        if macd > macd_sig and macd_hist is not None and macd_hist > 0:
            reasons.append("MACD bullish (above signal & positive hist)")
            score += 8
        elif macd < macd_sig and macd_hist is not None and macd_hist < 0:
            reasons.append("MACD bearish (below signal & negative hist)")
            score -= 8
    if ema200 is not None:
        if close > ema200:
            reasons.append("Price above EMA200 (uptrend context)")
            score += 5
        else:
            reasons.append("Price below EMA200 (downtrend context)")
            score -= 5
    if ema50 is not None:
        if close > ema50:
            reasons.append("Price above EMA50 (short-term bullish)")
            score += 4
        else:
            reasons.append("Price below EMA50 (short-term bearish)")
            score -= 4
    if bb_up is not None and bb_low is not None:
        if close <= bb_low:
            reasons.append("Price at / below lower Bollinger band (mean reversion up)")
            score += 6
        elif close >= bb_up:
            reasons.append("Price at / above upper Bollinger band (mean reversion down)")
            score -= 6
    if adx is not None:
        if adx > 25:
            reasons.append(f"ADX {adx:.1f} strong trend")
            if macd is not None and macd_sig is not None:
                if macd > macd_sig:
                    score += 4
                elif macd < macd_sig:
                    score -= 4
    if cci is not None:
        if cci < -100:
            reasons.append(f"CCI {cci:.1f} oversold")
            score += 4
        elif cci > 100:
            reasons.append(f"CCI {cci:.1f} overbought")
            score -= 4
    if stoch_k is not None:
        if stoch_k < 20:
            reasons.append(f"StochRSI K {stoch_k:.1f} oversold")
            score += 3
        elif stoch_k > 80:
            reasons.append(f"StochRSI K {stoch_k:.1f} overbought")
            score -= 3
    if atr is not None:
        reasons.append(f"ATR: {atr:.5f} (volatility unit)")
    if "RSI" in df.columns:
        div = detect_divergence(df["Close"], df["RSI"], lookback=10)
        if div == "bullish":
            reasons.append("Bullish RSI divergence")
            score += 8
        elif div == "bearish":
            reasons.append("Bearish RSI divergence")
            score -= 8
    if vwap is not None:
        if close > vwap:
            reasons.append("Price above VWAP (bullish participation)")
            score += 4
        else:
            reasons.append("Price below VWAP (weak / bearish participation)")
            score -= 4
    if supertrend_dir is not None:
        if supertrend_dir > 0:
            reasons.append("SuperTrend bullish")
            score += 6
        elif supertrend_dir < 0:
            reasons.append("SuperTrend bearish")
            score -= 6
    if don_high is not None and close >= don_high:
        reasons.append("Donchian breakout (range expansion up)")
        score += 7
    if vol_sma is not None and vol_sma > 0:
        if last_volume > vol_sma * 1.5:
            reasons.append("Volume spike above SMA20 confirms move")
            score += 6
        elif last_volume < vol_sma * 0.7:
            reasons.append("Volume below average (weak follow-through)")
            score -= 3
    score = max(0, min(100, score))
    if score >= 75:
        bias = "bullish"
        strength = "strong"
        label = "STRONG_BULLISH"
    elif score >= 60:
        bias = "bullish"
        strength = "normal"
        label = "BULLISH"
    elif score <= 25:
        bias = "bearish"
        strength = "strong"
        label = "STRONG_BEARISH"
    elif score <= 40:
        bias = "bearish"
        strength = "normal"
        label = "BEARISH"
    else:
        bias = "neutral"
        strength = "weak"
        label = "NEUTRAL"
    if rsi is not None and rsi < 30 and "BULLISH" not in label:
        label = "WATCH_LONG"
    if rsi is not None and rsi > 70 and "BEARISH" not in label:
        label = "WATCH_SHORT"
    return {
        "bias": bias,
        "strength": strength,
        "label": label,
        "reasons": reasons,
        "score": score,
        "rsi": rsi,
        "macd": macd,
        "macd_signal": macd_sig,
        "ema20": ema20,
        "ema50": ema50,
        "ema100": ema100,
        "ema200": ema200,
        "close": close,
        "vwap": vwap,
        "supertrend_dir": supertrend_dir,
        "donchian_high": don_high,
        "vol_sma20": vol_sma,
        "adx": adx,
        "atr": atr,
    }

@app.route("/analyze_symbol", methods=["POST"])
def analyze_symbol():
    payload = request.get_json() or {}
    symbol = payload.get("symbol", "BTC/USDT").upper()
    timeframe = payload.get("timeframe", "4h")
    limit = int(payload.get("limit", 200))
    ex = get_exchange()
    try:
        ohlcv = ex.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
        if not ohlcv:
            return jsonify({"success": False, "error": "No data from exchange"}), 400
        df = pd.DataFrame(ohlcv, columns=["Timestamp", "Open", "High", "Low", "Close", "Volume"])
        df["Time (UTC)"] = pd.to_datetime(df["Timestamp"], unit="ms")
        df_ind = add_all_indicators(df)
        sig = generate_signal_summary(df_ind)
        last = df_ind.iloc[-1]
        response = {
            "success": True,
            "symbol": symbol,
            "timeframe": timeframe,
            "last_candle": {
                "time_utc": last["Time (UTC)"].strftime("%Y-%m-%d %H:%M:%S"),
                "open": float(last["Open"]),
                "high": float(last["High"]),
                "low": float(last["Low"]),
                "close": float(last["Close"]),
                "volume": float(last["Volume"]),
            },
            "indicators": {
                "rsi": sig["rsi"],
                "macd": sig["macd"],
                "macd_signal": sig["macd_signal"],
                "ema20": sig["ema20"],
                "ema50": sig["ema50"],
                "ema100": sig["ema100"],
                "ema200": sig["ema200"],
            },
            "signal": sig["label"],
            "bias": sig["bias"],
            "score": sig["score"],
            "reasons": sig["reasons"]
        }
        return jsonify(response)
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/gainers_signals", methods=["GET"])
def gainers_signals():
    timeframe = "4h"
    limit = 200
    max_coins = 15
    conn = get_conn()
    cur = conn.cursor(dictionary=True)
    cur.execute("""
        SELECT symbol, price_change_percent, volume_24h
        FROM daily_gainers_losers
        WHERE DATE(fetched_at) = CURDATE()
          AND price_change_percent IS NOT NULL
        ORDER BY price_change_percent DESC
        LIMIT %s
    """, (max_coins,))
    rows = cur.fetchall()
    cur.close()
    conn.close()
    if not rows:
        return jsonify({"success": False, "error": "No gainers in DB, click Refresh first."}), 400
    ex = get_exchange()
    results = []
    for r in rows:
        sym = r["symbol"]
        try:
            ohlcv = ex.fetch_ohlcv(sym, timeframe=timeframe, limit=limit)
            if not ohlcv:
                continue
            df = pd.DataFrame(ohlcv, columns=["Timestamp", "Open", "High", "Low", "Close", "Volume"])
            df["Time (UTC)"] = pd.to_datetime(df["Timestamp"], unit="ms")
            df_ind = add_all_indicators(df)
            sig = generate_signal_summary(df_ind)
            results.append({
                "symbol": sym,
                "timeframe": timeframe,
                "price_change_percent": float(r["price_change_percent"]),
                "volume_24h": float(r["volume_24h"]),
                "rsi": sig["rsi"],
                "signal": sig["label"],
                "bias": sig["bias"],
                "score": sig["score"],
                "close": sig["close"]
            })
        except Exception:
            continue
    return jsonify({"success": True, "data": results})

@app.route("/rotation_signals", methods=["GET"])
def rotation_signals():
    conn = get_conn()
    cur = conn.cursor(dictionary=True)
    cur.execute("""
        SELECT symbol, price_change_percent, volume_24h
        FROM daily_gainers_losers
        WHERE DATE(fetched_at) = CURDATE()
          AND price_change_percent >= 10
        ORDER BY price_change_percent DESC
        LIMIT 10
    """)
    rows = cur.fetchall()
    cur.close()
    conn.close()
    if not rows:
        return jsonify({"success": False, "error": "No pumped coins found for rotation."}), 400
    try:
        rot = get_rotation_candidates_from_gainers(rows, max_per_category=5)
        return jsonify({"success": True, "data": rot})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/search_symbols", methods=["GET"])
def search_symbols():
    q = request.args.get("q", "").strip().upper()
    exchange = request.args.get("exchange", "binance")
    conn = get_conn()
    cur = conn.cursor(dictionary=True)
    if q:
        cur.execute("""
            SELECT symbol, base, quote, active, created_at
            FROM exchange_symbols
            WHERE exchange=%s
              AND (
                    symbol LIKE %s OR
                    base LIKE %s OR
                    quote LIKE %s
                  )
            ORDER BY symbol
            LIMIT 2000
        """, (exchange, f"%{q}%", f"%{q}%", f"%{q}%"))
    else:
        cur.execute("""
            SELECT symbol, base, quote, active, created_at
            FROM exchange_symbols
            WHERE exchange=%s
            ORDER BY symbol
            LIMIT 500
        """, (exchange,))
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return jsonify({"success": True, "data": rows})

@app.route("/export_symbols_excel", methods=["GET"])
def export_symbols_excel():
    q = request.args.get("q", "").strip().upper()
    exchange = request.args.get("exchange", "binance")
    conn = get_conn()
    df = pd.read_sql("""
        SELECT symbol, base, quote, active, created_at
        FROM exchange_symbols
        WHERE exchange=%s
          AND (
                %s = '' OR
                symbol LIKE %s OR
                base LIKE %s OR
                quote LIKE %s
              )
        ORDER BY symbol
    """, conn, params=(
        exchange,
        q,
        f"%{q}%",
        f"%{q}%",
        f"%{q}%"
    ))
    conn.close()
    output = BytesIO()
    df.to_excel(output, index=False, sheet_name="Symbols")
    output.seek(0)
    filename = f"symbols_{exchange}_{q or 'all'}.xlsx"
    return send_file(
        output,
        as_attachment=True,
        download_name=filename,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok", "message": "SUPER BOT v4 running"})

# ========= MAIN =========
if __name__ == "__main__":
    init_tables()
    start_websockets()
    app.run(host="0.0.0.0", port=8000, debug=False, threaded=True)