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
def save_daily_gainers_losers(data):
    """
    Save gainers/losers data to the database, overwriting any existing records for today.
    data: list of dicts with keys: symbol, lastPrice (or price), priceChangePercent, quoteVolume
    """
    conn = get_conn()
    cur = conn.cursor()

    # 1. Delete all records for today's date
    today = datetime.now().date()
    cur.execute("DELETE FROM daily_gainers_losers WHERE DATE(fetched_at) = %s", (today,))

    # 2. Deduplicate by symbol (keep the first occurrence)
    seen = set()
    unique_data = []
    for item in data:
        sym = item['symbol']
        if sym not in seen:
            seen.add(sym)
            unique_data.append(item)

    # 3. Insert new data
    insert_sql = """
        INSERT INTO daily_gainers_losers 
        (symbol, price, price_change_percent, volume_24h, fetched_at)
        VALUES (%s, %s, %s, %s, %s)
    """
    rows = []
    for item in unique_data:
        rows.append((
            item['symbol'],
            float(item.get('lastPrice', item.get('price', 0))),
            float(item.get('priceChangePercent', 0)),
            float(item.get('quoteVolume', 0)),
            datetime.now()
        ))
    cur.executemany(insert_sql, rows)
    conn.commit()
    cur.close()
    conn.close()
    print(f"Saved {len(rows)} gainers/losers records (overwrote previous).")

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


