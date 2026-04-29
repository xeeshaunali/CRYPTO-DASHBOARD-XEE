# manipulation_detector.py
import numpy as np
import pandas as pd
from datetime import datetime
from typing import Dict, List, Any, Optional, Tuple

def analyze_manipulation(ohlcv_rows: List[Dict], symbol: str, timeframe: str, 
                         order_book: Dict = None, trades: List = None) -> Dict:
    """
    Analyze a symbol for 4-phase market manipulation patterns:
    Phase 1: Accumulation (silent volume increase, price range compression)
    Phase 2: Fake-Out (breakout above/below with volume spike)
    Phase 3: Stop Hunt (liquidity sweep, wick through key levels)
    Phase 4: Result (reversal, trapping traders)
    """
    
    if len(ohlcv_rows) < 30:
        return {"error": "Insufficient data", "composite_score": 0}
    
    # Convert to DataFrame
    df = pd.DataFrame(ohlcv_rows)
    for col in ['open', 'high', 'low', 'close', 'volume']:
        if col in df.columns:
            df[col] = df[col].astype(float)
    df = df.sort_values('time_utc').reset_index(drop=True)
    
    opens = df['open'].values
    highs = df['high'].values
    lows = df['low'].values
    closes = df['close'].values
    volumes = df['volume'].values
    
    current_price = float(closes[-1])
    current_volume = float(volumes[-1])
    
    # ============ PHASE 1: ACCUMULATION DETECTION ============
    phase1_score = 0
    phase1_evidence = {}
    
    # Check for price range compression (narrowing range before move)
    if len(highs) >= 20:
        recent_highs = highs[-20:]
        recent_lows = lows[-20:]
        price_range_pct = ((max(recent_highs) - min(recent_lows)) / min(recent_lows)) * 100
        phase1_evidence['price_range_pct'] = round(price_range_pct, 2)
        
        # Tight range = accumulation
        if price_range_pct < 5:
            phase1_score += 25
        elif price_range_pct < 10:
            phase1_score += 15
        elif price_range_pct < 15:
            phase1_score += 5
    
    # Check for volume increase during consolidation
    if len(volumes) >= 20:
        recent_vol = np.mean(volumes[-10:])
        prev_vol = np.mean(volumes[-20:-10])
        volume_ratio = recent_vol / prev_vol if prev_vol > 0 else 1
        phase1_evidence['volume_ratio'] = round(volume_ratio, 2)
        
        if volume_ratio > 1.5:
            phase1_score += 20
        elif volume_ratio > 1.2:
            phase1_score += 10
    
    # Check for volume trend (increasing volume)
    if len(volumes) >= 15:
        vol_slope = np.polyfit(range(10), volumes[-10:], 1)[0]
        phase1_evidence['vol_slope_positive'] = vol_slope > 0
        if vol_slope > 0:
            phase1_score += 15
    
    # Check for low volatility / doji candles
    doji_count = 0
    for i in range(max(0, len(closes)-15), len(closes)-1):
        body = abs(closes[i] - opens[i])
        total_range = highs[i] - lows[i]
        if total_range > 0 and body / total_range < 0.1:
            doji_count += 1
    phase1_evidence['doji_count'] = doji_count
    if doji_count >= 3:
        phase1_score += 10
    
    phase1_detected = phase1_score >= 40
    phase1_evidence['detected'] = phase1_detected
    phase1_evidence['score'] = phase1_score
    
    # ============ PHASE 2: FAKE-OUT DETECTION ============
    phase2_score = 0
    phase2_evidence = {}
    
    # Find support and resistance levels
    lookback = min(30, len(highs))
    resistance_level = np.percentile(highs[-lookback:-5], 90) if len(highs) > 10 else highs[-1]
    support_level = np.percentile(lows[-lookback:-5], 10) if len(lows) > 10 else lows[-1]
    phase2_evidence['resistance'] = round(resistance_level, 6)
    phase2_evidence['support'] = round(support_level, 6)
    
    # Check for breakout above resistance or below support in last 5 candles
    breakouts = []
    for i in range(max(0, len(closes)-10), len(closes)-1):
        # Above resistance
        if highs[i] > resistance_level * 1.01:
            breakouts.append({'type': 'above', 'index': i, 'price': highs[i]})
            phase2_score += 15
            phase2_evidence['breakout_above'] = round(highs[i], 6)
        # Below support
        if lows[i] < support_level * 0.99:
            breakouts.append({'type': 'below', 'index': i, 'price': lows[i]})
            phase2_score += 15
            phase2_evidence['breakout_below'] = round(lows[i], 6)
    
    # Check if breakout had volume spike
    for i in range(max(0, len(volumes)-10), len(volumes)-1):
        if i > 0 and volumes[i] > volumes[i-1] * 1.5:
            if i in [b['index'] for b in breakouts]:
                phase2_score += 10
                phase2_evidence['volume_excess'] = round(volumes[i] / volumes[i-1], 2)
    
    # Check if price quickly reversed after breakout (fake-out)
    for breakout in breakouts:
        idx = breakout['index']
        if idx + 2 < len(closes):
            if breakout['type'] == 'above':
                # Price should close below breakout level within 2 candles
                if closes[idx+2] < breakout['price']:
                    phase2_score += 20
                    phase2_evidence['reversal_above'] = True
            else:
                if closes[idx+2] > breakout['price']:
                    phase2_score += 20
                    phase2_evidence['reversal_below'] = True
    
    # Determine fake-out direction
    fakeout_direction = "NEUTRAL"
    if phase2_evidence.get('breakout_above') and phase2_evidence.get('reversal_above'):
        fakeout_direction = "BEARISH_FAKEOUT"
        phase2_score += 15
    elif phase2_evidence.get('breakout_below') and phase2_evidence.get('reversal_below'):
        fakeout_direction = "BULLISH_FAKEOUT"
        phase2_score += 15
    
    phase2_evidence['direction'] = fakeout_direction
    phase2_detected = phase2_score >= 40
    phase2_evidence['detected'] = phase2_detected
    phase2_evidence['score'] = phase2_score
    
    # ============ PHASE 3: STOP HUNT DETECTION ============
    phase3_score = 0
    phase3_evidence = {}
    
    # Find equal highs/lows (inducement zones)
    eq_tolerance = 0.002  # 0.2%
    inducement_highs = []
    inducement_lows = []
    
    for i in range(5, len(highs)-1):
        window_h = highs[max(0, i-10):i]
        for prev_h in window_h:
            if prev_h > 0 and abs(highs[i] - prev_h) / prev_h < eq_tolerance:
                inducement_highs.append(highs[i])
                break
        window_l = lows[max(0, i-10):i]
        for prev_l in window_l:
            if prev_l > 0 and abs(lows[i] - prev_l) / prev_l < eq_tolerance:
                inducement_lows.append(lows[i])
                break
    
    phase3_evidence['inducement_highs'] = [round(h, 6) for h in inducement_highs[-5:]]
    phase3_evidence['inducement_lows'] = [round(l, 6) for l in inducement_lows[-5:]]
    
    # Check for wick sweeps (liquidity grabs)
    sweeps = []
    for i in range(max(5, len(highs)-20), len(highs)-1):
        candle_range = highs[i] - lows[i]
        if candle_range == 0:
            continue
        
        upper_wick = highs[i] - max(opens[i], closes[i])
        lower_wick = min(opens[i], closes[i]) - lows[i]
        
        # Bearish sweep: wick above resistance then close down
        if upper_wick / candle_range > 0.4:
            # Check if it swept an inducement high
            for ih in inducement_highs:
                if abs(highs[i] - ih) / ih < 0.005:
                    sweeps.append({'type': 'BEARISH', 'price': highs[i], 'index': i})
                    phase3_score += 20
                    phase3_evidence['bearish_sweep'] = round(highs[i], 6)
                    break
        
        # Bullish sweep: wick below support then close up
        if lower_wick / candle_range > 0.4:
            for il in inducement_lows:
                if abs(lows[i] - il) / il < 0.005:
                    sweeps.append({'type': 'BULLISH', 'price': lows[i], 'index': i})
                    phase3_score += 20
                    phase3_evidence['bullish_sweep'] = round(lows[i], 6)
                    break
    
    # Check volume on sweep candles
    for sweep in sweeps:
        idx = sweep['index']
        if idx > 0 and volumes[idx] > volumes[idx-1] * 1.3:
            phase3_score += 10
            phase3_evidence['sweep_volume_spike'] = round(volumes[idx] / volumes[idx-1], 2)
    
    # Check for wick-to-body ratio
    last_candle = df.iloc[-1]
    last_range = last_candle['high'] - last_candle['low']
    if last_range > 0:
        last_upper_wick = last_candle['high'] - max(last_candle['open'], last_candle['close'])
        last_lower_wick = min(last_candle['open'], last_candle['close']) - last_candle['low']
        last_wick_ratio = max(last_upper_wick, last_lower_wick) / last_range
        phase3_evidence['last_wick_ratio'] = round(last_wick_ratio, 2)
        
        if last_wick_ratio > 0.5:
            phase3_score += 10
            phase3_evidence['long_wick_warning'] = True
    
    phase3_detected = phase3_score >= 40
    phase3_evidence['detected'] = phase3_detected
    phase3_evidence['score'] = phase3_score
    
    # ============ PHASE 4: RESULT (TRAP OUTCOME) ============
    phase4_score = 0
    phase4_evidence = {}
    
    # Check price movement after potential stop hunt
    if len(closes) >= 5:
        recent_close = closes[-1]
        close_5_ago = closes[-5]
        price_move_pct = ((recent_close - close_5_ago) / close_5_ago) * 100
        phase4_evidence['move_pct'] = round(price_move_pct, 2)
        
        # Direction based on sweeps
        bullish_sweeps = [s for s in sweeps if s['type'] == 'BULLISH']
        bearish_sweeps = [s for s in sweeps if s['type'] == 'BEARISH']
        
        if bullish_sweeps and price_move_pct > 2:
            phase4_score += 25
            phase4_evidence['bullish_result'] = True
            phase4_evidence['direction'] = "BULLISH_RESULT"
        elif bearish_sweeps and price_move_pct < -2:
            phase4_score += 25
            phase4_evidence['bearish_result'] = True
            phase4_evidence['direction'] = "BEARISH_RESULT"
    
    # Check volume confirmation
    if len(volumes) >= 5:
        recent_vol_avg = np.mean(volumes[-3:])
        prev_vol_avg = np.mean(volumes[-8:-3])
        volume_surge = recent_vol_avg / prev_vol_avg if prev_vol_avg > 0 else 1
        phase4_evidence['volume_surge'] = round(volume_surge, 2)
        
        if volume_surge > 1.3 and abs(phase4_evidence.get('move_pct', 0)) > 1:
            phase4_score += 15
    
    phase4_detected = phase4_score >= 40
    phase4_evidence['detected'] = phase4_detected
    phase4_evidence['score'] = phase4_score
    
    # ============ COMPOSITE SCORE & MANIPULATION TYPE ============
    # Weighted composite (phases have different importance)
    composite_score = (
        phase1_score * 0.20 +
        phase2_score * 0.25 +
        phase3_score * 0.30 +
        phase4_score * 0.25
    )
    
    # Determine manipulation type
    manipulation_type = "NONE"
    if phase1_detected and phase2_detected and phase3_detected:
        manipulation_type = "FULL_MANIPULATION"
    elif phase2_detected and phase3_detected:
        manipulation_type = "STOP_HUNT"
    elif phase1_detected and phase2_detected:
        manipulation_type = "PUMP_AND_DUMP"
    elif phase2_detected:
        manipulation_type = "FAKEOUT"
    elif phase3_detected:
        manipulation_type = "LIQUIDITY_SWEEP"
    elif phase1_detected:
        manipulation_type = "ACCUMULATION"
    
    # Determine risk level
    if composite_score >= 70:
        risk_level = "CRITICAL"
        risk_color = "#dc2626"
    elif composite_score >= 50:
        risk_level = "HIGH"
        risk_color = "#f97316"
    elif composite_score >= 30:
        risk_level = "MODERATE"
        risk_color = "#eab308"
    else:
        risk_level = "LOW"
        risk_color = "#10b981"
    
    # Trading recommendation
    recommendation = generate_recommendation(manipulation_type, fakeout_direction, 
                                              phase3_evidence, phase4_evidence, current_price)
    
    # Order book signals (if available)
    ob_signals = analyze_order_book_signals(order_book, trades) if order_book else None
    
    # Prepare response
    phases = {
        "phase1_accumulation": {
            "detected": phase1_detected,
            "score": round(phase1_score, 1),
            "evidence": phase1_evidence
        },
        "phase2_fakeout": {
            "detected": phase2_detected,
            "score": round(phase2_score, 1),
            "evidence": phase2_evidence
        },
        "phase3_stop_hunt": {
            "detected": phase3_detected,
            "score": round(phase3_score, 1),
            "evidence": phase3_evidence
        },
        "phase4_result": {
            "detected": phase4_detected,
            "score": round(phase4_score, 1),
            "evidence": phase4_evidence
        }
    }
    
    # Count phases detected
    phases_detected = sum([phase1_detected, phase2_detected, phase3_detected, phase4_detected])
    
    # Price change
    price_change = ((closes[-1] - closes[-2]) / closes[-2] * 100) if len(closes) >= 2 else 0
    
    # Volume spike ratio
    volume_spike = volumes[-1] / np.mean(volumes[-10:-2]) if len(volumes) >= 10 else 1
    
    return {
        "success": True,
        "symbol": symbol,
        "timeframe": timeframe,
        "current_price": round(current_price, 6),
        "price_change": round(price_change, 2),
        "volume_spike": round(volume_spike, 2),
        "composite_score": round(composite_score, 1),
        "risk_level": risk_level,
        "risk_color": risk_color,
        "manipulation_type": manipulation_type,
        "phases_detected": phases_detected,
        "phases": phases,
        "recommendation": recommendation,
        "order_book_signals": ob_signals,
        "timestamp": datetime.utcnow().isoformat()
    }


def generate_recommendation(manip_type: str, fakeout_dir: str, 
                            phase3_evidence: Dict, phase4_evidence: Dict, 
                            current_price: float) -> str:
    """Generate trading recommendation based on detected manipulation"""
    
    if manip_type == "FULL_MANIPULATION":
        if phase4_evidence.get('direction') == "BULLISH_RESULT":
            return f"🚀 STRONG BUY - Manipulation complete! Price likely to continue upward. Enter LONG with stop below sweep level."
        elif phase4_evidence.get('direction') == "BEARISH_RESULT":
            return f"🔥 STRONG SELL - Manipulation complete! Price likely to continue downward. Enter SHORT with stop above sweep level."
    
    elif manip_type == "STOP_HUNT":
        if phase3_evidence.get('bullish_sweep'):
            return f"🎯 BULLISH STOP HUNT DETECTED - Liquidity grabbed below support. Price likely to reverse UP. Consider LONG entry."
        elif phase3_evidence.get('bearish_sweep'):
            return f"🎯 BEARISH STOP HUNT DETECTED - Liquidity grabbed above resistance. Price likely to reverse DOWN. Consider SHORT entry."
    
    elif manip_type == "PUMP_AND_DUMP":
        if fakeout_dir == "BULLISH_FAKEOUT":
            return f"⚠️ PUMP & DUMP WARNING - Fake breakout above resistance. Price likely to dump. Consider SHORT."
        else:
            return f"⚠️ PUMP & DUMP WARNING - Fake breakdown below support. Price likely to pump. Consider LONG."
    
    elif manip_type == "FAKEOUT":
        if fakeout_dir == "BEARISH_FAKEOUT":
            return f"📉 BEARISH FAKEOUT - Price broke above but reversed. Watch for short opportunity."
        elif fakeout_dir == "BULLISH_FAKEOUT":
            return f"📈 BULLISH FAKEOUT - Price broke below but reversed. Watch for long opportunity."
    
    elif manip_type == "LIQUIDITY_SWEEP":
        if phase3_evidence.get('bullish_sweep'):
            return f"🟢 BULLISH SWEEP - Liquidity taken below. Expect reversal up. Consider LONG."
        else:
            return f"🔴 BEARISH SWEEP - Liquidity taken above. Expect reversal down. Consider SHORT."
    
    elif manip_type == "ACCUMULATION":
        return f"📦 ACCUMULATION DETECTED - Smart money building position. Watch for breakout and fakeout before entering."
    
    return f"⏸️ NEUTRAL - No clear manipulation pattern detected. Wait for confirmation."


def analyze_order_book_signals(order_book: Dict, trades: List) -> Dict:
    """Analyze order book for manipulation signals"""
    if not order_book:
        return None
    
    signals = []
    imbalance = 0
    
    try:
        # Check for large bid/ask walls
        for exchange, book in order_book.items():
            bids = book.get('bids', [])
            asks = book.get('asks', [])
            
            if bids and asks:
                # Calculate imbalance
                top_bid = bids[0][1] if bids else 0
                top_ask = asks[0][1] if asks else 0
                total = top_bid + top_ask
                if total > 0:
                    ex_imbalance = (top_bid - top_ask) / total
                    imbalance += ex_imbalance
                
                # Detect walls
                if len(bids) > 5:
                    avg_bid = np.mean([q for _, q in bids[:5]])
                    if bids[0][1] > avg_bid * 3:
                        signals.append({
                            "type": "LARGE_BID_WALL",
                            "severity": "HIGH",
                            "desc": f"Large bid wall at {bids[0][0]} on {exchange}"
                        })
                
                if len(asks) > 5:
                    avg_ask = np.mean([q for _, q in asks[:5]])
                    if asks[0][1] > avg_ask * 3:
                        signals.append({
                            "type": "LARGE_ASK_WALL",
                            "severity": "HIGH",
                            "desc": f"Large ask wall at {asks[0][0]} on {exchange}"
                        })
        
        imbalance = imbalance / len(order_book) if order_book else 0
        
        # Check trade aggression
        buy_vol_60s = 0
        sell_vol_60s = 0
        now = datetime.now().timestamp()
        
        if trades:
            for trade in trades[-100:]:
                if now - trade[2] <= 60:
                    if trade[3] == 'b':
                        buy_vol_60s += trade[1]
                    else:
                        sell_vol_60s += trade[1]
        
        if buy_vol_60s > sell_vol_60s * 1.5:
            signals.append({
                "type": "BUY_AGGRESSION",
                "severity": "MEDIUM",
                "desc": "Strong buying pressure in last 60 seconds"
            })
        elif sell_vol_60s > buy_vol_60s * 1.5:
            signals.append({
                "type": "SELL_AGGRESSION",
                "severity": "MEDIUM",
                "desc": "Strong selling pressure in last 60 seconds"
            })
        
        return {
            "imbalance": round(imbalance, 4),
            "buy_vol_60s": round(buy_vol_60s, 4),
            "sell_vol_60s": round(sell_vol_60s, 4),
            "signals": signals[:5]
        }
        
    except Exception as e:
        print(f"Order book analysis error: {e}")
        return None