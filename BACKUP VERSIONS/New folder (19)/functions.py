# ========= DB HELPERS =========
# New Function for checking duplicate candles start
from db.connection import get_conn
from datetime import datetime, timedelta
import pandas as pd
import hashlib
import ccxt
import math
import json

def check_existing_candles(symbol, timeframe, timestamps):
    """
    Check which timestamps already exist in the database for a given symbol and timeframe.
    Returns a set of existing timestamps.
    """
    if not timestamps:
        return set()
    
    conn = get_conn()
    cur = conn.cursor()
    
    # Convert timestamps to datetime objects for comparison
    timestamp_list = []
    for t in timestamps:
        if isinstance(t, pd.Timestamp):
            timestamp_list.append(t.to_pydatetime())
        elif isinstance(t, datetime):
            timestamp_list.append(t)
        else:
            # Try to parse as datetime
            try:
                timestamp_list.append(pd.to_datetime(t).to_pydatetime())
            except:
                continue
    
    if not timestamp_list:
        cur.close()
        conn.close()
        return set()
    
    # Create placeholders for SQL IN clause
    placeholders = ','.join(['%s'] * len(timestamp_list))
    
    sql = f"""
    SELECT time_utc 
    FROM ohlcv_data
    WHERE symbol = %s AND timeframe = %s AND time_utc IN ({placeholders})
    """
    
    params = [symbol, timeframe] + timestamp_list
    cur.execute(sql, params)
    
    existing = {row[0] for row in cur.fetchall()}
    
    cur.close()
    conn.close()
    
    return existing
# End of Helper for Duplicate Candles 
# Added Updated Function for Duplicated Cadnles  Start
def save_ohlcv(df, symbol, timeframe):
    """
    Save OHLCV data to database, skipping duplicates.
    Returns count of newly inserted candles.
    """
    if df.empty:
        return 0
    
    conn = get_conn()
    cur = conn.cursor()
    
    # Get existing timestamps from database
    timestamps = df["Time (UTC)"].tolist()
    existing_timestamps = check_existing_candles(symbol, timeframe, timestamps)
    
    sql = """
    INSERT IGNORE INTO ohlcv_data
    (symbol, timeframe, time_utc, open, high, low, close, volume, volume_diff)
    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
    """
    
    rows = []
    skipped = 0
    
    for i, r in df.iterrows():
        t = r["Time (UTC)"]
        if isinstance(t, pd.Timestamp):
            t = t.to_pydatetime()
        
        # Skip if this timestamp already exists
        if t in existing_timestamps:
            skipped += 1
            continue
        
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
    
    inserted = 0
    if rows:
        cur.executemany(sql, rows)
        inserted = cur.rowcount
        conn.commit()
    
    cur.close()
    conn.close()
    
    print(f"📊 OHLCV Save Summary: {inserted} new candles inserted, {skipped} duplicates skipped")
    return inserted
# End of Duplicated Candles Code
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



