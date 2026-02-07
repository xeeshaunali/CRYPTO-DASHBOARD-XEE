# appp.py – SUPER BOT v4 – ENHANCED HISTORICAL OHLCV FETCHING + volume_diff
# WITH 10 EXCHANGES FOR LIVE ORDER DATA
from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
#import mysql.connector
import hashlib
# imported from functions file start
from functions import check_existing_candles
from functions import save_ohlcv
from functions import save_daily_gainers_losers
from functions import get_existing_symbols
from functions import save_new_symbols
from functions import get_exchange
from functions import pattern_to_hash
from functions import pattern_to_string
from functions import string_to_pattern
from functions import compute_triplet
from functions import pattern_distance
from functions import find_similar_patterns_fuzzy
# imported from functions file End
import ccxt
import pandas as pd
import pandas_ta as ta
from datetime import datetime, timedelta
import math
from db.connection import get_conn
import time
import json
import websocket
import threading
from io import BytesIO
import requests
import numpy as np
from typing import Dict, List, Tuple, Optional, Any
import gzip
# Assuming rotation.py exists with the function
from rotation import get_rotation_candidates_from_gainers

app = Flask(__name__)
CORS(app)

# Global real-time data with 10 exchanges
real_time_data = {
    "current_symbol": "BTC/USDT",
    "order_book": {
        "binance": {"bids": [], "asks": []},
        "bybit": {"bids": [], "asks": []},
        "okx": {"bids": [], "asks": []},
        "gateio": {"bids": [], "asks": []},
        #"kucoin": {"bids": [], "asks": []},
        "huobi": {"bids": [], "asks": []},
        "kraken": {"bids": [], "asks": []},
        "bitget": {"bids": [], "asks": []},
        "mexc": {"bids": [], "asks": []},
        "coinbase": {"bids": [], "asks": []}
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

# Global WS objects for all exchanges
binance_ws = None
bybit_ws = None
okx_ws = None
gateio_ws = None
#kucoin_ws = None
huobi_ws = None
kraken_ws = None
bitget_ws = None
mexc_ws = None
coinbase_ws = None

# # ========= DB CONNECTION =========
# def get_conn():
#     return mysql.connector.connect(
#         host="localhost",
#         user="root",
#         password="toor",
#         database="crypto_data"
#     )

# ========= DB HELPERS =========
# New Function for checking duplicate candles start


# Crypto Volume and Pattern Analyzer Start
# ========= NEW: CANDLE PATTERN & VOLUME SCANNER =========

@app.route("/scan_candle_patterns", methods=["POST"])
def scan_candle_patterns():
    """
    Scan multiple symbols for candle patterns and volume changes
    """
    payload = request.get_json() or {}
    timeframe = payload.get("timeframe", "1h")
    volume_threshold = float(payload.get("volume_threshold", 1.5))  # 1.5 = 150% volume increase
    min_volume = float(payload.get("min_volume", 100000))  # Minimum 24h volume in USD
    max_symbols = int(payload.get("max_symbols", 50))
    
    try:
        # Get active symbols from database
        conn = get_conn()
        cur = conn.cursor(dictionary=True)
        
        # Get symbols with recent data and sufficient volume
        cur.execute("""
            SELECT DISTINCT d.symbol 
            FROM ohlcv_data d
            JOIN daily_gainers_losers g ON d.symbol = g.symbol
            WHERE DATE(g.fetched_at) = CURDATE()
            AND g.volume_24h >= %s
            ORDER BY g.volume_24h DESC
            LIMIT %s
        """, (min_volume, max_symbols))
        
        symbols = [row['symbol'] for row in cur.fetchall()]
        cur.close()
        conn.close()
        
        if not symbols:
            # Fallback to top volume symbols from gainers table
            conn = get_conn()
            cur = conn.cursor(dictionary=True)
            cur.execute("""
                SELECT symbol 
                FROM daily_gainers_losers 
                WHERE DATE(fetched_at) = CURDATE()
                AND volume_24h >= %s
                ORDER BY volume_24h DESC
                LIMIT %s
            """, (min_volume, max_symbols))
            symbols = [row['symbol'] for row in cur.fetchall()]
            cur.close()
            conn.close()
        
        results = []
        
        for symbol in symbols:
            try:
                # Get recent candles for this symbol
                conn = get_conn()
                cur = conn.cursor(dictionary=True)
                cur.execute("""
                    SELECT time_utc, open, high, low, close, volume, volume_diff
                    FROM ohlcv_data
                    WHERE symbol = %s AND timeframe = %s
                    ORDER BY time_utc DESC
                    LIMIT 100
                """, (symbol, timeframe))
                rows = cur.fetchall()
                cur.close()
                conn.close()
                
                if len(rows) < 20:  # Need minimum data
                    continue
                
                # Convert to DataFrame
                df = pd.DataFrame(rows)
                df = df.sort_values('time_utc')
                
                # Calculate volume metrics
                recent_volume = df['volume'].tail(5).mean()
                previous_volume = df['volume'].iloc[-10:-5].mean()
                
                if previous_volume == 0:
                    continue
                    
                volume_ratio = recent_volume / previous_volume
                
                # Check if volume spike exceeds threshold
                if volume_ratio >= volume_threshold:
                    # Calculate OHLC metrics
                    df['open'] = df['open'].astype(float)
                    df['high'] = df['high'].astype(float)
                    df['low'] = df['low'].astype(float)
                    df['close'] = df['close'].astype(float)
                    
                    # Detect candle patterns
                    patterns = detect_candle_patterns(df)
                    
                    # Calculate volume profile
                    volume_profile = analyze_volume_profile(df)
                    
                    # Get current price from latest candle
                    current_price = float(df.iloc[-1]['close'])
                    prev_close = float(df.iloc[-2]['close'])
                    price_change = ((current_price - prev_close) / prev_close) * 100
                    
                    # Get 24h volume
                    conn = get_conn()
                    cur = conn.cursor(dictionary=True)
                    cur.execute("""
                        SELECT volume_24h 
                        FROM daily_gainers_losers 
                        WHERE symbol = %s 
                        AND DATE(fetched_at) = CURDATE()
                        LIMIT 1
                    """, (symbol,))
                    vol_row = cur.fetchone()
                    cur.close()
                    conn.close()
                    
                    results.append({
                        "symbol": symbol,
                        "current_price": current_price,
                        "price_change_24h": price_change,
                        "volume_24h": float(vol_row['volume_24h']) if vol_row else 0,
                        "volume_ratio": round(volume_ratio, 2),
                        "volume_spike": True,
                        "patterns": patterns,
                        "volume_profile": volume_profile,
                        "timeframe": timeframe,
                        "timestamp": datetime.utcnow().isoformat()
                    })
                    
            except Exception as e:
                print(f"Error analyzing {symbol}: {e}")
                continue
        
        # Sort by volume ratio (highest first)
        results.sort(key=lambda x: x['volume_ratio'], reverse=True)
        
        return jsonify({
            "success": True,
            "scanned_symbols": len(symbols),
            "matches": len(results),
            "timeframe": timeframe,
            "volume_threshold": volume_threshold,
            "results": results[:20]  # Return top 20
        })
        
    except Exception as e:
        print(f"Candle pattern scan error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"success": False, "error": str(e)}), 500

def detect_candle_patterns(df):
    """
    Detect common candle patterns
    """
    patterns = []
    
    if len(df) < 3:
        return patterns
    
    # Convert to float arrays
    opens = df['open'].astype(float).values
    highs = df['high'].astype(float).values
    lows = df['low'].astype(float).values
    closes = df['close'].astype(float).values
    
    # Check last 3 candles for patterns
    for i in range(max(0, len(df)-3), len(df)-1):
        # Bullish Engulfing
        if (closes[i] < opens[i] and  # Previous candle is bearish
            closes[i+1] > opens[i+1] and  # Current candle is bullish
            opens[i+1] < closes[i] and
            closes[i+1] > opens[i]):
            patterns.append({
                "name": "BULLISH_ENGULFING",
                "index": i,
                "strength": "medium",
                "description": "Bullish reversal pattern"
            })
        
        # Bearish Engulfing
        elif (closes[i] > opens[i] and  # Previous candle is bullish
              closes[i+1] < opens[i+1] and  # Current candle is bearish
              opens[i+1] > closes[i] and
              closes[i+1] < opens[i]):
            patterns.append({
                "name": "BEARISH_ENGULFING",
                "index": i,
                "strength": "medium",
                "description": "Bearish reversal pattern"
            })
        
        # Hammer
        if (min(opens[i], closes[i]) > lows[i] and  # Long lower shadow
            (highs[i] - max(opens[i], closes[i])) <= (max(opens[i], closes[i]) - lows[i]) * 0.3 and  # Small upper shadow
            (max(opens[i], closes[i]) - min(opens[i], closes[i])) <= (max(opens[i], closes[i]) - lows[i]) * 0.1):  # Small body
            if closes[i] > opens[i]:
                patterns.append({
                    "name": "BULLISH_HAMMER",
                    "index": i,
                    "strength": "medium",
                    "description": "Bullish reversal at bottom"
                })
        
        # Shooting Star
        if (max(opens[i], closes[i]) < highs[i] and  # Long upper shadow
            (min(opens[i], closes[i]) - lows[i]) <= (highs[i] - min(opens[i], closes[i])) * 0.3 and  # Small lower shadow
            (max(opens[i], closes[i]) - min(opens[i], closes[i])) <= (highs[i] - min(opens[i], closes[i])) * 0.1):  # Small body
            if closes[i] < opens[i]:
                patterns.append({
                    "name": "SHOOTING_STAR",
                    "index": i,
                    "strength": "medium",
                    "description": "Bearish reversal at top"
                })
        
        # Doji (indecision)
        body_size = abs(closes[i] - opens[i])
        total_range = highs[i] - lows[i]
        if total_range > 0 and body_size / total_range < 0.1:
            patterns.append({
                "name": "DOJI",
                "index": i,
                "strength": "low",
                "description": "Indecision pattern"
            })
    
    # Check for volume confirmation
    if patterns:
        volumes = df['volume'].astype(float).values
        for pattern in patterns:
            idx = pattern["index"]
            if idx > 0:
                volume_increase = volumes[idx] / volumes[idx-1] if volumes[idx-1] > 0 else 1
                pattern["volume_confirmation"] = volume_increase > 1.2
    
    return patterns

def analyze_volume_profile(df):
    """
    Analyze volume profile and trends
    """
    if len(df) < 10:
        return {}
    
    volumes = df['volume'].astype(float).values
    
    # Calculate volume metrics
    recent_avg = volumes[-5:].mean()
    previous_avg = volumes[-10:-5].mean()
    volume_trend = "neutral"
    
    if previous_avg > 0:
        ratio = recent_avg / previous_avg
        if ratio > 1.5:
            volume_trend = "strong_increasing"
        elif ratio > 1.2:
            volume_trend = "increasing"
        elif ratio < 0.8:
            volume_trend = "decreasing"
        elif ratio < 0.5:
            volume_trend = "strong_decreasing"
    
    # Volume volatility
    volume_std = np.std(volumes[-10:])
    volume_mean = np.mean(volumes[-10:])
    volume_volatility = volume_std / volume_mean if volume_mean > 0 else 0
    
    # Volume spikes
    volume_spikes = []
    for i in range(max(0, len(volumes)-5), len(volumes)-1):
        if volumes[i] > volumes[i-1] * 1.5 and volumes[i] > np.mean(volumes[max(0,i-5):i]):
            volume_spikes.append({
                "index": i,
                "ratio": volumes[i] / volumes[i-1] if volumes[i-1] > 0 else 1
            })
    
    return {
        "current_volume": float(volumes[-1]),
        "average_volume_5": float(recent_avg),
        "average_volume_10": float(previous_avg),
        "volume_trend": volume_trend,
        "volume_volatility": float(volume_volatility),
        "volume_spikes_count": len(volume_spikes),
        "last_spike_index": volume_spikes[-1]["index"] if volume_spikes else None,
        "last_spike_ratio": volume_spikes[-1]["ratio"] if volume_spikes else 1.0
    }

@app.route("/real_time_volume_analysis", methods=["POST"])
def real_time_volume_analysis():
    """
    Real-time volume analysis for a specific symbol across multiple exchanges
    """
    payload = request.get_json() or {}
    symbol = payload.get("symbol", real_time_data["current_symbol"])
    timeframe = payload.get("timeframe", "5m")
    lookback = int(payload.get("lookback", 20))
    
    try:
        # Fetch recent OHLCV data
        conn = get_conn()
        cur = conn.cursor(dictionary=True)
        cur.execute("""
            SELECT time_utc, open, high, low, close, volume, volume_diff
            FROM ohlcv_data
            WHERE symbol = %s AND timeframe = %s
            ORDER BY time_utc DESC
            LIMIT %s
        """, (symbol, timeframe, lookback))
        rows = cur.fetchall()
        cur.close()
        conn.close()
        
        if len(rows) < 5:
            return jsonify({
                "success": False,
                "error": "Insufficient data for analysis"
            }), 400
        
        df = pd.DataFrame(rows)
        df = df.sort_values('time_utc')
        
        # Calculate volume metrics
        volumes = df['volume'].astype(float).values
        volume_diffs = df['volume_diff'].astype(float).values
        
        # Volume analysis
        current_volume = float(volumes[-1])
        avg_volume_5 = float(np.mean(volumes[-5:]))
        avg_volume_10 = float(np.mean(volumes[-10:]) if len(volumes) >= 10 else np.mean(volumes))
        
        # Volume trend
        volume_trend = ""
        if avg_volume_5 > avg_volume_10 * 1.3:
            volume_trend = "STRONG_UPTREND"
        elif avg_volume_5 > avg_volume_10:
            volume_trend = "UPTREND"
        elif avg_volume_5 < avg_volume_10 * 0.7:
            volume_trend = "STRONG_DOWNTREND"
        elif avg_volume_5 < avg_volume_10:
            volume_trend = "DOWNTREND"
        else:
            volume_trend = "SIDEWAYS"
        
        # Volume spikes
        volume_spikes = []
        threshold = np.mean(volumes) * 1.5
        
        for i in range(len(volumes)):
            if volumes[i] > threshold:
                volume_spikes.append({
                    "index": i,
                    "volume": float(volumes[i]),
                    "ratio": float(volumes[i] / np.mean(volumes[max(0,i-3):i]) if i > 0 else 1)
                })
        
        # Volume vs Price analysis
        closes = df['close'].astype(float).values
        volume_price_correlation = np.corrcoef(volumes[-10:], closes[-10:])[0,1] if len(volumes) >= 10 else 0
        
        # Calculate Volume Weighted Average Price (VWAP)
        if len(df) > 0:
            typical_price = (df['high'].astype(float) + df['low'].astype(float) + df['close'].astype(float)) / 3
            vwap = (typical_price * df['volume'].astype(float)).sum() / df['volume'].astype(float).sum()
        else:
            vwap = 0
        
        # Volume-based signals
        signals = []
        if current_volume > avg_volume_5 * 1.5:
            if closes[-1] > closes[-2]:
                signals.append("HIGH_VOLUME_BREAKOUT")
            else:
                signals.append("HIGH_VOLUME_SELLOFF")
        
        if volume_diffs[-1] > np.mean(volume_diffs[-5:]) * 2:
            signals.append("VOLUME_SPIKE")
        
        # Real-time exchange volume data
        exchange_volumes = {}
        for exchange in real_time_data["order_book"].keys():
            # Estimate volume from order book depth
            bids = real_time_data["order_book"][exchange]["bids"]
            asks = real_time_data["order_book"][exchange]["asks"]
            total_depth = sum(q for _, q in bids) + sum(q for _, q in asks)
            exchange_volumes[exchange] = total_depth
        
        return jsonify({
            "success": True,
            "symbol": symbol,
            "timeframe": timeframe,
            "volume_metrics": {
                "current_volume": current_volume,
                "average_5_candles": avg_volume_5,
                "average_10_candles": avg_volume_10,
                "volume_trend": volume_trend,
                "volume_change_pct": ((current_volume - avg_volume_10) / avg_volume_10 * 100) if avg_volume_10 > 0 else 0,
                "volume_volatility": float(np.std(volumes) / np.mean(volumes) if np.mean(volumes) > 0 else 0),
                "vwap": float(vwap)
            },
            "volume_spikes": volume_spikes[-5:],  # Last 5 spikes
            "volume_price_correlation": float(volume_price_correlation),
            "signals": signals,
            "exchange_volumes": exchange_volumes,
            "analysis_timestamp": datetime.utcnow().isoformat()
        })
        
    except Exception as e:
        print(f"Real-time volume analysis error: {e}")
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/monitor_volume_changes", methods=["POST"])
def monitor_volume_changes():
    """
    Monitor volume changes for multiple symbols in real-time
    """
    payload = request.get_json() or {}
    symbols = payload.get("symbols", [])
    timeframe = payload.get("timeframe", "5m")
    alert_threshold = float(payload.get("alert_threshold", 2.0))  # 200% volume increase
    
    if not symbols:
        # Get top volume symbols
        conn = get_conn()
        cur = conn.cursor(dictionary=True)
        cur.execute("""
            SELECT symbol 
            FROM daily_gainers_losers 
            WHERE DATE(fetched_at) = CURDATE()
            ORDER BY volume_24h DESC
            LIMIT 20
        """)
        rows = cur.fetchall()
        symbols = [row['symbol'] for row in rows]
        cur.close()
        conn.close()
    
    results = []
    alerts = []
    
    for symbol in symbols:
        try:
            # Get recent volume data
            conn = get_conn()
            cur = conn.cursor(dictionary=True)
            cur.execute("""
                SELECT volume, time_utc
                FROM ohlcv_data
                WHERE symbol = %s AND timeframe = %s
                ORDER BY time_utc DESC
                LIMIT 10
            """, (symbol, timeframe))
            rows = cur.fetchall()
            cur.close()
            conn.close()
            
            if len(rows) >= 5:
                volumes = [float(row['volume']) for row in rows]
                current_volume = volumes[0]
                previous_avg = np.mean(volumes[1:5])
                
                if previous_avg > 0:
                    volume_ratio = current_volume / previous_avg
                    
                    result = {
                        "symbol": symbol,
                        "current_volume": current_volume,
                        "previous_average": previous_avg,
                        "volume_ratio": float(volume_ratio),
                        "volume_change_pct": float((volume_ratio - 1) * 100),
                        "alert": volume_ratio >= alert_threshold
                    }
                    
                    results.append(result)
                    
                    if volume_ratio >= alert_threshold:
                        alerts.append({
                            "symbol": symbol,
                            "volume_ratio": float(volume_ratio),
                            "current_volume": current_volume,
                            "timestamp": datetime.utcnow().isoformat(),
                            "message": f"Volume spike detected: {volume_ratio:.1f}x average"
                        })
        
        except Exception as e:
            print(f"Error monitoring {symbol}: {e}")
            continue
    
    # Sort by volume ratio
    results.sort(key=lambda x: x['volume_ratio'], reverse=True)
    
    return jsonify({
        "success": True,
        "monitored_symbols": len(symbols),
        "alerts_count": len(alerts),
        "alert_threshold": alert_threshold,
        "timeframe": timeframe,
        "results": results[:10],  # Top 10
        "alerts": alerts,
        "timestamp": datetime.utcnow().isoformat()
    })
# Stop 


# ========= REAL-TIME ANALYSIS ENDPOINTS =========

@app.route("/realtime_analysis", methods=["POST"])

def realtime_analysis():
    """Advanced real-time analysis combining order book, trades, and technical indicators"""
    try:
        #removed "kucoin", from code 
        # Get request parameters
        payload = request.get_json() or {}
        symbol = payload.get("symbol", real_time_data["current_symbol"])
        selected_exchanges = payload.get("exchanges", ["binance", "bybit", "okx", "gateio", "huobi", "kraken", "bitget", "mexc", "coinbase"])
        time_window = int(payload.get("time_window", 60))  # seconds
        prediction_horizon = int(payload.get("prediction_horizon", 5))  # minutes
        
        # Get current time
        now = time.time()
        
        # Filter data by selected exchanges
        filtered_order_book = {}
        for exchange in selected_exchanges:
            if exchange in real_time_data["order_book"]:
                filtered_order_book[exchange] = real_time_data["order_book"][exchange]
        
        # Filter trades by selected exchanges and time window
        recent_trades = [
            t for t in real_time_data["trades"]
            if t[4] in selected_exchanges and (now - t[2] <= time_window)
        ]
        
        # Calculate combined order book metrics
        combined_bids = []
        combined_asks = []
        total_bid_volume = 0.0
        total_ask_volume = 0.0
        
        for exchange, book in filtered_order_book.items():
            for price, volume in book["bids"]:
                combined_bids.append([price, volume])
                total_bid_volume += volume
            for price, volume in book["asks"]:
                combined_asks.append([price, volume])
                total_ask_volume += volume
        
        # Sort and limit
        combined_bids.sort(key=lambda x: x[0], reverse=True)
        combined_asks.sort(key=lambda x: x[0])
        combined_bids = combined_bids[:20]
        combined_asks = combined_asks[:20]
        
        # Calculate order flow metrics
        total_volume = total_bid_volume + total_ask_volume
        order_flow_imbalance = 0.0
        if total_volume > 0:
            order_flow_imbalance = (total_bid_volume - total_ask_volume) / total_volume
        
        # Calculate trade metrics
        buy_trades = 0
        sell_trades = 0
        buy_volume = 0.0
        sell_volume = 0.0
        trade_prices = []
        
        for trade in recent_trades:
            price, volume, timestamp, side, exchange = trade
            trade_prices.append(price)
            if side == 'b':
                buy_trades += 1
                buy_volume += volume
            else:
                sell_trades += 1
                sell_volume += volume
        
        total_trades = buy_trades + sell_trades
        trade_ratio = buy_trades / total_trades if total_trades > 0 else 0.5
        
        # Calculate price metrics
        current_price = 0.0
        if trade_prices:
            current_price = trade_prices[-1]
        elif combined_bids and combined_asks:
            current_price = (combined_bids[0][0] + combined_asks[0][0]) / 2
        
        # Calculate price change
        price_change = 0.0
        if len(trade_prices) >= 2:
            oldest_price = trade_prices[0]
            latest_price = trade_prices[-1]
            price_change = ((latest_price - oldest_price) / oldest_price) * 100
        
        # Calculate volatility
        volatility = 0.0
        if len(trade_prices) >= 2:
            prices_array = np.array(trade_prices)
            volatility = np.std(prices_array) / np.mean(prices_array) * 100
        
        # Calculate momentum
        momentum = 0.0
        if len(trade_prices) >= 5:
            recent_prices = trade_prices[-5:]
            momentum = ((recent_prices[-1] - recent_prices[0]) / recent_prices[0]) * 100
        
        # Calculate VWAP
        vwap = 0.0
        if recent_trades:
            total_value = sum(t[0] * t[1] for t in recent_trades)
            total_volume_traded = sum(t[1] for t in recent_trades)
            vwap = total_value / total_volume_traded if total_volume_traded > 0 else current_price
        
        # Calculate support and resistance levels
        support_levels = [bid[0] for bid in combined_bids[:5]]
        resistance_levels = [ask[0] for ask in combined_asks[:5]]
        
        # Generate trading signal
        signal = generate_realtime_signal({
            "order_flow_imbalance": order_flow_imbalance,
            "trade_ratio": trade_ratio,
            "price_change": price_change,
            "volatility": volatility,
            "momentum": momentum,
            "current_price": current_price,
            "vwap": vwap,
            "buy_volume": buy_volume,
            "sell_volume": sell_volume
        })
        
        # Generate price predictions
        predictions = generate_realtime_predictions({
            "current_price": current_price,
            "order_flow_imbalance": order_flow_imbalance,
            "momentum": momentum,
            "volatility": volatility,
            "prediction_horizon": prediction_horizon
        })
        
        # Calculate market sentiment
        sentiment = calculate_market_sentiment({
            "order_flow_imbalance": order_flow_imbalance,
            "trade_ratio": trade_ratio,
            "momentum": momentum,
            "price_change": price_change
        })
        
        # Prepare response
        response = {
            "success": True,
            "timestamp": now,
            "symbol": symbol,
            "selected_exchanges": selected_exchanges,
            "time_window": time_window,
            "metrics": {
                "current_price": current_price,
                "price_change": price_change,
                "order_flow_imbalance": order_flow_imbalance,
                "total_bid_volume": total_bid_volume,
                "total_ask_volume": total_ask_volume,
                "buy_trades": buy_trades,
                "sell_trades": sell_trades,
                "buy_volume": buy_volume,
                "sell_volume": sell_volume,
                "trade_ratio": trade_ratio,
                "volatility": volatility,
                "momentum": momentum,
                "vwap": vwap
            },
            "levels": {
                "support": support_levels,
                "resistance": resistance_levels,
                "stop_loss": calculate_stop_loss(current_price, support_levels, resistance_levels, signal)
            },
            "order_book_summary": {
                "top_bids": combined_bids[:5],
                "top_asks": combined_asks[:5],
                "bid_ask_spread": combined_asks[0][0] - combined_bids[0][0] if combined_bids and combined_asks else 0
            },
            "signal": signal,
            "predictions": predictions,
            "sentiment": sentiment,
            "recent_trades_count": len(recent_trades)
        }
        
        return jsonify(response)
        
    except Exception as e:
        print(f"Real-time analysis error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"success": False, "error": str(e)}), 500

def generate_realtime_signal(metrics: Dict[str, Any]) -> Dict[str, Any]:
    """Generate trading signal based on real-time metrics"""
    
    score = 50  # Neutral starting point
    
    # Order flow imbalance contribution
    imbalance = metrics["order_flow_imbalance"]
    if imbalance > 0.3:
        score += 25
    elif imbalance > 0.1:
        score += 15
    elif imbalance < -0.3:
        score -= 25
    elif imbalance < -0.1:
        score -= 15
    
    # Trade ratio contribution
    trade_ratio = metrics["trade_ratio"]
    if trade_ratio > 0.7:
        score += 20
    elif trade_ratio < 0.3:
        score -= 20
    
    # Momentum contribution
    momentum = metrics["momentum"]
    if momentum > 0.5:
        score += 15
    elif momentum < -0.5:
        score -= 15
    
    # Price vs VWAP
    if metrics["current_price"] > metrics["vwap"] * 1.001:
        score += 10
    elif metrics["current_price"] < metrics["vwap"] * 0.999:
        score -= 10
    
    # Volume dominance
    total_volume = metrics["buy_volume"] + metrics["sell_volume"]
    if total_volume > 0:
        volume_ratio = metrics["buy_volume"] / total_volume
        if volume_ratio > 0.7:
            score += 10
        elif volume_ratio < 0.3:
            score -= 10
    
    # Cap score between 0 and 100
    score = max(0, min(100, score))
    
    # Determine signal
    if score >= 80:
        signal = "STRONG_BUY"
        icon = "🚀"
        confidence = "High"
        color_class = "buy"
    elif score >= 65:
        signal = "BUY"
        icon = "📈"
        confidence = "Medium"
        color_class = "buy"
    elif score >= 45:
        signal = "HOLD"
        icon = "⏸️"
        confidence = "Low"
        color_class = "neutral"
    elif score >= 30:
        signal = "SELL"
        icon = "📉"
        confidence = "Medium"
        color_class = "sell"
    else:
        signal = "STRONG_SELL"
        icon = "🔥"
        confidence = "High"
        color_class = "sell"
    
    return {
        "signal": signal,
        "icon": icon,
        "confidence": confidence,
        "score": score,
        "color_class": color_class,
        "reasons": [
            f"Order flow: {'Buying' if imbalance > 0 else 'Selling'} pressure",
            f"Trade ratio: {trade_ratio:.1%} buys",
            f"Momentum: {'Up' if momentum > 0 else 'Down'} {abs(momentum):.2f}%"
        ]
    }

def generate_realtime_predictions(metrics: Dict[str, Any]) -> Dict[str, Any]:
    """Generate price predictions based on real-time metrics"""
    
    current_price = metrics["current_price"]
    imbalance = metrics["order_flow_imbalance"]
    momentum = metrics["momentum"]
    volatility = metrics["volatility"]
    horizon = metrics["prediction_horizon"]
    
    # Base prediction formula
    base_change_percent = (imbalance * 0.5 + momentum * 0.02) * horizon
    
    # Add volatility adjustment
    volatility_adjustment = (volatility / 100) * math.sqrt(horizon) * (np.random.random() - 0.5)
    
    # Calculate predictions for different timeframes
    pred_5min = current_price * (1 + (base_change_percent + volatility_adjustment * 0.5) / 100)
    pred_15min = current_price * (1 + (base_change_percent * 3 + volatility_adjustment) / 100)
    
    # Calculate confidence range
    confidence_range = volatility / 100 * 2  # 2x volatility as confidence range
    
    return {
        "5_min": {
            "price": pred_5min,
            "change_percent": ((pred_5min - current_price) / current_price) * 100,
            "confidence": max(30, 100 - abs(base_change_percent) * 10)
        },
        "15_min": {
            "price": pred_15min,
            "change_percent": ((pred_15min - current_price) / current_price) * 100,
            "confidence": max(20, 100 - abs(base_change_percent * 3) * 10)
        },
        "range": {
            "lower": current_price * (1 - confidence_range),
            "upper": current_price * (1 + confidence_range)
        }
    }

def calculate_market_sentiment(metrics: Dict[str, Any]) -> Dict[str, Any]:
    """Calculate overall market sentiment"""
    
    sentiment_score = 50
    
    # Weighted contributions
    sentiment_score += metrics["order_flow_imbalance"] * 25
    sentiment_score += (metrics["trade_ratio"] - 0.5) * 20
    sentiment_score += metrics["momentum"] * 5
    sentiment_score += metrics["price_change"] * 2
    
    # Cap score
    sentiment_score = max(0, min(100, sentiment_score))
    
    # Determine sentiment category
    if sentiment_score >= 70:
        sentiment = "Bullish"
        icon = "😊"
    elif sentiment_score >= 60:
        sentiment = "Slightly Bullish"
        icon = "🙂"
    elif sentiment_score >= 40:
        sentiment = "Neutral"
        icon = "😐"
    elif sentiment_score >= 30:
        sentiment = "Slightly Bearish"
        icon = "😕"
    else:
        sentiment = "Bearish"
        icon = "😟"
    
    return {
        "sentiment": sentiment,
        "icon": icon,
        "score": sentiment_score,
        "description": f"Market shows {sentiment.lower()} sentiment"
    }

def calculate_stop_loss(current_price: float, support_levels: List[float], 
                       resistance_levels: List[float], signal: Dict[str, Any]) -> float:
    """Calculate stop loss level based on signal and support/resistance"""
    
    if not support_levels or not resistance_levels:
        return current_price * 0.97  # Default 3% stop loss
    
    if "BUY" in signal["signal"]:
        # For buy signals, stop loss below support
        stop_loss = min(support_levels) * 0.97  # 3% below support
    elif "SELL" in signal["signal"]:
        # For sell signals, stop loss above resistance
        stop_loss = max(resistance_levels) * 1.03  # 3% above resistance
    else:
        # For neutral/hold, use tighter stop loss
        stop_loss = current_price * 0.99  # 1% stop loss
    
    return stop_loss

# ========= ENHANCED PREDICTION ENDPOINTS =========

@app.route("/multi_timeframe_analysis", methods=["POST"])
def multi_timeframe_analysis():
    """Enhanced multi-timeframe analysis with support/resistance and signals"""
    payload = request.get_json() or {}
    symbol = payload.get("symbol", "BTC/USDT").upper()
    timeframes = payload.get("timeframes", ["1h", "4h", "1d", "1w"])
    look_back = int(payload.get("look_back", 100))
    
    try:
        predictions = []
        all_indicators = {}
        
        # Analyze each timeframe
        for timeframe in timeframes:
            # Get data for this timeframe
            conn = get_conn()
            cur = conn.cursor(dictionary=True)
            cur.execute("""
                SELECT time_utc, open, high, low, close, volume
                FROM ohlcv_data
                WHERE symbol = %s AND timeframe = %s
                ORDER BY time_utc DESC
                LIMIT %s
            """, (symbol, timeframe, look_back))
            rows = cur.fetchall()
            cur.close()
            conn.close()
            
            if len(rows) < 20:  # Need minimum data
                continue
            
            # Convert to DataFrame
            df = pd.DataFrame(rows)
            df = df.sort_values('time_utc')
            
            # Calculate indicators
            close_prices = df['close'].astype(float)
            high_prices = df['high'].astype(float)
            low_prices = df['low'].astype(float)
            volume = df['volume'].astype(float)
            
            # Calculate RSI
            rsi = ta.rsi(close_prices, length=14).iloc[-1] if len(close_prices) >= 14 else None
            
            # Calculate MACD
            macd_result = ta.macd(close_prices, fast=12, slow=26, signal=9)
            macd = macd_result.iloc[-1, 0] if not macd_result.empty else None
            macd_signal = macd_result.iloc[-1, 1] if macd_result.shape[1] > 1 else None
            
            # Calculate EMAs
            ema_20 = ta.ema(close_prices, length=20).iloc[-1] if len(close_prices) >= 20 else None
            ema_50 = ta.ema(close_prices, length=50).iloc[-1] if len(close_prices) >= 50 else None
            ema_200 = ta.ema(close_prices, length=200).iloc[-1] if len(close_prices) >= 200 else None
            
            # Calculate support and resistance using recent highs/lows
            recent_highs = high_prices.tail(20)
            recent_lows = low_prices.tail(20)
            
            support_level = round(float(recent_lows.min()), 4)
            resistance_level = round(float(recent_highs.max()), 4)
            
            # Calculate ATR for volatility
            atr = ta.atr(high_prices, low_prices, close_prices, length=14).iloc[-1] if len(close_prices) >= 14 else None
            
            # Generate prediction using pattern matching
            prediction_result = predict_for_timeframe(symbol, timeframe, look_back)
            
            # Determine signal
            signal, recommendation = generate_signal(
                rsi=rsi,
                macd=macd,
                macd_signal=macd_signal,
                ema_20=ema_20,
                ema_50=ema_50,
                current_price=float(close_prices.iloc[-1]),
                predicted_change=prediction_result.get('predicted_change', 0) if prediction_result else 0
            )
            
            # Calculate confidence
            confidence = calculate_confidence(
                rsi=rsi,
                macd_strength=abs(macd - macd_signal) if macd and macd_signal else 0,
                trend_alignment=check_trend_alignment(ema_20, ema_50, ema_200, close_prices.iloc[-1]),
                volume_trend=check_volume_trend(volume)
            )
            
            prediction_data = {
                "timeframe": timeframe,
                "current_price": float(close_prices.iloc[-1]),
                "rsi": float(rsi) if rsi else None,
                "macd": float(macd) if macd else None,
                "macd_signal": float(macd_signal) if macd_signal else None,
                "ema_20": float(ema_20) if ema_20 else None,
                "ema_50": float(ema_50) if ema_50 else None,
                "ema_200": float(ema_200) if ema_200 else None,
                "support": support_level,
                "resistance": resistance_level,
                "atr": float(atr) if atr else None,
                "predicted_change": prediction_result.get('predicted_change', 0) if prediction_result else 0,
                "signal": signal,
                "recommendation": recommendation,
                "confidence": confidence,
                "macd_status": "Bullish" if macd and macd_signal and macd > macd_signal else "Bearish" if macd and macd_signal else "Neutral"
            }
            
            predictions.append(prediction_data)
            all_indicators[timeframe] = prediction_data
        
        # Generate overall summary
        summary = generate_overall_summary(predictions, symbol)
        
        return jsonify({
            "success": True,
            "symbol": symbol,
            "predictions": predictions,
            "summary": summary,
            "timestamp": datetime.utcnow().isoformat()
        })
        
    except Exception as e:
        print(f"Multi timeframe analysis error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"success": False, "error": str(e)}), 500

def predict_for_timeframe(symbol, timeframe, look_back):
    """Helper function to predict for a specific timeframe"""
    try:
        # Try to get prediction from existing endpoint
        response = requests.post(
            f"http://127.0.0.1:8000/predict_candle",
            json={"symbol": symbol, "timeframe": timeframe, "look_back": look_back},
            timeout=10
        )
        if response.status_code == 200:
            data = response.json()
            if data.get("success"):
                pred = data.get("prediction", {})
                return {
                    "predicted_change": pred.get("pct_close", 0),
                    "confidence": pred.get("confidence", 50),
                    "matches": pred.get("matches", 0)
                }
    except Exception:
        pass
    
    # Fallback: simple prediction based on recent trend
    conn = get_conn()
    cur = conn.cursor(dictionary=True)
    cur.execute("""
        SELECT close FROM ohlcv_data 
        WHERE symbol = %s AND timeframe = %s 
        ORDER BY time_utc DESC LIMIT 20
    """, (symbol, timeframe))
    rows = cur.fetchall()
    cur.close()
    conn.close()
    
    if len(rows) >= 10:
        prices = [float(r['close']) for r in rows[:10]]
        recent_change = ((prices[0] - prices[-1]) / prices[-1]) * 100
        
        # Simple momentum-based prediction
        predicted_change = recent_change * 0.7  # Assume continuation but weaker
        confidence = min(70, abs(predicted_change) * 2)  # Higher confidence for stronger moves
        
        return {
            "predicted_change": round(predicted_change, 2),
            "confidence": round(confidence, 1),
            "matches": 0
        }
    
    return {"predicted_change": 0, "confidence": 50, "matches": 0}

def generate_signal(rsi, macd, macd_signal, ema_20, ema_50, current_price, predicted_change):
    """Generate trading signal based on multiple indicators"""
    
    signal_score = 0
    reasons = []
    
    # RSI analysis
    if rsi:
        if rsi < 30:
            signal_score += 20
            reasons.append("RSI oversold")
        elif rsi > 70:
            signal_score -= 20
            reasons.append("RSI overbought")
        elif rsi > 50:
            signal_score += 5
        else:
            signal_score -= 5
    
    # MACD analysis
    if macd and macd_signal:
        if macd > macd_signal and macd > 0:
            signal_score += 15
            reasons.append("MACD bullish")
        elif macd < macd_signal and macd < 0:
            signal_score -= 15
            reasons.append("MACD bearish")
    
    # EMA analysis
    if ema_20 and ema_50:
        if current_price > ema_20 > ema_50:
            signal_score += 15
            reasons.append("Strong uptrend")
        elif current_price < ema_20 < ema_50:
            signal_score -= 15
            reasons.append("Strong downtrend")
        elif current_price > ema_20:
            signal_score += 5
        else:
            signal_score -= 5
    
    # Predicted change
    if predicted_change > 1:
        signal_score += 10
        reasons.append(f"Predicted +{predicted_change:.1f}%")
    elif predicted_change < -1:
        signal_score -= 10
        reasons.append(f"Predicted {predicted_change:.1f}%")
    
    # Determine final signal
    if signal_score >= 30:
        signal = "STRONG BULLISH"
        recommendation = "BUY/LONG"
    elif signal_score >= 15:
        signal = "BULLISH"
        recommendation = "BUY (Small)"
    elif signal_score <= -30:
        signal = "STRONG BEARISH"
        recommendation = "SELL/SHORT"
    elif signal_score <= -15:
        signal = "BEARISH"
        recommendation = "SELL (Small)"
    elif signal_score > 0:
        signal = "SLIGHTLY BULLISH"
        recommendation = "HOLD/BUY Dips"
    elif signal_score < 0:
        signal = "SLIGHTLY BEARISH"
        recommendation = "HOLD/SELL Rallies"
    else:
        signal = "NEUTRAL"
        recommendation = "HOLD/Wait"
    
    return signal, recommendation

def calculate_confidence(rsi, macd_strength, trend_alignment, volume_trend):
    """Calculate confidence score (0-100)"""
    confidence = 50
    
    # RSI confidence
    if rsi:
        if rsi < 25 or rsi > 75:
            confidence += 15  # Extreme readings are more confident
        elif 45 < rsi < 55:
            confidence -= 10  # Middle RSI is less confident
    
    # MACD strength
    confidence += min(20, macd_strength * 10)
    
    # Trend alignment
    confidence += trend_alignment * 10
    
    # Volume trend
    confidence += volume_trend * 5
    
    # Cap between 10 and 95
    confidence = max(10, min(95, confidence))
    
    return round(confidence)

def check_trend_alignment(ema_20, ema_50, ema_200, current_price):
    """Check if trends are aligned (returns -1 to 1)"""
    if not all([ema_20, ema_50, ema_200]):
        return 0
    
    # Check if all EMAs are in order (uptrend: price > ema20 > ema50 > ema200)
    if current_price > ema_20 > ema_50 > ema_200:
        return 1  # Strong uptrend alignment
    elif current_price < ema_20 < ema_50 < ema_200:
        return -1  # Strong downtrend alignment
    elif current_price > ema_20 > ema_50:
        return 0.5  # Partial uptrend
    elif current_price < ema_20 < ema_50:
        return -0.5  # Partial downtrend
    
    return 0  # No clear alignment

def check_volume_trend(volume_series):
    """Check if volume is increasing (returns -1 to 1)"""
    if len(volume_series) < 5:
        return 0
    
    recent_avg = volume_series.tail(5).mean()
    previous_avg = volume_series.iloc[-10:-5].mean()
    
    if previous_avg == 0:
        return 0
    
    ratio = recent_avg / previous_avg
    
    if ratio > 1.3:
        return 1  # Volume increasing
    elif ratio < 0.7:
        return -1  # Volume decreasing
    
    return 0

def generate_overall_summary(predictions, symbol):
    """Generate overall market summary"""
    if not predictions:
        return {
            "overall_signal": "NEUTRAL",
            "trend_direction": "Sideways",
            "confidence": 50,
            "recommended_action": "Wait",
            "support_levels": [],
            "resistance_levels": [],
            "stop_loss_level": None,
            "rsi": None,
            "macd": None,
            "volatility": "Low"
        }
    
    # Calculate weighted average signal
    total_weight = 0
    weighted_signal = 0
    timeframe_weights = {"1h": 1, "4h": 2, "1d": 3, "1w": 4}
    
    all_supports = []
    all_resistances = []
    all_rsi = []
    all_macd = []
    
    for pred in predictions:
        weight = timeframe_weights.get(pred["timeframe"], 1)
        signal_value = 1 if "BULL" in pred["signal"] else -1 if "BEAR" in pred["signal"] else 0
        weighted_signal += signal_value * weight * pred["confidence"] / 100
        total_weight += weight
        
        if pred.get("support"):
            all_supports.append(pred["support"])
        if pred.get("resistance"):
            all_resistances.append(pred["resistance"])
        if pred.get("rsi"):
            all_rsi.append(pred["rsi"])
        if pred.get("macd"):
            all_macd.append(pred["macd"])
    
    avg_signal = weighted_signal / total_weight if total_weight > 0 else 0
    
    # Determine overall signal
    if avg_signal > 0.3:
        overall_signal = "BULLISH"
        trend_direction = "Up"
        recommended_action = "Buy/Long"
    elif avg_signal > 0.1:
        overall_signal = "SLIGHTLY BULLISH"
        trend_direction = "Up (Weak)"
        recommended_action = "Buy Dips"
    elif avg_signal < -0.3:
        overall_signal = "BEARISH"
        trend_direction = "Down"
        recommended_action = "Sell/Short"
    elif avg_signal < -0.1:
        overall_signal = "SLIGHTLY BEARISH"
        trend_direction = "Down (Weak)"
        recommended_action = "Sell Rallies"
    else:
        overall_signal = "NEUTRAL"
        trend_direction = "Sideways"
        recommended_action = "Wait/Hold"
    
    # Calculate confidence
    avg_confidence = sum(p["confidence"] for p in predictions) / len(predictions) if predictions else 50
    
    # Calculate support/resistance levels
    support_levels = sorted(list(set(all_supports))) if all_supports else []
    resistance_levels = sorted(list(set(all_resistances))) if all_resistances else []
    
    # Calculate stop loss level (1.5x ATR below support for long, above resistance for short)
    stop_loss_level = None
    if support_levels and resistance_levels:
        current_mid = (support_levels[0] + resistance_levels[0]) / 2
        if "BULL" in overall_signal:
            stop_loss_level = round(support_levels[0] * 0.97, 4)  # 3% below support
        elif "BEAR" in overall_signal:
            stop_loss_level = round(resistance_levels[0] * 1.03, 4)  # 3% above resistance
    
    # Calculate volatility
    avg_atr = sum(p.get("atr", 0) for p in predictions if p.get("atr")) / len([p for p in predictions if p.get("atr")]) if any(p.get("atr") for p in predictions) else 0
    volatility = "High" if avg_atr > 100 else "Medium" if avg_atr > 50 else "Low"
    
    return {
        "overall_signal": overall_signal,
        "trend_direction": trend_direction,
        "confidence": round(avg_confidence, 1),
        "recommended_action": recommended_action,
        "support_levels": support_levels[:3],  # Top 3 supports
        "resistance_levels": resistance_levels[:3],  # Top 3 resistances
        "stop_loss_level": stop_loss_level,
        "rsi": round(sum(all_rsi) / len(all_rsi), 1) if all_rsi else None,
        "macd": {"macd": round(sum(all_macd) / len(all_macd), 4) if all_macd else None, "signal": None},
        "volatility": volatility
    }

@app.route("/get_prediction_history", methods=["GET"])
def get_prediction_history():
    """Get recent prediction history"""
    symbol = request.args.get("symbol", "BTC/USDT").upper()
    limit = int(request.args.get("limit", 20))
    
    conn = get_conn()
    cur = conn.cursor(dictionary=True)
    
    # Check if predictions_log table exists, create if not
    cur.execute("""
        CREATE TABLE IF NOT EXISTS predictions_log (
            id INT AUTO_INCREMENT PRIMARY KEY,
            symbol VARCHAR(20),
            timeframe VARCHAR(10),
            predicted_change FLOAT,
            confidence FLOAT,
            `signal` VARCHAR(20),
            recommendation VARCHAR(50),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            actual_change FLOAT DEFAULT NULL,
            accuracy FLOAT DEFAULT NULL
        )
    """)
    
    # Get recent predictions
    cur.execute("""
        SELECT symbol, timeframe, predicted_change, confidence, 
               signal, recommendation, created_at, actual_change, accuracy
        FROM predictions_log
        WHERE symbol = %s
        ORDER BY created_at DESC
        LIMIT %s
    """, (symbol, limit))
    
    rows = cur.fetchall()
    cur.close()
    conn.close()
    
    return jsonify({
        "success": True,
        "predictions": rows,
        "count": len(rows)
    })

@app.route("/log_prediction", methods=["POST"])
def log_prediction():
    """Log a prediction for future accuracy tracking"""
    payload = request.get_json() or {}
    
    required_fields = ["symbol", "timeframe", "predicted_change", "signal"]
    for field in required_fields:
        if field not in payload:
            return jsonify({"success": False, "error": f"Missing field: {field}"}), 400
    
    conn = get_conn()
    cur = conn.cursor()
    
    try:
        cur.execute("""
            INSERT INTO predictions_log 
            (symbol, timeframe, predicted_change, confidence, signal, recommendation)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (
            payload["symbol"],
            payload["timeframe"],
            payload["predicted_change"],
            payload.get("confidence", 50),
            payload["signal"],
            payload.get("recommendation", "N/A")
        ))
        
        conn.commit()
        prediction_id = cur.lastrowid
        
        cur.close()
        conn.close()
        
        return jsonify({
            "success": True,
            "prediction_id": prediction_id,
            "message": "Prediction logged successfully"
        })
        
    except Exception as e:
        conn.rollback()
        cur.close()
        conn.close()
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/update_prediction_accuracy", methods=["POST"])
def update_prediction_accuracy():
    """Update prediction with actual result"""
    payload = request.get_json() or {}
    
    prediction_id = payload.get("prediction_id")
    actual_change = payload.get("actual_change")
    
    if not prediction_id or actual_change is None:
        return jsonify({"success": False, "error": "Missing prediction_id or actual_change"}), 400
    
    conn = get_conn()
    cur = conn.cursor(dictionary=True)
    
    try:
        # Get the original prediction
        cur.execute("""
            SELECT predicted_change FROM predictions_log WHERE id = %s
        """, (prediction_id,))
        prediction = cur.fetchone()
        
        if not prediction:
            return jsonify({"success": False, "error": "Prediction not found"}), 404
        
        predicted_change = prediction["predicted_change"]
        
        # Calculate accuracy (percentage match)
        if predicted_change == 0:
            accuracy = 100 if actual_change == 0 else 0
        else:
            accuracy = max(0, 100 - abs((actual_change - predicted_change) / predicted_change * 100))
        
        # Update the prediction
        cur.execute("""
            UPDATE predictions_log 
            SET actual_change = %s, accuracy = %s
            WHERE id = %s
        """, (actual_change, accuracy, prediction_id))
        
        conn.commit()
        cur.close()
        conn.close()
        
        return jsonify({
            "success": True,
            "accuracy": round(accuracy, 2),
            "message": "Accuracy updated"
        })
        
    except Exception as e:
        conn.rollback()
        cur.close()
        conn.close()
        return jsonify({"success": False, "error": str(e)}), 500

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
# Removed Kucoin from code  ("kucoin", kucoin_ws),
# ========= REAL-TIME WEBSOCKETS =========
def close_websockets():
    """Close all WebSocket connections"""
    global binance_ws, bybit_ws, okx_ws, gateio_ws,  huobi_ws, kraken_ws, bitget_ws, mexc_ws, coinbase_ws
    
    websockets_to_close = [
        ("binance", binance_ws),
        ("bybit", bybit_ws),
        ("okx", okx_ws),
        ("gateio", gateio_ws),
        #("kucoin", kucoin_ws),
        ("huobi", huobi_ws),
        ("kraken", kraken_ws),
        ("bitget", bitget_ws),
        ("mexc", mexc_ws),
        ("coinbase", coinbase_ws)
    ]
    
    for name, ws in websockets_to_close:
        if ws:
            try:
                ws.close()
                print(f"Closed {name} WebSocket")
            except Exception as e:
                print(f"Error closing {name} WebSocket: {e}")
    # Removed Kucoin from code kucoin_ws = 
    # Clear all WebSocket references
    binance_ws = bybit_ws = okx_ws = gateio_ws = huobi_ws = kraken_ws = bitget_ws = mexc_ws = coinbase_ws = None
    
    # Small delay to ensure WebSockets are properly closed
    time.sleep(0.5)
# Removed Kucoin from code kucoin_ws,
def start_websockets():
    """Start WebSocket connections for current symbol"""
    global binance_ws, bybit_ws, okx_ws, gateio_ws, huobi_ws, kraken_ws, bitget_ws, mexc_ws, coinbase_ws
    
    # Ensure old WebSockets are closed
    close_websockets()
    
    symbol = real_time_data["current_symbol"]
    print(f"Starting WebSockets for symbol: {symbol}")
    
    # Convert symbol for each exchange
    # Removed KuCoin From Code 
    binance_pair = symbol.replace('/', '').lower()
    bybit_pair = symbol.replace('/', '').upper()
    okx_pair = symbol.replace('/', '-').upper()
    gateio_pair = symbol.replace('/', '_').upper()
    #kucoin_pair = symbol.replace('/', '-').upper()
    huobi_pair = symbol.replace('/', '').lower()
    kraken_pair = symbol.replace('/', '').upper()  # Note: Kraken uses different pairs for some coins
    bitget_pair = symbol.replace('/', '').upper()
    mexc_pair = symbol.replace('/', '_').upper()
    coinbase_pair = symbol.replace('/', '-').upper()

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
                #elif exchange_name == 'kucoin':
                    #global kucoin_ws
                    #kucoin_ws = ws
                elif exchange_name == 'huobi':
                    global huobi_ws
                    huobi_ws = ws
                elif exchange_name == 'kraken':
                    global kraken_ws
                    kraken_ws = ws
                elif exchange_name == 'bitget':
                    global bitget_ws
                    bitget_ws = ws
                elif exchange_name == 'mexc':
                    global mexc_ws
                    mexc_ws = ws
                elif exchange_name == 'coinbase':
                    global coinbase_ws
                    coinbase_ws = ws
                
                # Run WebSocket
                ws.run_forever(ping_interval=20, ping_timeout=10)
                
            except Exception as e:
                print(f"{exchange_name} WS connection error: {e}")
                
                # Check if symbol has changed while reconnecting
                if real_time_data["current_symbol"] != thread_symbol:
                    print(f"Symbol changed from {thread_symbol} to {real_time_data['current_symbol']}. Stopping {exchange_name} WebSocket thread.")
                    break
                    
                time.sleep(5)  # Wait before reconnecting

    # Start WebSocket threads for all exchanges
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
    
    # KuCoin Removed from Code
    #kucoin_url = "wss://ws-api.kucoin.com/endpoint"
    #def kucoin_open(ws):
        # Subscribe to order book
     #   orderbook_sub = {
            #"type": "subscribe",
            #"topic": f"/market/level2:{kucoin_pair}",
            #"privateChannel": False,
            #"response": True
        #}
        #ws.send(json.dumps(orderbook_sub))
        
        # Subscribe to trades
        #trades_sub = {
         #   "type": "subscribe",
         #   "topic": f"/market/trade:{kucoin_pair}",
         #   "privateChannel": False,
          #  "response": True
        #}
        #ws.send(json.dumps(trades_sub))
        #print(f"KuCoin subscribed to {kucoin_pair}")
    #threading.Thread(target=ws_thread, args=('kucoin', kucoin_url, kucoin_open, on_message_kucoin), daemon=True).start()
    
    # Huobi - FIXED: Added gzip decompression
    huobi_url = "wss://api.huobi.pro/ws"
    def huobi_open(ws):
        # Subscribe to order book
        orderbook_sub = {
            "sub": f"market.{huobi_pair}.depth.step0",
            "id": "id1"
        }
        ws.send(json.dumps(orderbook_sub))
        
        # Subscribe to trades
        trades_sub = {
            "sub": f"market.{huobi_pair}.trade.detail",
            "id": "id2"
        }
        ws.send(json.dumps(trades_sub))
        print(f"Huobi subscribed to {huobi_pair}")
    threading.Thread(target=ws_thread, args=('huobi', huobi_url, huobi_open, on_message_huobi), daemon=True).start()
    
    # Kraken
    kraken_url = "wss://ws.kraken.com"
    def kraken_open(ws):
        # Subscribe to order book
        orderbook_sub = {
            "event": "subscribe",
            "pair": [kraken_pair],
            "subscription": {"name": "book", "depth": 25}
        }
        ws.send(json.dumps(orderbook_sub))
        
        # Subscribe to trades
        trades_sub = {
            "event": "subscribe",
            "pair": [kraken_pair],
            "subscription": {"name": "trade"}
        }
        ws.send(json.dumps(trades_sub))
        print(f"Kraken subscribed to {kraken_pair}")
    threading.Thread(target=ws_thread, args=('kraken', kraken_url, kraken_open, on_message_kraken), daemon=True).start()
    
    # Bitget - FIXED: Added error handling for string index
    bitget_url = "wss://ws.bitget.com/v2/ws/public"
    def bitget_open(ws):
        # Subscribe to order book
        orderbook_sub = {
            "op": "subscribe",
            "args": [{
                "instType": "SPOT",
                "channel": "books",
                "instId": bitget_pair
            }]
        }
        ws.send(json.dumps(orderbook_sub))
        
        # Subscribe to trades
        trades_sub = {
            "op": "subscribe",
            "args": [{
                "instType": "SPOT",
                "channel": "trade",
                "instId": bitget_pair
            }]
        }
        ws.send(json.dumps(trades_sub))
        print(f"Bitget subscribed to {bitget_pair}")
    threading.Thread(target=ws_thread, args=('bitget', bitget_url, bitget_open, on_message_bitget), daemon=True).start()
    
    # MEXC
    mexc_url = "wss://wbs.mexc.com/ws"
    def mexc_open(ws):
        # Subscribe to order book
        orderbook_sub = {
            "method": "SUBSCRIPTION",
            "params": [f"spot@public.miniTicker.v3.api@{mexc_pair}"]
        }
        ws.send(json.dumps(orderbook_sub))
        
        # Subscribe to trades
        trades_sub = {
            "method": "SUBSCRIPTION",
            "params": [f"spot@public.deals.v3.api@{mexc_pair}"]
        }
        ws.send(json.dumps(trades_sub))
        print(f"MEXC subscribed to {mexc_pair}")
    threading.Thread(target=ws_thread, args=('mexc', mexc_url, mexc_open, on_message_mexc), daemon=True).start()
    
    # Coinbase
    coinbase_url = "wss://ws-feed.exchange.coinbase.com"
    def coinbase_open(ws):
        subscribe_msg = {
            "type": "subscribe",
            "product_ids": [coinbase_pair],
            "channels": ["level2", "ticker", "matches"]
        }
        ws.send(json.dumps(subscribe_msg))
        print(f"Coinbase subscribed to {coinbase_pair}")
    threading.Thread(target=ws_thread, args=('coinbase', coinbase_url, coinbase_open, on_message_coinbase), daemon=True).start()
    
    print(f"✅ All 10 exchange WebSockets started for {symbol}")

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
# Removed KuCoin from code
# def on_message_kucoin(ws, message):
#     try:
#         # Verify we're still tracking the right symbol
#         current_symbol = real_time_data["current_symbol"].replace('/', '-')
#         data = json.loads(message)
        
#         # Only process if this is for our current symbol
#         if 'topic' in data:
#             topic = data['topic']
#             if current_symbol.upper() not in topic:
#                 return  # Skip messages for other symbols
        
#         # Handle order book updates
#         if 'market/level2:' in str(data.get('topic', '')):
#             # Level 2 order book update
#             if 'data' in data:
#                 book_data = data['data']
#                 if 'changes' in book_data:
#                     # KuCoin sends incremental updates, we need to maintain our own order book
#                     # For simplicity, we'll just store the entire snapshot if available
#                     if 'asks' in book_data and 'bids' in book_data:
#                         update_order_book("kucoin", book_data['bids'], book_data['asks'])
        
#         # Handle trade updates
#         elif 'market/trade:' in str(data.get('topic', '')):
#             if 'data' in data:
#                 trade_data = data['data']
#                 if isinstance(trade_data, dict) and 'trades' in trade_data:
#                     for trade in trade_data['trades']:
#                         side = 'b' if trade.get('side') == 'buy' else 's'
#                         price = trade.get('price')
#                         size = trade.get('size')
                        
#                         if price and size:
#                             process_trade("kucoin", {
#                                 "price": float(price),
#                                 "volume": float(size),
#                                 "timestamp": time.time(),
#                                 "side": side
#                             })
                
#     except Exception as e:
#         print(f"KuCoin message error: {e}")


# Code Update Fix Start
# ========= BINANCE ALL PAIRS SCANNER =========

def fetch_all_binance_pairs():
    """Fetch all Binance spot and futures pairs with rate limiting"""
    try:
        # Initialize Binance exchange
        binance = ccxt.binance({
            'enableRateLimit': True,
            'rateLimit': 1000,  # Binance rate limit
            'options': {
                'defaultType': 'spot',  # Start with spot
            }
        })
        
        # Create futures exchange instance
        binance_futures = ccxt.binance({
            'enableRateLimit': True,
            'rateLimit': 1000,
            'options': {
                'defaultType': 'future',
            }
        })
        
        all_pairs = []
        
        # Fetch spot markets
        print("Fetching Binance spot markets...")
        try:
            binance.load_markets()
            spot_markets = binance.markets
            for symbol, market in spot_markets.items():
                if market['active']:
                    all_pairs.append({
                        'symbol': symbol,
                        'base_asset': market.get('base'),
                        'quote_asset': market.get('quote'),
                        'pair_type': 'spot',
                        'status': 'active' if market.get('active') else 'inactive'
                    })
            print(f"Found {len(spot_markets)} spot markets")
            time.sleep(1)  # Rate limiting
        except Exception as e:
            print(f"Error fetching spot markets: {e}")
        
        # Fetch futures markets
        print("Fetching Binance futures markets...")
        try:
            binance_futures.load_markets()
            futures_markets = binance_futures.markets
            for symbol, market in futures_markets.items():
                if market['active']:
                    all_pairs.append({
                        'symbol': symbol,
                        'base_asset': market.get('base'),
                        'quote_asset': market.get('quote', 'USDT'),
                        'pair_type': 'future',
                        'status': 'active' if market.get('active') else 'inactive'
                    })
            print(f"Found {len(futures_markets)} futures markets")
            time.sleep(1)  # Rate limiting
        except Exception as e:
            print(f"Error fetching futures markets: {e}")
        
        # Save to database
        if all_pairs:
            conn = get_conn()
            cur = conn.cursor()
            
            # Clear existing data
            cur.execute("DELETE FROM binance_all_pairs")
            
            # Insert new data
            sql = """
            INSERT INTO binance_all_pairs (symbol, base_asset, quote_asset, pair_type, status)
            VALUES (%s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE 
                base_asset = VALUES(base_asset),
                quote_asset = VALUES(quote_asset),
                status = VALUES(status),
                last_updated = CURRENT_TIMESTAMP
            """
            
            rows = [(p['symbol'], p['base_asset'], p['quote_asset'], p['pair_type'], p['status']) 
                   for p in all_pairs]
            
            cur.executemany(sql, rows)
            conn.commit()
            
            cur.close()
            conn.close()
            
            print(f"Saved {len(all_pairs)} Binance pairs to database")
        
        return all_pairs
        
    except Exception as e:
        print(f"Error fetching Binance pairs: {e}")
        import traceback
        traceback.print_exc()
        return []

@app.route("/update_binance_pairs", methods=["POST"])
def update_binance_pairs():
    """Update all Binance spot and futures pairs"""
    try:
        print("Starting Binance pairs update...")
        pairs = fetch_all_binance_pairs()
        
        return jsonify({
            "success": True,
            "message": f"Updated {len(pairs)} Binance pairs",
            "spot_count": len([p for p in pairs if p['pair_type'] == 'spot']),
            "futures_count": len([p for p in pairs if p['pair_type'] == 'future']),
            "timestamp": datetime.utcnow().isoformat()
        })
        
    except Exception as e:
        print(f"Update error: {e}")
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/get_binance_pairs", methods=["GET"])
def get_binance_pairs():
    """Get all Binance pairs from database"""
    try:
        pair_type = request.args.get("type", "all")  # all, spot, future
        status = request.args.get("status", "active")
        quote_asset = request.args.get("quote", "")  # USDT, BTC, etc
        limit = int(request.args.get("limit", 1000))
        
        conn = get_conn()
        cur = conn.cursor(dictionary=True)
        
        query = "SELECT * FROM binance_all_pairs WHERE 1=1"
        params = []
        
        if pair_type != "all":
            query += " AND pair_type = %s"
            params.append(pair_type)
        
        if status:
            query += " AND status = %s"
            params.append(status)
        
        if quote_asset:
            query += " AND (quote_asset = %s OR symbol LIKE %s)"
            params.append(quote_asset)
            params.append(f"%/{quote_asset}")
        
        query += " ORDER BY symbol LIMIT %s"
        params.append(limit)
        
        cur.execute(query, params)
        rows = cur.fetchall()
        
        cur.close()
        conn.close()
        
        return jsonify({
            "success": True,
            "count": len(rows),
            "pairs": rows
        })
        
    except Exception as e:
        print(f"Get pairs error: {e}")
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/scan_all_pairs", methods=["POST"])
def scan_all_pairs():
    """
    Comprehensive scanner for all Binance pairs with rate limiting
    """
    payload = request.get_json() or {}
    timeframe = payload.get("timeframe", "5m")
    pair_type = payload.get("pair_type", "spot")  # spot, future, all
    quote_asset = payload.get("quote_asset", "USDT")
    max_pairs = int(payload.get("max_pairs", 100))
    delay_ms = int(payload.get("delay_ms", 100))  # Delay between requests
    
    try:
        # Get pairs from database
        conn = get_conn()
        cur = conn.cursor(dictionary=True)
        
        query = """
        SELECT symbol, pair_type, base_asset, quote_asset 
        FROM binance_all_pairs 
        WHERE status = 'active'
        """
        params = []
        
        if pair_type != "all":
            query += " AND pair_type = %s"
            params.append(pair_type)
        
        if quote_asset:
            query += " AND (quote_asset = %s OR symbol LIKE %s)"
            params.append(quote_asset)
            params.append(f"%/{quote_asset}")
        
        query += " ORDER BY RAND() LIMIT %s"
        params.append(max_pairs)
        
        cur.execute(query, params)
        pairs = cur.fetchall()
        cur.close()
        conn.close()
        
        if not pairs:
            return jsonify({
                "success": False,
                "error": "No pairs found. Run /update_binance_pairs first."
            }), 400
        
        # Initialize exchange
        exchange = ccxt.binance({
            'enableRateLimit': True,
            'rateLimit': 1000,
        })
        
        results = []
        volume_alerts = []
        pattern_alerts = []
        
        print(f"Scanning {len(pairs)} pairs with {delay_ms}ms delay...")
        
        for i, pair in enumerate(pairs):
            try:
                symbol = pair['symbol']
                pair_type_str = pair['pair_type']
                
                # Configure exchange for spot or futures
                if pair_type_str == 'future':
                    exchange.options['defaultType'] = 'future'
                else:
                    exchange.options['defaultType'] = 'spot'
                
                # Fetch OHLCV data
                ohlcv = exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=20)
                
                if len(ohlcv) >= 10:
                    df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
                    
                    # Calculate volume metrics
                    recent_volume = df['volume'].tail(5).mean()
                    previous_volume = df['volume'].iloc[-10:-5].mean()
                    
                    if previous_volume > 0:
                        volume_ratio = recent_volume / previous_volume
                        
                        # Detect volume spike
                        if volume_ratio >= 2.0:  # 200% volume increase
                            volume_alerts.append({
                                "symbol": symbol,
                                "pair_type": pair_type_str,
                                "volume_ratio": float(volume_ratio),
                                "current_volume": float(recent_volume),
                                "previous_volume": float(previous_volume),
                                "timeframe": timeframe
                            })
                        
                        # Calculate price change
                        current_price = float(df.iloc[-1]['close'])
                        prev_price = float(df.iloc[-2]['close'])
                        price_change = ((current_price - prev_price) / prev_price) * 100
                        
                        # Detect simple patterns
                        pattern = detect_simple_pattern(df)
                        
                        if pattern:
                            pattern_alerts.append({
                                "symbol": symbol,
                                "pair_type": pair_type_str,
                                "pattern": pattern,
                                "price_change": float(price_change),
                                "current_price": current_price
                            })
                        
                        results.append({
                            "symbol": symbol,
                            "pair_type": pair_type_str,
                            "current_price": current_price,
                            "price_change": float(price_change),
                            "volume_ratio": float(volume_ratio),
                            "current_volume": float(recent_volume),
                            "pattern": pattern
                        })
                
                # Rate limiting - delay between requests
                if i < len(pairs) - 1:
                    time.sleep(delay_ms / 1000)
                
                # Progress update
                if (i + 1) % 10 == 0:
                    print(f"  Progress: {i + 1}/{len(pairs)} pairs scanned")
                
            except ccxt.RateLimitExceeded:
                print("Rate limit exceeded, waiting 1 second...")
                time.sleep(1)
                continue
            except ccxt.NetworkError:
                print(f"Network error for {pair['symbol']}, skipping...")
                continue
            except Exception as e:
                print(f"Error scanning {pair['symbol']}: {str(e)[:100]}")
                continue
        
        # Sort results by volume ratio (highest first)
        results.sort(key=lambda x: x.get('volume_ratio', 0), reverse=True)
        
        return jsonify({
            "success": True,
            "scanned_pairs": len(pairs),
            "successful_scans": len(results),
            "volume_alerts": len(volume_alerts),
            "pattern_alerts": len(pattern_alerts),
            "timeframe": timeframe,
            "results": results[:50],  # Return top 50
            "volume_alerts_list": volume_alerts[:20],
            "pattern_alerts_list": pattern_alerts[:20],
            "timestamp": datetime.utcnow().isoformat()
        })
        
    except Exception as e:
        print(f"Scan error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"success": False, "error": str(e)}), 500

def detect_simple_pattern(df):
    """Detect simple candle patterns"""
    if len(df) < 3:
        return None
    
    opens = df['open'].values
    highs = df['high'].values
    lows = df['low'].values
    closes = df['close'].values
    
    # Last 3 candles
    o1, o2, o3 = opens[-3], opens[-2], opens[-1]
    h1, h2, h3 = highs[-3], highs[-2], highs[-1]
    l1, l2, l3 = lows[-3], lows[-2], lows[-1]
    c1, c2, c3 = closes[-3], closes[-2], closes[-1]
    
    # Bullish Engulfing
    if c2 < o2 and c3 > o3 and o3 < c2 and c3 > o2:
        return "BULLISH_ENGULFING"
    
    # Bearish Engulfing
    if c2 > o2 and c3 < o3 and o3 > c2 and c3 < o2:
        return "BEARISH_ENGULFING"
    
    # Hammer (bullish reversal)
    body = abs(c3 - o3)
    lower_shadow = min(o3, c3) - l3
    upper_shadow = h3 - max(o3, c3)
    
    if lower_shadow > body * 2 and upper_shadow < body * 0.1:
        return "HAMMER"
    
    # Shooting Star (bearish reversal)
    if upper_shadow > body * 2 and lower_shadow < body * 0.1:
        return "SHOOTING_STAR"
    
    # Three White Soldiers
    if c1 > o1 and c2 > o2 and c3 > o3 and c1 < c2 < c3:
        return "THREE_WHITE_SOLDIERS"
    
    # Three Black Crows
    if c1 < o1 and c2 < o2 and c3 < o3 and c1 > c2 > c3:
        return "THREE_BLACK_CROWS"
    
    return None

@app.route("/continuous_scan", methods=["POST"])
def continuous_scan():
    """
    Start continuous scanning with configurable parameters
    """
    payload = request.get_json() or {}
    interval_minutes = int(payload.get("interval", 5))
    max_pairs_per_scan = int(payload.get("max_pairs", 50))
    quote_asset = payload.get("quote_asset", "USDT")
    
    # Store scan configuration (in production, use a proper task queue)
    global scan_config
    scan_config = {
        "active": True,
        "interval": interval_minutes,
        "max_pairs": max_pairs_per_scan,
        "quote_asset": quote_asset,
        "last_scan": None,
        "next_scan": datetime.utcnow() + timedelta(minutes=interval_minutes)
    }
    
    # Start background thread for continuous scanning
    import threading
    scan_thread = threading.Thread(target=continuous_scan_worker, daemon=True)
    scan_thread.start()
    
    return jsonify({
        "success": True,
        "message": f"Continuous scan started. Scanning every {interval_minutes} minutes.",
        "config": scan_config
    })

def continuous_scan_worker():
    """Background worker for continuous scanning"""
    global scan_config
    
    while scan_config.get("active", False):
        try:
            # Run scan
            scan_config["last_scan"] = datetime.utcnow()
            
            # Call the scan function
            # Note: In production, you'd call this properly
            print(f"Running scheduled scan at {scan_config['last_scan']}")
            
            # Wait for next scan
            next_scan = scan_config["next_scan"]
            wait_seconds = (next_scan - datetime.utcnow()).total_seconds()
            
            if wait_seconds > 0:
                time.sleep(wait_seconds)
            
            # Update next scan time
            scan_config["next_scan"] = datetime.utcnow() + timedelta(
                minutes=scan_config["interval"]
            )
            
        except Exception as e:
            print(f"Continuous scan error: {e}")
            time.sleep(60)  # Wait a minute on error

@app.route("/stop_continuous_scan", methods=["POST"])
def stop_continuous_scan():
    """Stop continuous scanning"""
    global scan_config
    scan_config["active"] = False
    
    return jsonify({
        "success": True,
        "message": "Continuous scan stopped"
    })

@app.route("/get_scan_status", methods=["GET"])
def get_scan_status():
    """Get current scan status"""
    global scan_config
    
    return jsonify({
        "success": True,
        "active": scan_config.get("active", False),
        "config": scan_config
    })

# Initialize scan config
scan_config = {
    "active": False,
    "interval": 5,
    "max_pairs": 50,
    "quote_asset": "USDT",
    "last_scan": None,
    "next_scan": None
}

@app.route("/enhanced_scan_candle_patterns", methods=["POST"])
def enhanced_scan_candle_patterns():
    """
    Enhanced scanner that works with all Binance pairs
    """
    payload = request.get_json() or {}
    timeframe = payload.get("timeframe", "15m")
    volume_threshold = float(payload.get("volume_threshold", 1.5))
    min_volume_usd = float(payload.get("min_volume_usd", 100000))
    max_symbols = int(payload.get("max_symbols", 100))
    pair_type = payload.get("pair_type", "spot")
    
    try:
        # Get pairs from database
        conn = get_conn()
        cur = conn.cursor(dictionary=True)
        
        # Get active USDT pairs with estimated volume
        query = """
        SELECT DISTINCT b.symbol, b.pair_type, g.volume_24h
        FROM binance_all_pairs b
        LEFT JOIN daily_gainers_losers g ON b.symbol = g.symbol AND DATE(g.fetched_at) = CURDATE()
        WHERE b.status = 'active'
        AND b.pair_type = %s
        AND (b.quote_asset = 'USDT' OR b.symbol LIKE '%/USDT')
        AND (g.volume_24h IS NULL OR g.volume_24h >= %s)
        ORDER BY COALESCE(g.volume_24h, 0) DESC
        LIMIT %s
        """
        
        cur.execute(query, (pair_type, min_volume_usd, max_symbols))
        pairs = cur.fetchall()
        cur.close()
        conn.close()
        
        if not pairs:
            # Fallback: get any USDT pairs
            conn = get_conn()
            cur = conn.cursor(dictionary=True)
            cur.execute("""
                SELECT symbol, pair_type 
                FROM binance_all_pairs 
                WHERE status = 'active' 
                AND pair_type = %s
                AND (quote_asset = 'USDT' OR symbol LIKE '%/USDT')
                LIMIT %s
            """, (pair_type, max_symbols))
            pairs = cur.fetchall()
            cur.close()
            conn.close()
        
        results = []
        
        # Initialize exchange
        exchange = ccxt.binance({
            'enableRateLimit': True,
            'rateLimit': 1000,
        })
        
        for i, pair in enumerate(pairs):
            try:
                symbol = pair['symbol']
                
                # Set exchange type
                exchange.options['defaultType'] = pair['pair_type']
                
                # Fetch OHLCV data
                ohlcv = exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=50)
                
                if len(ohlcv) >= 20:
                    df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
                    
                    # Calculate volume metrics
                    recent_volume = df['volume'].tail(5).mean()
                    previous_volume = df['volume'].iloc[-20:-5].mean()
                    
                    if previous_volume > 0:
                        volume_ratio = recent_volume / previous_volume
                        
                        if volume_ratio >= volume_threshold:
                            # Detect patterns
                            patterns = detect_enhanced_patterns(df)
                            
                            # Calculate price metrics
                            current_price = float(df.iloc[-1]['close'])
                            prev_close = float(df.iloc[-2]['close'])
                            price_change = ((current_price - prev_close) / prev_close) * 100
                            
                            # Get 24h volume if available
                            volume_24h = float(pair.get('volume_24h', 0))
                            
                            results.append({
                                "symbol": symbol,
                                "pair_type": pair['pair_type'],
                                "current_price": current_price,
                                "price_change_24h": float(price_change),
                                "volume_24h": volume_24h,
                                "volume_ratio": round(volume_ratio, 2),
                                "volume_spike": volume_ratio >= volume_threshold,
                                "patterns": patterns,
                                "timeframe": timeframe,
                                "timestamp": datetime.utcnow().isoformat()
                            })
                    
                    # Rate limiting
                    time.sleep(0.1)  # 100ms delay
                
            except Exception as e:
                print(f"Error analyzing {pair['symbol']}: {str(e)[:100]}")
                continue
        
        # Sort by volume ratio
        results.sort(key=lambda x: x['volume_ratio'], reverse=True)
        
        return jsonify({
            "success": True,
            "scanned_symbols": len(pairs),
            "matches": len(results),
            "timeframe": timeframe,
            "volume_threshold": volume_threshold,
            "pair_type": pair_type,
            "results": results[:50]  # Return top 50
        })
        
    except Exception as e:
        print(f"Enhanced scan error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"success": False, "error": str(e)}), 500

def detect_enhanced_patterns(df):
    """Enhanced pattern detection"""
    patterns = []
    
    if len(df) < 10:
        return patterns
    
    opens = df['open'].values
    highs = df['high'].values
    lows = df['low'].values
    closes = df['close'].values
    
    # Check last 5 candles
    for i in range(max(0, len(df)-5), len(df)-1):
        # Doji
        body = abs(closes[i] - opens[i])
        total_range = highs[i] - lows[i]
        if total_range > 0 and body / total_range < 0.1:
            patterns.append("DOJI")
        
        # Marubozu
        if body / total_range > 0.9:
            if closes[i] > opens[i]:
                patterns.append("BULLISH_MARUBOZU")
            else:
                patterns.append("BEARISH_MARUBOZU")
        
        # Spinning Top
        upper_shadow = highs[i] - max(opens[i], closes[i])
        lower_shadow = min(opens[i], closes[i]) - lows[i]
        if body / total_range < 0.3 and upper_shadow > body and lower_shadow > body:
            patterns.append("SPINNING_TOP")
    
    # Remove duplicates
    return list(set(patterns))[:3]  # Return max 3 unique patterns
# End


def on_message_huobi(ws, message):
    try:
        # Huobi sends gzipped data, so we need to decompress it
        try:
            # Try to decompress if it's gzipped
            if isinstance(message, bytes):
                # Check if it's gzipped by looking for gzip magic number
                if len(message) > 2 and message[0:2] == b'\x1f\x8b':
                    message = gzip.decompress(message).decode('utf-8')
                else:
                    message = message.decode('utf-8')
        except:
            # If decompression fails, try to decode as string
            if isinstance(message, bytes):
                message = message.decode('utf-8', errors='ignore')
        
        # Verify we're still tracking the right symbol
        current_symbol = real_time_data["current_symbol"].replace('/', '')
        
        # Check for ping response
        if 'ping' in message:
            try:
                data = json.loads(message)
                pong_msg = {'pong': data['ping']}
                ws.send(json.dumps(pong_msg))
                return
            except:
                pass
        
        try:
            data = json.loads(message)
        except json.JSONDecodeError:
            print(f"Huobi message is not valid JSON: {message[:100]}")
            return
        
        # Only process if this is for our current symbol
        if 'ch' in data:
            channel = data['ch']
            if current_symbol.lower() not in channel:
                return  # Skip messages for other symbols
        
        # Handle order book updates
        if 'depth.step0' in str(data.get('ch', '')):
            if 'tick' in data:
                tick = data['tick']
                bids = tick.get('bids', [])
                asks = tick.get('asks', [])
                update_order_book("huobi", bids, asks)
        
        # Handle trade updates
        elif 'trade.detail' in str(data.get('ch', '')):
            if 'tick' in data:
                tick = data['tick']
                if 'data' in tick:
                    for trade in tick['data']:
                        side = 'b' if trade.get('direction') == 'buy' else 's'
                        price = trade.get('price')
                        amount = trade.get('amount')
                        
                        if price and amount:
                            process_trade("huobi", {
                                "price": float(price),
                                "volume": float(amount),
                                "timestamp": time.time(),
                                "side": side
                            })
                
    except Exception as e:
        print(f"Huobi message error: {e}")
        # Don't print the full message as it might be binary

def on_message_kraken(ws, message):
    try:
        data = json.loads(message)
        
        # Check for system status
        if isinstance(data, list):
            # Kraken sends arrays for updates
            channel_name = data[-2] if len(data) > 2 else ''
            
            # Check if this is for our symbol
            if 'book' in str(channel_name) or 'trade' in str(channel_name):
                # For simplicity, we'll just update with placeholder data
                # In production, you'd want to parse Kraken's specific format
                pass
                
    except Exception as e:
        print(f"Kraken message error: {e}")

def on_message_bitget(ws, message):
    try:
        data = json.loads(message)
        
        # Handle order book updates
        if data.get('action') == 'snapshot' and data.get('arg', {}).get('channel') == 'books':
            if 'data' in data:
                for book_data in data['data']:
                    bids = book_data.get('bids', [])
                    asks = book_data.get('asks', [])
                    update_order_book("bitget", bids, asks)
        
        # Handle trade updates - FIXED: Added proper indexing checks
        elif data.get('action') == 'update' and data.get('arg', {}).get('channel') == 'trade':
            if 'data' in data:
                for trade_data in data['data']:
                    if isinstance(trade_data, list):
                        for trade in trade_data:
                            # Check if trade has enough elements
                            if isinstance(trade, list) and len(trade) >= 3:
                                side = 'b' if trade[0] == 'buy' else 's'
                                price = trade[1]
                                volume = trade[2]
                                
                                if price and volume:
                                    process_trade("bitget", {
                                        "price": float(price),
                                        "volume": float(volume),
                                        "timestamp": time.time(),
                                        "side": side
                                    })
                            elif isinstance(trade, dict):
                                # Handle dictionary format if present
                                side = 'b' if trade.get('side') == 'buy' else 's'
                                price = trade.get('price')
                                volume = trade.get('size') or trade.get('volume')
                                
                                if price and volume:
                                    process_trade("bitget", {
                                        "price": float(price),
                                        "volume": float(volume),
                                        "timestamp": time.time(),
                                        "side": side
                                    })
                
    except Exception as e:
        print(f"Bitget message error: {e}")
        # Print the raw message for debugging
        try:
            print(f"Raw Bitget message: {message[:200]}")
        except:
            pass

def on_message_mexc(ws, message):
    try:
        data = json.loads(message)
        
        # Handle order book updates
        if 'deals' in str(data.get('c', '')):
            # Trade updates
            if 'd' in data:
                for trade in data['d'].get('deals', []):
                    side = 'b' if trade.get('S') == 1 else 's'
                    price = trade.get('p')
                    volume = trade.get('v')
                    
                    if price and volume:
                        process_trade("mexc", {
                            "price": float(price),
                            "volume": float(volume),
                            "timestamp": time.time(),
                            "side": side
                        })
        
        # Handle ticker updates (for price)
        elif 'miniTicker' in str(data.get('c', '')):
            if 'd' in data:
                ticker = data['d']
                price = ticker.get('c')
                if price:
                    # Create a synthetic trade for price updates
                    process_trade("mexc", {
                        "price": float(price),
                        "volume": 0.001,
                        "timestamp": time.time(),
                        "side": 'b'  # Default to buy
                    })
                
    except Exception as e:
        print(f"MEXC message error: {e}")

def on_message_coinbase(ws, message):
    try:
        data = json.loads(message)
        
        # Handle order book updates
        if data.get('type') == 'l2update':
            # Level 2 order book update
            if 'changes' in data:
                # Coinbase sends incremental updates
                # For simplicity, we'll just note that we have data
                if 'product_id' in data:
                    # Verify symbol
                    current_symbol = real_time_data["current_symbol"].replace('/', '-')
                    if data['product_id'] == current_symbol:
                        # We have order book data for this symbol
                        pass
        
        # Handle trade updates
        elif data.get('type') == 'match':
            side = 'b' if data.get('side') == 'buy' else 's'
            price = data.get('price')
            size = data.get('size')
            
            if price and size:
                process_trade("coinbase", {
                    "price": float(price),
                    "volume": float(size),
                    "timestamp": time.time(),
                    "side": side
                })
                
    except Exception as e:
        print(f"Coinbase message error: {e}")

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
def get_realtime_data():
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
    return jsonify({"status": "ok", "message": "SUPER BOT v4 running with 10 exchanges"})

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
    # Removed Kucoin from Code "kucoin", 
    for exchange in ["binance", "bybit", "okx", "gateio", "huobi", "kraken", "bitget", "mexc", "coinbase"]:
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
    # Removed KuCoin From Code "kucoin",
    for exchange in ["binance", "bybit", "okx", "gateio", "huobi", "kraken", "bitget", "mexc", "coinbase"]:
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
    print("🚀 SUPER BOT v4.1 Starting...")
    print("📊 Database: crypto_data")
    print("🌐 WebSocket: Real-time order flow enabled with 10 EXCHANGES")
    print("🔗 API: http://0.0.0.0:8000")
    print("=" * 50)
    print("🎯 ENHANCED PREDICTION SYSTEM READY WITH:")
    print("  • Multi-timeframe analysis (1H, 4H, 1D, 1W)")
    print("  • Long/Short signals with confidence levels")
    print("  • Support/Resistance levels")
    print("  • TradingView chart integration")
    print("  • Prediction history tracking")
    print("  • Technical analysis summary")
    print("  • NEW: 10 Exchange Real-Time Analysis")
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
    
    print("\n📝 ENHANCED WORKFLOW:")
    print("1. Fetch data (OHLCV tab)")
    print("2. Train model (Train Bot tab)")
    print("3. Go to Real-Time Analysis tab for live order book & trade analysis")
    print("4. View TradingView chart and signals in Predictions tab")
    print("\n⚡ Starting server with 10 exchanges...")
    
    # Start WebSockets with initial symbol
    start_websockets()
    
    # Add a small delay to let WebSockets connect
    print("⏳ Waiting for WebSocket connections to establish...")
    time.sleep(3)
    
    # Check initial WebSocket status
    # Removed Kucoin from code "kucoin", 
    print("\n🔍 Initial WebSocket status for 10 exchanges:")
    exchanges_list = ["binance", "bybit", "okx", "gateio", "huobi", "kraken", "bitget", "mexc", "coinbase"]
    for exchange in exchanges_list:
        book = real_time_data["order_book"][exchange]
        if book["bids"] or book["asks"]:
            print(f"   {exchange}: ✓ Connected")
        else:
            print(f"   {exchange}: ⚠️ Waiting for data...")
    
    print("\n✅ Server ready! Use /verify_symbol endpoint to check WebSocket status.")
    print("✅ Use /set_symbol endpoint to change live tracking symbol.")
    print("✅ Real-Time Analysis tab ready for 10 exchange order book & trade analysis!")
    print("✅ Enhanced Predictions tab ready for multi-timeframe analysis!")
    
    app.run(host="0.0.0.0", port=8000, debug=False, threaded=True)