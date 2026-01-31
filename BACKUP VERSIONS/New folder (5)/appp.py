# app.py – SUPER BOT v4 – ENHANCED HISTORICAL OHLCV FETCHING + volume_diff
from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
import mysql.connector
import hashlib
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

# ========= DB HELPERS =========
def save_ohlcv(df, symbol, timeframe):
    conn = get_conn()
    cur = conn.cursor()
    
    sql = """
    INSERT IGNORE INTO ohlcv_data
    (symbol, timeframe, time_utc, open, high, low, close, volume, volume_diff)
    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
    """
    
    rows = []
    for i, r in df.iterrows():
        t = r["Time (UTC)"]
        if isinstance(t, pd.Timestamp):
            t = t.to_pydatetime()
        
        # Calculate volume_diff: current volume - previous volume (0 for first candle)
        volume_diff = 0.0
        if i > 0:
            prev_volume = float(df.iloc[i-1]["Volume"])
            current_volume = float(r["Volume"])
            volume_diff = current_volume - prev_volume
        
        rows.append((
            symbol,
            timeframe,
            t,
            float(r["Open"]),
            float(r["High"]),
            float(r["Low"]),
            float(r["Close"]),
            float(r["Volume"]),
            volume_diff
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

# ========= PATTERN-BASED PREDICTION SYSTEM =========
def pattern_to_hash(pattern):
    """Convert pattern list to SHA256 hash"""
    pattern_str = '|'.join([f"{c:.2f}|{h:.2f}|{l:.2f}" for c, h, l in pattern])
    return hashlib.sha256(pattern_str.encode()).hexdigest()

def pattern_to_string(pattern):
    """Convert pattern list to string (for storage)"""
    return '|'.join([f"{c:.2f}|{h:.2f}|{l:.2f}" for c, h, l in pattern])

def string_to_pattern(pattern_str):
    """Convert string back to pattern list"""
    if not pattern_str:
        return []
    pattern = []
    parts = pattern_str.split('|')
    for i in range(0, len(parts), 3):
        if i + 2 < len(parts):
            pattern.append((float(parts[i]), float(parts[i+1]), float(parts[i+2])))
    return pattern

def compute_triplet(row, prev_close):
    """Compute % change triplet for a candle vs previous close"""
    if prev_close == 0:
        return (0.0, 0.0, 0.0)
    pct_close = ((row['Close'] - prev_close) / prev_close) * 100
    pct_high = ((row['High'] - prev_close) / prev_close) * 100
    pct_low = ((row['Low'] - prev_close) / prev_close) * 100
    return (round(pct_close, 2), round(pct_high, 2), round(pct_low, 2))

def pattern_distance(p1, p2):
    """Calculate similarity between two patterns with normalization"""
    if len(p1) != len(p2):
        return float('inf')
    
    # For very long patterns, use windowed comparison
    if len(p1) > 100:
        window_size = min(50, len(p1) // 10)
        distances = []
        for i in range(0, len(p1) - window_size + 1, window_size // 2):
            window1 = p1[i:i+window_size]
            window2 = p2[i:i+window_size]
            dist = sum(math.sqrt((t1[0] - t2[0])**2 + (t1[1] - t2[1])**2 + (t1[2] - t2[2])**2)
                     for t1, t2 in zip(window1, window2)) / len(window1)
            distances.append(dist)
        return sum(distances) / len(distances)
    
    # For shorter patterns, use original method
    dist = 0
    for t1, t2 in zip(p1, p2):
        dist += math.sqrt((t1[0] - t2[0])**2 + (t1[1] - t2[1])**2 + (t1[2] - t2[2])**2)
    return dist / len(p1)

def find_similar_patterns_fuzzy(current_pattern, hist_patterns, timeframe, max_matches=100, similarity_threshold=0.5):
    """Find similar patterns using fuzzy matching with better thresholds"""
    matches = []
    
    for hist in hist_patterns:
        parsed_pattern = string_to_pattern(hist['pattern_string'])
        
        if len(parsed_pattern) != len(current_pattern):
            continue
        
        # Calculate distance with normalization
        dist = pattern_distance(current_pattern, parsed_pattern)
        
        # Dynamic threshold based on pattern length
        adjusted_threshold = similarity_threshold * (1 + len(current_pattern) / 1000)
        
        if dist <= adjusted_threshold:
            # Get weights for this pattern
            conn = get_conn()
            cur = conn.cursor(dictionary=True)
            weights = {}
            for pred_type in ['close', 'high', 'low']:
                cur.execute(f"""
                    SELECT weight 
                    FROM weights_{pred_type}_{timeframe} 
                    WHERE pattern_hash = %s
                """, (hist['pattern_hash'],))
                row = cur.fetchone()
                weights[pred_type] = row['weight'] if row else 1.0
            cur.close()
            conn.close()
            
            outcomes = json.loads(hist['outcomes'] or '[]')
            if not outcomes:
                continue
                
            matches.append({
                'pattern_hash': hist['pattern_hash'],
                'outcomes': outcomes,
                'weights': weights,
                'dist': dist,
                'occurrences': hist['occurrences']
            })
            
            if len(matches) >= max_matches:
                break
    
    return matches

@app.route("/train_bot", methods=["POST"])
def train_bot():
    payload = request.get_json() or {}
    symbol = payload.get("symbol", "BTC/USDT").upper()
    timeframes = payload.get("timeframes", ["4h"])
    look_back = int(payload.get("look_back", 50))
    
    if look_back < 10 or look_back > 5000:
        return jsonify({"success": False, "error": "Look back must be 10-5000"}), 400
    
    trained = 0
    total_patterns_added = 0
    total_patterns_updated = 0
    
    for tf in timeframes:
        # Check if pattern table exists for this timeframe
        conn = get_conn()
        cur = conn.cursor()
        cur.execute(f"SHOW TABLES LIKE 'patterns_{tf}'")
        if not cur.fetchone():
            cur.close()
            conn.close()
            print(f"Pattern table for timeframe {tf} doesn't exist - skipping")
            continue
        cur.close()
        conn.close()
        
        # Fetch historical candles
        conn = get_conn()
        cur = conn.cursor(dictionary=True)
        cur.execute("""
            SELECT time_utc, open, high, low, close
            FROM ohlcv_data
            WHERE symbol = %s AND timeframe = %s
            ORDER BY time_utc ASC
        """, (symbol, tf))
        rows = cur.fetchall()
        cur.close()
        conn.close()
        
        if len(rows) < look_back + 1:
            print(f"Not enough data for {symbol} {tf}: {len(rows)} rows, need {look_back + 1}")
            continue
        
        df = pd.DataFrame(rows)
        df['time_utc'] = pd.to_datetime(df['time_utc'])
        
        # Rename to match compute_triplet expectations
        df = df.rename(columns={
            'open': 'Open',
            'high': 'High',
            'low': 'Low',
            'close': 'Close'
        })
        
        df = df.sort_values('time_utc').reset_index(drop=True)
        
        # Compute triplets (skip first candle)
        triplets = []
        for i in range(1, len(df)):
            prev_close = df.iloc[i-1]['Close']
            triplet = compute_triplet(df.iloc[i], prev_close)
            triplets.append(triplet)
        
        if len(triplets) < look_back:
            print(f"Not enough triplets for {symbol} {tf}: {len(triplets)} triplets, need {look_back}")
            continue
        
        # Build and store patterns
        conn = get_conn()
        cur = conn.cursor()
        
        patterns_processed = 0
        patterns_added = 0
        patterns_updated = 0
        
        # Process in reverse to get most recent patterns first
        start_idx = max(0, len(triplets) - look_back - 1000)
        
        for i in range(start_idx, len(triplets) - look_back):
            pattern = triplets[i:i+look_back]
            next_triplet = triplets[i + look_back]
            
            pattern_str = pattern_to_string(pattern)
            pattern_hash = pattern_to_hash(pattern)
            new_outcome = list(next_triplet)  # [pct_close, pct_high, pct_low]
            
            # Check if pattern already exists
            cur.execute(f"""
                SELECT outcomes, occurrences 
                FROM patterns_{tf} 
                WHERE pattern_hash = %s
            """, (pattern_hash,))
            row = cur.fetchone()
            
            if row:
                # Update existing pattern
                current_outcomes = json.loads(row[0] or '[]')
                current_outcomes.append(new_outcome)
                updated_json = json.dumps(current_outcomes)
                
                cur.execute(f"""
                    UPDATE patterns_{tf}
                    SET outcomes = %s,
                        occurrences = occurrences + 1
                    WHERE pattern_hash = %s
                """, (updated_json, pattern_hash))
                patterns_updated += 1
            else:
                # Insert new pattern
                cur.execute(f"""
                    INSERT INTO patterns_{tf} (pattern_hash, pattern_string, outcomes, occurrences)
                    VALUES (%s, %s, %s, 1)
                """, (pattern_hash, pattern_str, json.dumps([new_outcome])))
                patterns_added += 1
            
            # Initialize or update weights (always ensure weight exists)
            for pred_type in ['close', 'high', 'low']:
                # Check if weights table exists
                cur.execute(f"SHOW TABLES LIKE 'weights_{pred_type}_{tf}'")
                if cur.fetchone():
                    cur.execute(f"""
                        INSERT INTO weights_{pred_type}_{tf} (pattern_hash, weight)
                        VALUES (%s, 1.0)
                        ON DUPLICATE KEY UPDATE pattern_hash = pattern_hash
                    """, (pattern_hash,))
            
            patterns_processed += 1
            
            # Commit in batches to avoid long transactions
            if patterns_processed % 500 == 0:
                conn.commit()
                print(f"  Processed {patterns_processed} patterns...")
        
        conn.commit()
        cur.close()
        conn.close()
        
        print(f"✓ Trained {tf}: {patterns_added} new, {patterns_updated} updated patterns (lookback={look_back})")
        trained += 1
        total_patterns_added += patterns_added
        total_patterns_updated += patterns_updated
    
    return jsonify({
        "success": True, 
        "message": f"Trained {trained}/{len(timeframes)} timeframes for {symbol}",
        "look_back": look_back,
        "patterns_added": total_patterns_added,
        "patterns_updated": total_patterns_updated
    })

@app.route("/predict_candle", methods=["POST"])
def predict_candle():
    payload = request.get_json() or {}
    symbol = payload.get("symbol", "BTC/USDT").upper()
    timeframe = payload.get("timeframe", "4h")
    look_back = int(payload.get("look_back", 50))
    expander = float(payload.get("expander", 1.33))
    similarity_threshold = float(payload.get("similarity_threshold", 0.5))  # Increased default
    max_matches = int(payload.get("max_matches", 100))
    
    # Dynamic threshold adjustment based on lookback
    if look_back > 100:
        similarity_threshold = max(similarity_threshold, 0.3)
        if look_back > 500:
            similarity_threshold = max(similarity_threshold, 0.5)
        if look_back > 1000:
            similarity_threshold = max(similarity_threshold, 1.0)
    
    # Get latest look_back +1 candles from DB
    conn = get_conn()
    cur = conn.cursor(dictionary=True)
    cur.execute("""
        SELECT time_utc, close, high, low
        FROM ohlcv_data
        WHERE symbol = %s AND timeframe = %s
        ORDER BY time_utc DESC
        LIMIT %s
    """, (symbol, timeframe, look_back + 1))
    rows = cur.fetchall()
    cur.close()
    conn.close()
    
    if len(rows) < look_back + 1:
        return jsonify({"success": False, "error": f"Not enough recent data: {len(rows)} rows, need {look_back + 1}. Please fetch data first from OHLCV tab."})
    
    # Convert to DataFrame with proper column names
    df_recent = pd.DataFrame(rows)
    df_recent['close'] = df_recent['close'].astype(float)
    df_recent['high'] = df_recent['high'].astype(float)
    df_recent['low'] = df_recent['low'].astype(float)
    
    # Compute current pattern (last look_back triplets)
    current_triplets = []
    for i in range(1, len(df_recent)):
        prev_close = df_recent.iloc[i-1]['close']
        # Create a row-like dict for compute_triplet
        row = {
            'Close': df_recent.iloc[i]['close'],
            'High': df_recent.iloc[i]['high'],
            'Low': df_recent.iloc[i]['low']
        }
        triplet = compute_triplet(row, prev_close)
        current_triplets.append(triplet)
    
    if len(current_triplets) < look_back:
        return jsonify({"success": False, "error": f"Not enough triplets: {len(current_triplets)}, need {look_back}"})
    
    current_pattern = current_triplets[-look_back:]
    
    # Check if pattern table exists
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(f"SHOW TABLES LIKE 'patterns_{timeframe}'")
    if not cur.fetchone():
        cur.close()
        conn.close()
        return jsonify({"success": False, "error": f"Pattern table for {timeframe} doesn't exist. Train the model first."})
    cur.close()
    conn.close()
    
    # Fetch historical patterns
    conn = get_conn()
    cur = conn.cursor(dictionary=True)
    cur.execute(f"""
        SELECT pattern_hash, pattern_string, outcomes, occurrences
        FROM patterns_{timeframe}
        ORDER BY occurrences DESC
        LIMIT %s
    """, (max_matches * 10,))
    hist_patterns = cur.fetchall()
    cur.close()
    conn.close()
    
    if not hist_patterns:
        return jsonify({"success": False, "error": "No historical patterns found. Train the model first."})
    
    # Find similar patterns using fuzzy matching
    matches = find_similar_patterns_fuzzy(
        current_pattern, 
        hist_patterns, 
        timeframe, 
        max_matches, 
        similarity_threshold
    )
    
    if not matches:
        # Try with even higher threshold for very long patterns
        if look_back > 500:
            matches = find_similar_patterns_fuzzy(
                current_pattern, 
                hist_patterns, 
                timeframe, 
                max_matches, 
                similarity_threshold * 2
            )
        
        if not matches:
            return jsonify({
                "success": False, 
                "error": f"No matching patterns found. Try: 1) Smaller lookback, 2) Higher similarity threshold, 3) More training data",
                "current_lookback": look_back,
                "similarity_threshold_tried": similarity_threshold,
                "total_patterns_in_db": len(hist_patterns)
            })
    
    # Weighted average next moves
    total_weight = 0
    weighted_close = 0
    weighted_high = 0
    weighted_low = 0
    
    for m in matches:
        # Weight based on similarity (closer distance = higher weight)
        similarity_weight = 1.0 / (1.0 + m['dist'])
        
        # Combine with pattern-specific weights
        pattern_weight = min(m['weights']['close'], m['weights']['high'], m['weights']['low'])
        
        # Total weight for this match
        match_weight = similarity_weight * pattern_weight * m['occurrences']
        
        # Average outcomes for this pattern
        avg_close = sum(o[0] for o in m['outcomes']) / len(m['outcomes'])
        avg_high = sum(o[1] for o in m['outcomes']) / len(m['outcomes'])
        avg_low = sum(o[2] for o in m['outcomes']) / len(m['outcomes'])
        
        weighted_close += avg_close * match_weight
        weighted_high += avg_high * match_weight
        weighted_low += avg_low * match_weight
        total_weight += match_weight
    
    if total_weight == 0:
        total_weight = 1  # avoid div0
    
    pct_close = weighted_close / total_weight
    pct_high = weighted_high / total_weight
    pct_low = weighted_low / total_weight
    
    # Expand bounds
    close_low = pct_close / expander
    close_high = pct_close * expander
    high_low = pct_high / expander
    high_high = pct_high * expander
    low_low = pct_low / expander
    low_high = pct_low * expander
    
    # Calculate confidence
    perfect_count = 0
    total_outcomes = 0
    for m in matches:
        for o in m['outcomes']:
            if (close_low <= o[0] <= close_high and 
                high_low <= o[1] <= high_high and 
                low_low <= o[2] <= low_high):
                perfect_count += 1
            total_outcomes += 1
    
    confidence = (perfect_count / total_outcomes * 100) if total_outcomes > 0 else 0
    
    return jsonify({
        "success": True,
        "prediction": {
            "pct_close": round(pct_close, 2),
            "close_low": round(close_low, 2),
            "close_high": round(close_high, 2),
            "pct_high": round(pct_high, 2),
            "high_low": round(high_low, 2),
            "high_high": round(high_high, 2),
            "pct_low": round(pct_low, 2),
            "low_low": round(low_low, 2),
            "low_high": round(low_high, 2),
            "confidence": round(confidence, 2),
            "matches": len(matches),
            "total_patterns_checked": len(hist_patterns),
            "similarity_threshold_used": similarity_threshold,
            "current_lookback": look_back
        }
    })

@app.route("/predict_candle_flexible", methods=["POST"])
def predict_candle_flexible():
    """Flexible prediction that tries multiple lookback lengths"""
    payload = request.get_json() or {}
    symbol = payload.get("symbol", "BTC/USDT").upper()
    timeframe = payload.get("timeframe", "4h")
    expander = float(payload.get("expander", 1.33))
    
    # Try different lookback values in order
    lookback_options = [50, 100, 200, 500, 1000, 2000, 3000]
    similarity_thresholds = [0.1, 0.2, 0.3, 0.5, 1.0, 1.5, 2.0]
    
    results = []
    
    for look_back, threshold in zip(lookback_options, similarity_thresholds):
        try:
            # Get data for this lookback
            conn = get_conn()
            cur = conn.cursor(dictionary=True)
            cur.execute("""
                SELECT time_utc, close, high, low
                FROM ohlcv_data
                WHERE symbol = %s AND timeframe = %s
                ORDER BY time_utc DESC
                LIMIT %s
            """, (symbol, timeframe, look_back + 1))
            rows = cur.fetchall()
            cur.close()
            conn.close()
            
            if len(rows) < look_back + 1:
                continue
            
            # Compute pattern
            df_recent = pd.DataFrame(rows)
            df_recent['close'] = df_recent['close'].astype(float)
            df_recent['high'] = df_recent['high'].astype(float)
            df_recent['low'] = df_recent['low'].astype(float)
            
            current_triplets = []
            for i in range(1, len(df_recent)):
                prev_close = df_recent.iloc[i-1]['close']
                row = {
                    'Close': df_recent.iloc[i]['close'],
                    'High': df_recent.iloc[i]['high'],
                    'Low': df_recent.iloc[i]['low']
                }
                triplet = compute_triplet(row, prev_close)
                current_triplets.append(triplet)
            
            if len(current_triplets) < look_back:
                continue
            
            current_pattern = current_triplets[-look_back:]
            
            # Check if pattern table exists
            conn = get_conn()
            cur = conn.cursor()
            cur.execute(f"SHOW TABLES LIKE 'patterns_{timeframe}'")
            if not cur.fetchone():
                cur.close()
                conn.close()
                continue
            cur.close()
            conn.close()
            
            # Fetch historical patterns
            conn = get_conn()
            cur = conn.cursor(dictionary=True)
            cur.execute(f"""
                SELECT pattern_hash, pattern_string, outcomes, occurrences
                FROM patterns_{timeframe}
                ORDER BY occurrences DESC
                LIMIT 1000
            """)
            hist_patterns = cur.fetchall()
            cur.close()
            conn.close()
            
            if not hist_patterns:
                continue
            
            # Find similar patterns
            matches = find_similar_patterns_fuzzy(
                current_pattern, 
                hist_patterns, 
                timeframe, 
                50, 
                threshold
            )
            
            if matches and len(matches) >= 3:
                # Calculate prediction
                total_weight = 0
                weighted_close = 0
                weighted_high = 0
                weighted_low = 0
                
                for m in matches:
                    similarity_weight = 1.0 / (1.0 + m['dist'])
                    pattern_weight = min(m['weights']['close'], m['weights']['high'], m['weights']['low'])
                    match_weight = similarity_weight * pattern_weight * m['occurrences']
                    
                    avg_close = sum(o[0] for o in m['outcomes']) / len(m['outcomes'])
                    avg_high = sum(o[1] for o in m['outcomes']) / len(m['outcomes'])
                    avg_low = sum(o[2] for o in m['outcomes']) / len(m['outcomes'])
                    
                    weighted_close += avg_close * match_weight
                    weighted_high += avg_high * match_weight
                    weighted_low += avg_low * match_weight
                    total_weight += match_weight
                
                if total_weight > 0:
                    pct_close = weighted_close / total_weight
                    pct_high = weighted_high / total_weight
                    pct_low = weighted_low / total_weight
                    
                    results.append({
                        "lookback": look_back,
                        "matches": len(matches),
                        "threshold": threshold,
                        "pct_close": round(pct_close, 2),
                        "pct_high": round(pct_high, 2),
                        "pct_low": round(pct_low, 2)
                    })
                
                if len(results) >= 3:
                    break
        
        except Exception as e:
            print(f"Error trying lookback {look_back}: {e}")
            continue
    
    if not results:
        return jsonify({"success": False, "error": "No matches found with any lookback length"})
    
    # Average the results
    avg_close = sum(r["pct_close"] for r in results) / len(results)
    avg_high = sum(r["pct_high"] for r in results) / len(results)
    avg_low = sum(r["pct_low"] for r in results) / len(results)
    
    return jsonify({
        "success": True,
        "prediction": {
            "pct_close": round(avg_close, 2),
            "pct_high": round(avg_high, 2),
            "pct_low": round(avg_low, 2),
            "confidence": round((len(results) / 7) * 100, 2),  # 7 is total lookback options
            "lookbacks_used": [r["lookback"] for r in results],
            "matches_per_lookback": [r["matches"] for r in results],
            "total_results": len(results)
        }
    })

@app.route("/debug_patterns", methods=["POST"])
def debug_patterns():
    """Debug endpoint to see pattern matching issues"""
    payload = request.get_json() or {}
    symbol = payload.get("symbol", "BTC/USDT").upper()
    timeframe = payload.get("timeframe", "4h")
    look_back = int(payload.get("look_back", 50))
    
    # Get current pattern
    conn = get_conn()
    cur = conn.cursor(dictionary=True)
    cur.execute("""
        SELECT close, high, low
        FROM ohlcv_data
        WHERE symbol = %s AND timeframe = %s
        ORDER BY time_utc DESC
        LIMIT %s
    """, (symbol, timeframe, look_back + 1))
    rows = cur.fetchall()
    cur.close()
    conn.close()
    
    if len(rows) < look_back + 1:
        return jsonify({"success": False, "error": f"Not enough data for debug: {len(rows)} rows"})
    
    # Compute current pattern
    df_recent = pd.DataFrame(rows)
    df_recent['close'] = df_recent['close'].astype(float)
    df_recent['high'] = df_recent['high'].astype(float)
    df_recent['low'] = df_recent['low'].astype(float)
    
    current_triplets = []
    for i in range(1, len(df_recent)):
        prev_close = df_recent.iloc[i-1]['close']
        row = {
            'Close': df_recent.iloc[i]['close'],
            'High': df_recent.iloc[i]['high'],
            'Low': df_recent.iloc[i]['low']
        }
        triplet = compute_triplet(row, prev_close)
        current_triplets.append(triplet)
    
    if len(current_triplets) < look_back:
        return jsonify({"success": False, "error": "Not enough triplets"})
    
    current_pattern = current_triplets[-look_back:]
    
    # Check database
    conn = get_conn()
    cur = conn.cursor(dictionary=True)
    
    # Count patterns
    cur.execute(f"SELECT COUNT(*) as count FROM patterns_{timeframe}")
    pattern_count = cur.fetchone()['count']
    
    # Get sample patterns
    cur.execute(f"""
        SELECT pattern_string, outcomes, occurrences 
        FROM patterns_{timeframe} 
        ORDER BY occurrences DESC 
        LIMIT 5
    """)
    sample_patterns = cur.fetchall()
    
    # Get weight counts
    weight_counts = {}
    for pred_type in ['close', 'high', 'low']:
        cur.execute(f"SELECT COUNT(*) as count FROM weights_{pred_type}_{timeframe}")
        weight_counts[pred_type] = cur.fetchone()['count']
    
    cur.close()
    conn.close()
    
    # Analyze current pattern
    avg_close = sum(t[0] for t in current_pattern) / len(current_pattern)
    avg_high = sum(t[1] for t in current_pattern) / len(current_pattern)
    avg_low = sum(t[2] for t in current_pattern) / len(current_pattern)
    
    return jsonify({
        "success": True,
        "symbol": symbol,
        "timeframe": timeframe,
        "lookback_requested": look_back,
        "current_pattern_stats": {
            "length": len(current_pattern),
            "avg_pct_close": round(avg_close, 4),
            "avg_pct_high": round(avg_high, 4),
            "avg_pct_low": round(avg_low, 4),
            "min_pct_close": round(min(t[0] for t in current_pattern), 4),
            "max_pct_close": round(max(t[0] for t in current_pattern), 4),
            "first_3_triplets": current_pattern[:3],
            "last_3_triplets": current_pattern[-3:]
        },
        "database_stats": {
            "total_patterns": pattern_count,
            "weights_close": weight_counts['close'],
            "weights_high": weight_counts['high'],
            "weights_low": weight_counts['low']
        },
        "sample_patterns": [
            {
                "length": len(string_to_pattern(p['pattern_string'])),
                "occurrences": p['occurrences'],
                "avg_pct_close": round(sum(t[0] for t in string_to_pattern(p['pattern_string'])) / len(string_to_pattern(p['pattern_string'])), 4),
                "first_3_triplets": string_to_pattern(p['pattern_string'])[:3] if string_to_pattern(p['pattern_string']) else []
            }
            for p in sample_patterns
        ]
    })

# ========= REAL-TIME WEBSOCKETS =========
def close_websockets():
    """Close all WebSocket connections"""
    global binance_ws, bybit_ws, okx_ws, gateio_ws
    
    websockets_to_close = [
        ("binance", binance_ws),
        ("bybit", bybit_ws),
        ("okx", okx_ws),
        ("gateio", gateio_ws)
    ]
    
    for name, ws in websockets_to_close:
        if ws:
            try:
                ws.close()
                print(f"Closed {name} WebSocket")
            except Exception as e:
                print(f"Error closing {name} WebSocket: {e}")
    
    # Clear all WebSocket references
    binance_ws = bybit_ws = okx_ws = gateio_ws = None
    
    # Small delay to ensure WebSockets are properly closed
    time.sleep(0.5)

def start_websockets():
    """Start WebSocket connections for current symbol"""
    global binance_ws, bybit_ws, okx_ws, gateio_ws
    
    # Ensure old WebSockets are closed
    close_websockets()
    
    symbol = real_time_data["current_symbol"]
    print(f"Starting WebSockets for symbol: {symbol}")
    
    # Convert symbol for each exchange
    binance_pair = symbol.replace('/', '').lower()
    bybit_pair = symbol.replace('/', '').upper()
    okx_pair = symbol.replace('/', '-').upper()
    gateio_pair = symbol.replace('/', '_').upper()

    def ws_thread(exchange_name, url, on_open=None, on_message=None):
        """WebSocket thread with symbol verification"""
        thread_symbol = real_time_data["current_symbol"]  # Capture symbol for this thread
        
        while True:
            try:
                # Check if symbol has changed (thread should exit)
                if real_time_data["current_symbol"] != thread_symbol:
                    print(f"Symbol changed from {thread_symbol} to {real_time_data['current_symbol']}. Stopping {exchange_name} WebSocket thread.")
                    break
                
                print(f"Starting {exchange_name} WebSocket for {thread_symbol}...")
                
                # Create WebSocket
                ws = websocket.WebSocketApp(
                    url,
                    on_open=on_open,
                    on_message=on_message,
                    on_error=lambda ws, error: print(f"{exchange_name} WebSocket error: {error}"),
                    on_close=lambda ws, close_status_code, close_msg: print(f"{exchange_name} WebSocket closed: {close_msg}")
                )
                
                # Assign to correct global variable
                if exchange_name == 'binance':
                    global binance_ws
                    binance_ws = ws
                elif exchange_name == 'bybit':
                    global bybit_ws
                    bybit_ws = ws
                elif exchange_name == 'okx':
                    global okx_ws
                    okx_ws = ws
                elif exchange_name == 'gateio':
                    global gateio_ws
                    gateio_ws = ws
                
                # Run WebSocket
                ws.run_forever(ping_interval=20, ping_timeout=10)
                
            except Exception as e:
                print(f"{exchange_name} WS connection error: {e}")
                
                # Check if symbol has changed while reconnecting
                if real_time_data["current_symbol"] != thread_symbol:
                    print(f"Symbol changed from {thread_symbol} to {real_time_data['current_symbol']}. Stopping {exchange_name} WebSocket thread.")
                    break
                    
                time.sleep(5)  # Wait before reconnecting

    # Start WebSocket threads
    # Binance
    binance_url = f"wss://stream.binance.com:9443/stream?streams={binance_pair}@depth20@100ms/{binance_pair}@trade"
    threading.Thread(target=ws_thread, args=('binance', binance_url, None, on_message_binance), daemon=True).start()
    
    # Bybit
    bybit_url = "wss://stream.bybit.com/v5/public/spot"
    def bybit_open(ws):
        subscribe_msg = {
            "op": "subscribe",
            "args": [
                f"orderbook.50.{bybit_pair}",
                f"publicTrade.{bybit_pair}"
            ]
        }
        ws.send(json.dumps(subscribe_msg))
        print(f"Bybit subscribed to {bybit_pair}")
    threading.Thread(target=ws_thread, args=('bybit', bybit_url, bybit_open, on_message_bybit), daemon=True).start()
    
    # OKX
    okx_url = "wss://ws.okx.com:8443/ws/v5/public"
    def okx_open(ws):
        ws.send(json.dumps({"op": "subscribe", "args": [
            {"channel": "books5", "instId": okx_pair},
            {"channel": "trades", "instId": okx_pair}
        ]}))
        print(f"OKX subscribed to {okx_pair}")
    threading.Thread(target=ws_thread, args=('okx', okx_url, okx_open, on_message_okx), daemon=True).start()
    
    # Gate.io
    gateio_url = "wss://api.gateio.ws/ws/v4/"
    def gateio_open(ws):
        timestamp = int(time.time())
        # Subscribe to order book
        orderbook_sub = {
            "time": timestamp,
            "channel": "spot.order_book",
            "event": "subscribe",
            "payload": [gateio_pair, "20", "100ms"]
        }
        ws.send(json.dumps(orderbook_sub))
        
        # Subscribe to trades
        trades_sub = {
            "time": timestamp,
            "channel": "spot.trades",
            "event": "subscribe",
            "payload": [gateio_pair]
        }
        ws.send(json.dumps(trades_sub))
        print(f"Gate.io subscribed to {gateio_pair}")
    threading.Thread(target=ws_thread, args=('gateio', gateio_url, gateio_open, on_message_gateio), daemon=True).start()
    
    print(f"✅ All WebSockets started for {symbol}")

def on_message_binance(ws, message):
    try:
        # Verify we're still tracking the right symbol
        current_symbol = real_time_data["current_symbol"].replace('/', '')
        data = json.loads(message)
        
        if 'stream' in data:
            stream_name = data['stream']
            # Only process if this is for our current symbol
            if current_symbol.lower() not in stream_name:
                return  # Skip messages for other symbols
            
            if data['stream'].endswith('@depth20@100ms'):
                book = data['data']
                update_order_book("binance", book['bids'], book['asks'])
            elif data['stream'].endswith('@trade'):
                trade = data['data']
                side = 'b' if not trade.get('m') else 's'  # m=true means seller initiated
                process_trade("binance", {
                    "price": float(trade['p']),
                    "volume": float(trade['q']),
                    "timestamp": trade['T'] / 1000,
                    "side": side
                })
    except Exception as e:
        print(f"Binance message error: {e}")

def on_message_bybit(ws, message):
    try:
        # Verify we're still tracking the right symbol
        current_symbol = real_time_data["current_symbol"].replace('/', '')
        data = json.loads(message)
        
        # Check for successful subscription
        if 'success' in data and data['success']:
            print(f"Bybit subscription success: {data.get('ret_msg', '')}")
            return
        
        if 'topic' in data:
            topic = data['topic']
            
            # Only process if this is for our current symbol
            if current_symbol.upper() not in topic:
                return  # Skip messages for other symbols
            
            # Order book updates
            if 'orderbook.50.' in topic:
                book_data = data.get('data', {})
                if 'b' in book_data and 'a' in book_data:
                    bids = book_data.get('b', [])
                    asks = book_data.get('a', [])
                    update_order_book("bybit", bids, asks)
            
            # Trade updates
            elif 'publicTrade.' in topic:
                trades = data.get('data', [])
                if isinstance(trades, list):
                    for t in trades:
                        # Bybit V5 uses different field names
                        side = 'b' if t.get('S') == 'Buy' else 's'
                        price = t.get('p')
                        volume = t.get('v')
                        timestamp = t.get('T', time.time() * 1000) / 1000  # Convert ms to seconds
                        
                        if price and volume:
                            process_trade("bybit", {
                                "price": float(price),
                                "volume": float(volume),
                                "timestamp": timestamp,
                                "side": side
                            })
    except Exception as e:
        print(f"Bybit message error: {e}")

def on_message_okx(ws, message):
    try:
        # Verify we're still tracking the right symbol
        current_symbol = real_time_data["current_symbol"].replace('/', '-')
        data = json.loads(message)
        
        # Handle pong response for ping
        if data.get('event') == 'subscribe':
            print(f"OKX subscription success: {data.get('arg', {}).get('channel')}")
            return
        
        if 'arg' in data and 'data' in data:
            channel = data['arg']['channel']
            inst_id = data['arg'].get('instId', '')
            
            # Only process if this is for our current symbol
            if current_symbol.upper() not in inst_id:
                return  # Skip messages for other symbols
            
            if channel == 'books5':
                book = data['data'][0]
                bids = book.get('bids', [])
                asks = book.get('asks', [])
                update_order_book("okx", bids, asks)
                
            elif channel == 'trades':
                for t in data['data']:
                    side = 'b' if t.get('side') == 'buy' else 's'
                    price = t.get('px')
                    volume = t.get('sz')
                    timestamp = int(t.get('ts', time.time() * 1000000)) / 1000000  # Convert to seconds
                    
                    if price and volume:
                        process_trade("okx", {
                            "price": float(price),
                            "volume": float(volume),
                            "timestamp": timestamp,
                            "side": side
                        })
    except Exception as e:
        print(f"OKX message error: {e}")

def on_message_gateio(ws, message):
    try:
        # Verify we're still tracking the right symbol
        current_symbol = real_time_data["current_symbol"].replace('/', '_')
        data = json.loads(message)
        
        # Handle subscription response
        if data.get('event') == 'subscribe':
            print(f"Gate.io subscription success: {data.get('channel')}")
            return
        
        # Handle order book updates
        if data.get('channel') == 'spot.order_book' and data.get('event') == 'update':
            result = data.get('result', {})
            
            # Only process if this is for our current symbol
            channel_symbol = result.get('s', '')
            if current_symbol.upper() not in channel_symbol:
                return  # Skip messages for other symbols
            
            # Gate.io uses 'bids' and 'asks' (not 'b' and 'a')
            bids = result.get('bids', [])
            asks = result.get('asks', [])
            
            # Format bids and asks as list of [price, quantity]
            formatted_bids = []
            formatted_asks = []
            
            if bids and isinstance(bids, list):
                for bid in bids:
                    if len(bid) >= 2:
                        try:
                            price = float(bid[0]) if isinstance(bid[0], (int, float, str)) else 0
                            quantity = float(bid[1]) if isinstance(bid[1], (int, float, str)) else 0
                            if price > 0 and quantity > 0:
                                formatted_bids.append([price, quantity])
                        except (ValueError, TypeError):
                            continue
            
            if asks and isinstance(asks, list):
                for ask in asks:
                    if len(ask) >= 2:
                        try:
                            price = float(ask[0]) if isinstance(ask[0], (int, float, str)) else 0
                            quantity = float(ask[1]) if isinstance(ask[1], (int, float, str)) else 0
                            if price > 0 and quantity > 0:
                                formatted_asks.append([price, quantity])
                        except (ValueError, TypeError):
                            continue
            
            if formatted_bids or formatted_asks:
                update_order_book("gateio", formatted_bids, formatted_asks)
        
        # Handle trade updates
        elif data.get('channel') == 'spot.trades' and data.get('event') == 'update':
            result = data.get('result', {})
            
            # Handle both single trade and list of trades
            trades = []
            if isinstance(result, dict):
                trades = [result]
            elif isinstance(result, list):
                trades = result
            
            for trade in trades:
                if isinstance(trade, dict):
                    # Only process if this is for our current symbol
                    trade_symbol = trade.get('currency_pair', '')
                    if current_symbol.upper() not in trade_symbol:
                        continue  # Skip trades for other symbols
                    
                    side = 'b' if trade.get('side') == 'buy' else 's'
                    price = trade.get('price')
                    amount = trade.get('amount')
                    
                    # Handle timestamp - Gate.io uses create_time_ms or create_time
                    try:
                        if 'create_time_ms' in trade:
                            # Convert to float first, then divide
                            timestamp_ms = float(trade['create_time_ms'])
                        elif 'create_time' in trade:
                            # Check if it's already in seconds or milliseconds
                            create_time = trade['create_time']
                            if isinstance(create_time, (int, float)):
                                timestamp_ms = float(create_time)
                                # If create_time is less than 10000000000, it's likely in seconds
                                if timestamp_ms < 10000000000:
                                    timestamp_ms = timestamp_ms * 1000
                            elif isinstance(create_time, str):
                                timestamp_ms = float(create_time)
                                if timestamp_ms < 10000000000:
                                    timestamp_ms = timestamp_ms * 1000
                            else:
                                timestamp_ms = time.time() * 1000
                        else:
                            timestamp_ms = time.time() * 1000
                        
                        timestamp = timestamp_ms / 1000  # Convert to seconds
                    except (ValueError, TypeError) as e:
                        print(f"Gate.io timestamp error: {e}, using current time")
                        timestamp = time.time()
                    
                    if price and amount:
                        try:
                            process_trade("gateio", {
                                "price": float(price),
                                "volume": float(amount),
                                "timestamp": timestamp,
                                "side": side
                            })
                        except (ValueError, TypeError) as e:
                            print(f"Gate.io trade processing error: {e}")
                        
    except Exception as e:
        print(f"Gate.io message error: {e}")
        # Print the raw message for debugging
        try:
            print(f"Raw Gate.io message: {message[:200]}...")
        except:
            pass

def process_trade(exchange, trade):
    try:
        price = trade.get('price', 0)
        volume = trade.get('volume', 0)
        timestamp = trade.get('timestamp', time.time())
        side = trade.get('side', 'b')
        
        # Convert to float safely
        try:
            if not isinstance(price, (int, float)):
                price = float(price)
            if not isinstance(volume, (int, float)):
                volume = float(volume)
            if not isinstance(timestamp, (int, float)):
                timestamp = float(timestamp)
        except (ValueError, TypeError):
            # Skip invalid trade
            return
        
        # Add trade to the list
        real_time_data["trades"].append([price, volume, timestamp, side, exchange])
        
        # Keep only last 1000 trades
        if len(real_time_data["trades"]) > 1000:
            real_time_data["trades"] = real_time_data["trades"][-1000:]
        
        # Recalculate metrics
        calculate_realtime_metrics()
        
    except Exception as e:
        print(f"Process trade error for {exchange}: {e}")

def update_order_book(exchange, bids, asks):
    try:
        # Format and validate bids
        formatted_bids = []
        if bids and isinstance(bids, list):
            for bid in bids:
                if isinstance(bid, list) and len(bid) >= 2:
                    try:
                        # Convert to float safely
                        price = float(bid[0]) if isinstance(bid[0], (int, float, str)) else 0
                        quantity = float(bid[1]) if isinstance(bid[1], (int, float, str)) else 0
                        if price > 0 and quantity > 0:
                            formatted_bids.append([price, quantity])
                    except (ValueError, TypeError) as e:
                        # Silently skip invalid entries
                        continue
        
        # Format and validate asks
        formatted_asks = []
        if asks and isinstance(asks, list):
            for ask in asks:
                if isinstance(ask, list) and len(ask) >= 2:
                    try:
                        # Convert to float safely
                        price = float(ask[0]) if isinstance(ask[0], (int, float, str)) else 0
                        quantity = float(ask[1]) if isinstance(ask[1], (int, float, str)) else 0
                        if price > 0 and quantity > 0:
                            formatted_asks.append([price, quantity])
                    except (ValueError, TypeError) as e:
                        # Silently skip invalid entries
                        continue
        
        # Sort bids descending and asks ascending
        formatted_bids = sorted(formatted_bids, key=lambda x: x[0], reverse=True)[:20]
        formatted_asks = sorted(formatted_asks, key=lambda x: x[0])[:20]
        
        # Update order book
        if formatted_bids or formatted_asks:
            real_time_data["order_book"][exchange]["bids"] = formatted_bids
            real_time_data["order_book"][exchange]["asks"] = formatted_asks
            
            # Recalculate metrics
            calculate_realtime_metrics()
            
    except Exception as e:
        print(f"Update order book error for {exchange}: {e}")

def calculate_realtime_metrics():
    try:
        total_buy = 0
        total_sell = 0
        
        # Calculate total buy and sell volume across all exchanges
        for ex_book in real_time_data["order_book"].values():
            total_buy += sum(q for _, q in ex_book["bids"])
            total_sell += sum(q for _, q in ex_book["asks"])
        
        real_time_data["total_buy_volume"] = total_buy
        real_time_data["total_sell_volume"] = total_sell
        
        # Calculate order flow imbalance
        total = total_buy + total_sell + 1e-8
        real_time_data["order_flow_imbalance"] = (total_buy - total_sell) / total
        
        # Calculate VWAP from recent trades (last 5 minutes)
        now = time.time()
        recent_trades = [t for t in real_time_data["trades"] if now - t[2] < 300]
        
        if recent_trades:
            vwap_sum = sum(t[0] * t[1] for t in recent_trades)
            vol_sum = sum(t[1] for t in recent_trades)
            real_time_data["vwap"] = vwap_sum / vol_sum if vol_sum > 0 else None
            real_time_data["current_price"] = recent_trades[-1][0] if recent_trades else 0.0
        else:
            real_time_data["vwap"] = None
            real_time_data["current_price"] = 0.0
        
        # Calculate predicted price based on order flow imbalance
        if real_time_data["current_price"]:
            real_time_data["predicted_price"] = real_time_data["current_price"] * (1 + 0.005 * real_time_data["order_flow_imbalance"])
        else:
            real_time_data["predicted_price"] = 0.0
        
        real_time_data["last_update"] = time.time()
        
    except Exception as e:
        print(f"Calculate realtime metrics error: {e}")

# ========= ENDPOINTS =========
@app.route('/realtime_data')
def realtime_data():
    return jsonify(real_time_data)

@app.route('/set_symbol', methods=['POST'])
def set_symbol():
    try:
        data = request.json
        new_symbol = data.get('symbol', 'BTC/USDT').upper()
        
        if new_symbol != real_time_data["current_symbol"]:
            print(f"Changing symbol from {real_time_data['current_symbol']} to {new_symbol}")
            
            # FIRST: Stop all WebSockets
            close_websockets()
            
            # SECOND: Update the current symbol
            real_time_data["current_symbol"] = new_symbol
            
            # THIRD: Clear all existing data
            for ex in real_time_data["order_book"]:
                real_time_data["order_book"][ex] = {"bids": [], "asks": []}
            real_time_data["trades"].clear()
            real_time_data["vwap"] = None
            real_time_data["current_price"] = 0.0
            real_time_data["total_buy_volume"] = 0.0
            real_time_data["total_sell_volume"] = 0.0
            real_time_data["order_flow_imbalance"] = 0.0
            real_time_data["predicted_price"] = 0.0
            real_time_data["last_update"] = 0
            
            # FOURTH: Start WebSockets with new symbol
            start_websockets()
            
            # Give WebSockets time to connect
            time.sleep(2)
            
            print(f"✅ Symbol changed to {new_symbol}. WebSockets restarted.")
            
        return jsonify({"success": True, "symbol": new_symbol})
    except Exception as e:
        print(f"Set symbol error: {e}")
        return jsonify({"success": False, "error": str(e)}), 500

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
        if from_year:
            from_year = int(from_year)
            since = int(datetime(from_year, 1, 1).timestamp() * 1000)
        else:
            since = None
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
            if until:
                ohlcv = [c for c in ohlcv if c[0] < until]
            if not ohlcv:
                break
            all_ohlcv.extend(ohlcv)
            total_fetched += len(ohlcv)
            df_chunk = pd.DataFrame(ohlcv, columns=["Timestamp", "Open", "High", "Low", "Close", "Volume"])
            df_chunk["Time (UTC)"] = pd.to_datetime(df_chunk["Timestamp"], unit="ms")
            df_chunk = df_chunk.sort_values("Time (UTC)").reset_index(drop=True)
            df_chunk["volume_diff"] = df_chunk["Volume"].diff().fillna(0.0)
            save_ohlcv(df_chunk, symbol, timeframe)
            since = ohlcv[-1][0] + 1
            time.sleep(0.5)
            if total_fetched > 1_000_000:
                break
        if not all_ohlcv:
            return jsonify({"success": False, "error": "No data from exchange"}), 400
        df = pd.DataFrame(all_ohlcv, columns=["Timestamp", "Open", "High", "Low", "Close", "Volume"])
        df["Time (UTC)"] = pd.to_datetime(df["Timestamp"], unit="ms")
        df = df.sort_values("Time (UTC)").reset_index(drop=True)
        df["volume_diff"] = df["Volume"].diff().fillna(0.0)
        return jsonify({
            "success": True,
            "message": f"Fetched and saved {total_fetched} candles for {symbol} (all available in range)",
            "data": df[["Time (UTC)", "Open", "High", "Low", "Close", "Volume", "volume_diff"]].to_dict(orient="records")
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
        SELECT time_utc, open, high, low, close, volume, volume_diff
        FROM ohlcv_data
        WHERE symbol=%s AND timeframe=%s
        ORDER BY time_utc DESC
        LIMIT 1000
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
        "volume": float(r["volume"]),
        "volume_diff": float(r["volume_diff"]) if r["volume_diff"] is not None else 0.0
    } for r in rows]
    return jsonify({"success": True, "data": data})

def add_all_indicators(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    out = df.copy()
    if "Time (UTC)" in out.columns:
        time_col = "Time (UTC)"
    elif "Timestamp" in out.columns:
        out["Time (UTC)"] = pd.to_datetime(out["Timestamp"], unit="ms")
        time_col = "Time (UTC)"
    else:
        print("[WARNING] No time column found in DataFrame for indicators")
        time_col = None
    if time_col:
        out = out.sort_values(time_col).drop_duplicates(subset=time_col, keep="last")
        out.set_index(time_col, inplace=True)
    close = out["Close"]
    high = out["High"]
    low = out["Low"]
    volume = out["Volume"]
    out["RSI"] = ta.rsi(close, length=14)
    stochrsi = ta.stochrsi(close, length=14, rsi_length=14, k=3, d=3)
    if stochrsi is not None and not stochrsi.empty:
        out["STOCHRSI_K"] = stochrsi.iloc[:, 0]
        out["STOCHRSI_D"] = stochrsi.iloc[:, 1]
    macd = ta.macd(close, fast=12, slow=26, signal=9)
    if macd is not None and not macd.empty:
        out["MACD"] = macd.iloc[:, 0]
        out["MACD_SIGNAL"] = macd.iloc[:, 1]
        out["MACD_HIST"] = macd.iloc[:, 2]
    out["EMA20"] = ta.ema(close, length=20)
    out["EMA50"] = ta.ema(close, length=50)
    out["EMA100"] = ta.ema(close, length=100)
    out["EMA200"] = ta.ema(close, length=200)
    bb = ta.bbands(close, length=20, std=2)
    if bb is not None and not bb.empty:
        out["BB_LOW"] = bb.iloc[:, 0]
        out["BB_MID"] = bb.iloc[:, 1]
        out["BB_UPPER"] = bb.iloc[:, 2]
        out["BB_WIDTH"] = (out["BB_UPPER"] - out["BB_LOW"]) / out["BB_MID"]
    adx = ta.adx(high, low, close, length=14)
    if adx is not None and not adx.empty:
        out["ADX"] = adx.iloc[:, 0]
    out["CCI"] = ta.cci(high, low, close, length=20)
    out["OBV"] = ta.obv(close, volume)
    out["ATR"] = ta.atr(high, low, close, length=14)
    try:
        cdl = ta.cdl_pattern(out["Open"], high, low, close,
                             name=["engulfing", "doji", "hammer", "shootingstar"])
        if cdl is not None and not cdl.empty:
            for col in cdl.columns:
                out[col] = cdl[col]
    except Exception:
        pass
    try:
        out["VWAP"] = ta.vwap(high=high, low=low, close=close, volume=volume)
    except Exception as e:
        print(f"[VWAP] Failed: {e}")
        out["VWAP"] = pd.NA
    try:
        st = ta.supertrend(high=high, low=low, close=close, length=10, multiplier=3)
        if st is not None and not st.empty:
            out["SUPERTREND"] = st.iloc[:, 0]
            out["SUPERTREND_DIR"] = st.iloc[:, 1]
    except Exception:
        pass
    try:
        dc = ta.donchian(high=high, low=low, lower_length=20, upper_length=20)
        if dc is not None and not dc.empty:
            out["DONCHIAN_LOW"] = dc.iloc[:, 0]
            out["DONCHIAN_HIGH"] = dc.iloc[:, 2]
    except Exception:
        pass
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
    score = 50
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
        df = df.sort_values("Time (UTC)").reset_index(drop=True)
        df["volume_diff"] = df["Volume"].diff().fillna(0.0)
        
        df_ind = add_all_indicators(df)
        sig = generate_signal_summary(df_ind)
        
        if df_ind.empty:
            return jsonify({"success": False, "error": "No valid data after processing"}), 400
            
        last = df_ind.iloc[-1]
        
        response = {
            "success": True,
            "symbol": symbol,
            "timeframe": timeframe,
            "last_candle": {
                "time_utc": last.name.strftime("%Y-%m-%d %H:%M:%S") if isinstance(last.name, pd.Timestamp) else str(last.name),
                "open": float(last["Open"]),
                "high": float(last["High"]),
                "low": float(last["Low"]),
                "close": float(last["Close"]),
                "volume": float(last["Volume"]),
            },
            "indicators": {
                "rsi": float(sig["rsi"]) if sig["rsi"] is not None else None,
                "macd": float(sig["macd"]) if sig["macd"] is not None else None,
                "macd_signal": float(sig["macd_signal"]) if sig["macd_signal"] is not None else None,
                "ema20": float(sig["ema20"]) if sig["ema20"] is not None else None,
                "ema50": float(sig["ema50"]) if sig["ema50"] is not None else None,
                "ema100": float(sig["ema100"]) if sig["ema100"] is not None else None,
                "ema200": float(sig["ema200"]) if sig["ema200"] is not None else None,
            },
            "signal": sig["label"],
            "bias": sig["bias"],
            "score": sig["score"],
            "reasons": sig["reasons"]
        }
        return jsonify(response)
    except Exception as e:
        import traceback
        print("Error in /analyze_symbol:", str(e))
        print(traceback.format_exc())
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
            df = df.sort_values("Time (UTC)").reset_index(drop=True)
            df["volume_diff"] = df["Volume"].diff().fillna(0.0)
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

# ========= DEBUG & VERIFICATION ENDPOINTS =========
@app.route("/debug_exchanges", methods=["GET"])
def debug_exchanges():
    """Debug endpoint to check WebSocket connections"""
    status = {
        "current_symbol": real_time_data["current_symbol"],
        "last_update": real_time_data["last_update"],
        "last_update_time": datetime.fromtimestamp(real_time_data["last_update"]).strftime("%Y-%m-%d %H:%M:%S") if real_time_data["last_update"] > 0 else "Never",
        "exchanges": {}
    }
    
    for exchange in ["binance", "bybit", "okx", "gateio"]:
        book = real_time_data["order_book"][exchange]
        status["exchanges"][exchange] = {
            "bids_count": len(book["bids"]),
            "asks_count": len(book["asks"]),
            "total_buy": sum(q for _, q in book["bids"]),
            "total_sell": sum(q for _, q in book["asks"]),
            "has_data": len(book["bids"]) > 0 or len(book["asks"]) > 0
        }
    
    # Count trades per exchange
    trade_counts = {}
    for trade in real_time_data["trades"][-100:]:  # Last 100 trades
        exchange = trade[4]
        trade_counts[exchange] = trade_counts.get(exchange, 0) + 1
    
    status["recent_trades"] = trade_counts
    status["total_trades"] = len(real_time_data["trades"])
    
    return jsonify(status)

@app.route('/verify_symbol', methods=['GET'])
def verify_symbol():
    """Verify current symbol and WebSocket status"""
    symbol = real_time_data["current_symbol"]
    
    status = {
        "current_symbol": symbol,
        "last_update": real_time_data["last_update"],
        "last_update_time": datetime.fromtimestamp(real_time_data["last_update"]).strftime("%Y-%m-%d %H:%M:%S") if real_time_data["last_update"] > 0 else "Never",
        "exchanges": {}
    }
    
    for exchange in ["binance", "bybit", "okx", "gateio"]:
        book = real_time_data["order_book"][exchange]
        status["exchanges"][exchange] = {
            "bids": len(book["bids"]),
            "asks": len(book["asks"]),
            "has_data": len(book["bids"]) > 0 or len(book["asks"]) > 0,
            "top_bid": book["bids"][0][0] if book["bids"] else None,
            "top_ask": book["asks"][0][0] if book["asks"] else None
        }
    
    # Count recent trades
    now = time.time()
    recent_trades = [t for t in real_time_data["trades"] if now - t[2] < 60]  # Last 60 seconds
    status["recent_trades_last_minute"] = len(recent_trades)
    status["total_trades"] = len(real_time_data["trades"])
    
    return jsonify(status)

# ========= MAIN =========
if __name__ == "__main__":
    print("🚀 SUPER BOT v4 Starting...")
    print("📊 Database: crypto_data")
    print("🌐 WebSocket: Real-time order flow enabled")
    print("🔗 API: http://0.0.0.0:8000")
    print("=" * 50)
    print("🎯 PREDICTION SYSTEM READY WITH:")
    print("  • Fuzzy pattern matching")
    print("  • Dynamic similarity thresholds")
    print("  • Windowed comparison for long patterns")
    print("  • Flexible prediction (multiple lookbacks)")
    print("  • Debug endpoint for troubleshooting")
    print("=" * 50)
    
    # Test database connection
    try:
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("SHOW TABLES")
        tables = [table[0] for table in cur.fetchall()]
        print(f"✅ Database connected. Found {len(tables)} tables.")
        
        # Check for required tables
        required_tables = ['ohlcv_data', 'patterns_1h', 'weights_close_1h']
        for table in required_tables:
            if table in tables:
                print(f"   ✓ {table} exists")
            else:
                print(f"   ⚠️ {table} missing - some features may not work")
        
        # Check pattern tables
        pattern_tables = [t for t in tables if t.startswith('patterns_')]
        if pattern_tables:
            print(f"   Found pattern tables: {', '.join(pattern_tables)}")
        else:
            print("   ⚠️ No pattern tables found - train the model first")
        
        cur.close()
        conn.close()
    except Exception as e:
        print(f"❌ Database connection failed: {e}")
        print("   Please check MySQL is running and database 'crypto_data' exists")
    
    print("\n📝 RECOMMENDED WORKFLOW:")
    print("1. Fetch data (OHLCV tab)")
    print("2. Train model (Train Bot tab)")
    print("3. Use flexible prediction or debug to test")
    print("\n⚡ Starting server...")
    
    # Start WebSockets with initial symbol
    start_websockets()
    
    # Add a small delay to let WebSockets connect
    print("⏳ Waiting for WebSocket connections to establish...")
    time.sleep(3)
    
    # Check initial WebSocket status
    print("\n🔍 Initial WebSocket status:")
    for exchange in ["binance", "bybit", "okx", "gateio"]:
        book = real_time_data["order_book"][exchange]
        if book["bids"] or book["asks"]:
            print(f"   {exchange}: ✓ Connected")
        else:
            print(f"   {exchange}: ⚠️ Waiting for data...")
    
    print("\n✅ Server ready! Use /verify_symbol endpoint to check WebSocket status.")
    print("✅ Use /set_symbol endpoint to change live tracking symbol.")
    
    app.run(host="0.0.0.0", port=8000, debug=False, threaded=True)