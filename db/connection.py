import mysql.connector

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