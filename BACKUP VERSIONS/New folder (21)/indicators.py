# indicators.py
import pandas as pd
import numpy as np
import pandas_ta as ta
from typing import Dict, Tuple, List, Optional
from dataclasses import dataclass

# ---------- Configuration ----------

INDICATOR_CONFIG = {
    'rsi_period': 14,
    'macd_fast': 12,
    'macd_slow': 26,
    'macd_signal': 9,
    'ema_periods': [20, 50, 100, 200],
    'bollinger_period': 20,
    'bollinger_std': 2,
    'atr_period': 14,
    'adx_period': 14,
    'volume_ma_periods': [20, 50],
    'volume_profile_period': 50,
    'vwap_period': 20,
    'obv_ma_period': 20,
    'supertrend_period': 10,
    'supertrend_multiplier': 3,
    'ichimoku_conversion': 9,
    'ichimoku_base': 26,
    'ichimoku_lagging': 52,
    'ichimoku_displacement': 26,
    'stochastic_period': 14,
    'williams_period': 14,
    'mfi_period': 14,
    'cci_period': 20,
    'roc_period': 12,
    'donchian_period': 20,
    'parabolic_sar_start': 0.02,
    'parabolic_sar_increment': 0.02,
    'parabolic_sar_max': 0.2
}

# ---------- Data Structures ----------

@dataclass
class Signal:
    bias: str  # 'bullish', 'bearish', 'neutral'
    strength: str  # 'strong', 'moderate', 'weak'
    label: str
    reasons: List[str]
    score: float  # 0-100
    confidence: float  # 0-1
    indicators: Dict
    divergence_signals: List[str]
    volume_signals: List[str]
    trend_alignment: str  # 'bullish', 'bearish', 'mixed', 'neutral'
    momentum_score: float  # -1 to 1
    volatility_state: str  # 'high', 'normal', 'low'
    support_resistance: Dict

# ---------- Enhanced Indicator Computation ----------

def add_all_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """
    Add comprehensive technical indicators to dataframe.
    Expects columns: Time (UTC), Open, High, Low, Close, Volume
    """
    if df.empty or len(df) < 100:  # Need sufficient data
        return df

    out = df.copy()
    close = out["Close"]
    high = out["High"]
    low = out["Low"]
    open_ = out["Open"]
    volume = out["Volume"]
    
    # Typical price and money flow
    typical_price = (high + low + close) / 3
    money_flow = typical_price * volume
    
    # 1. MOMENTUM INDICATORS
    
    # RSI and Stochastic RSI
    out["RSI"] = ta.rsi(close, length=INDICATOR_CONFIG['rsi_period'])
    out["RSI_SMA"] = ta.sma(out["RSI"], length=9)
    
    # Stochastic
    stochastic = ta.stoch(high, low, close, 
                         k=INDICATOR_CONFIG['stochastic_period'], 
                         d=3, smooth_k=3)
    if stochastic is not None:
        out["STOCH_K"] = stochastic.iloc[:, 0]
        out["STOCH_D"] = stochastic.iloc[:, 1]
    
    # Stochastic RSI
    stochrsi = ta.stochrsi(close, length=14, rsi_length=14, k=3, d=3)
    if stochrsi is not None:
        out["STOCHRSI_K"] = stochrsi.iloc[:, 0]
        out["STOCHRSI_D"] = stochrsi.iloc[:, 1]
    
    # MACD with histogram
    macd = ta.macd(close, 
                   fast=INDICATOR_CONFIG['macd_fast'],
                   slow=INDICATOR_CONFIG['macd_slow'],
                   signal=INDICATOR_CONFIG['macd_signal'])
    if macd is not None:
        out["MACD"] = macd.iloc[:, 0]
        out["MACD_SIGNAL"] = macd.iloc[:, 1]
        out["MACD_HIST"] = macd.iloc[:, 2]
        out["MACD_HIST_SMA"] = ta.sma(out["MACD_HIST"], length=9)
    
    # Williams %R
    out["WILLIAMS_R"] = ta.willr(high, low, close, length=INDICATOR_CONFIG['williams_period'])
    
    # Rate of Change
    out["ROC"] = ta.roc(close, length=INDICATOR_CONFIG['roc_period'])
    
    # Ultimate Oscillator
    out["UO"] = ta.uo(high, low, close)
    
    # 2. TREND INDICATORS
    
    # EMAs
    for period in INDICATOR_CONFIG['ema_periods']:
        out[f"EMA{period}"] = ta.ema(close, length=period)
    
    # SMA
    out["SMA20"] = ta.sma(close, length=20)
    out["SMA50"] = ta.sma(close, length=50)
    
    # Ichimoku Cloud (simplified)
    try:
        ichimoku = ta.ichimoku(high, low, close, 
                               tenkan=INDICATOR_CONFIG['ichimoku_conversion'],
                               kijun=INDICATOR_CONFIG['ichimoku_base'],
                               senkou=INDICATOR_CONFIG['ichimoku_displacement'])
        if ichimoku is not None:
            out["ICHIMOKU_CONVERSION"] = ichimoku[0]
            out["ICHIMOKU_BASE"] = ichimoku[1]
            out["ICHIMOKU_SPAN_A"] = ichimoku[2]
            out["ICHIMOKU_SPAN_B"] = ichimoku[3]
    except:
        pass
    
    # Parabolic SAR
    out["PSAR"] = ta.psar(high, low, 
                          af0=INDICATOR_CONFIG['parabolic_sar_start'],
                          af=INDICATOR_CONFIG['parabolic_sar_increment'],
                          max_af=INDICATOR_CONFIG['parabolic_sar_max'])
    
    # SuperTrend
    supertrend = ta.supertrend(high, low, close, 
                               length=INDICATOR_CONFIG['supertrend_period'],
                               multiplier=INDICATOR_CONFIG['supertrend_multiplier'])
    if supertrend is not None:
        out["SUPERTREND"] = supertrend.iloc[:, 0]
        out["SUPERTREND_DIR"] = supertrend.iloc[:, 1]
    
    # ADX and Directional Indicators
    adx_full = ta.adx(high, low, close, length=INDICATOR_CONFIG['adx_period'])
    if adx_full is not None:
        out["ADX"] = adx_full.iloc[:, 0]
        out["DMP"] = adx_full.iloc[:, 1]  # +DI
        out["DMN"] = adx_full.iloc[:, 2]  # -DI
    
    # 3. VOLATILITY INDICATORS
    
    # Bollinger Bands
    bb = ta.bbands(close, 
                   length=INDICATOR_CONFIG['bollinger_period'],
                   std=INDICATOR_CONFIG['bollinger_std'])
    if bb is not None:
        out["BB_LOWER"] = bb.iloc[:, 0]
        out["BB_MID"] = bb.iloc[:, 1]
        out["BB_UPPER"] = bb.iloc[:, 2]
        out["BB_WIDTH"] = (out["BB_UPPER"] - out["BB_LOWER"]) / out["BB_MID"]
        out["BB_PERCENT"] = (close - out["BB_LOWER"]) / (out["BB_UPPER"] - out["BB_LOWER"])
    
    # Average True Range
    out["ATR"] = ta.atr(high, low, close, length=INDICATOR_CONFIG['atr_period'])
    out["ATR_PERCENT"] = out["ATR"] / close * 100
    
    # Keltner Channels
    kc = ta.kc(high, low, close, length=20, scalar=2)
    if kc is not None:
        out["KC_UPPER"] = kc.iloc[:, 0]
        out["KC_LOWER"] = kc.iloc[:, 1]
    
    # Donchian Channels
    donchian = ta.donchian(high, low, length=INDICATOR_CONFIG['donchian_period'])
    if donchian is not None:
        out["DONCHIAN_UPPER"] = donchian.iloc[:, 0]
        out["DONCHIAN_LOWER"] = donchian.iloc[:, 1]
    
    # 4. VOLUME INDICATORS (COMPREHENSIVE)
    
    # On-Balance Volume with MA
    out["OBV"] = ta.obv(close, volume)
    out["OBV_MA"] = ta.sma(out["OBV"], length=INDICATOR_CONFIG['obv_ma_period'])
    
    # Volume Moving Averages
    for period in INDICATOR_CONFIG['volume_ma_periods']:
        out[f"VOLUME_MA{period}"] = ta.sma(volume, length=period)
    
    # Volume Price Trend
    out["VPT"] = volume * ((close - close.shift(1)) / close.shift(1)).cumsum()
    
    # Chaikin Money Flow
    out["CMF"] = ta.cmf(high, low, close, volume, length=20)
    
    # Money Flow Index
    out["MFI"] = ta.mfi(high, low, close, volume, length=INDICATOR_CONFIG['mfi_period'])
    
    # Volume Weighted Average Price
    out["VWAP"] = (money_flow.cumsum() / volume.cumsum())
    
    # Volume Oscillator
    out["VOLUME_OSCILLATOR"] = (out["VOLUME_MA20"] - out["VOLUME_MA50"]) / out["VOLUME_MA50"] * 100
    
    # Volume Profile (simplified)
    out["VOLUME_PROFILE_HIGH"] = ta.sma(high * volume, length=INDICATOR_CONFIG['volume_profile_period']) / ta.sma(volume, length=INDICATOR_CONFIG['volume_profile_period'])
    out["VOLUME_PROFILE_LOW"] = ta.sma(low * volume, length=INDICATOR_CONFIG['volume_profile_period']) / ta.sma(volume, length=INDICATOR_CONFIG['volume_profile_period'])
    
    # Accumulation/Distribution Line
    out["ADL"] = ta.ad(high, low, close, volume)
    
    # Ease of Movement
    out["EOM"] = ta.eom(high, low, volume, length=14)
    
    # Volume Ratio
    out["VOLUME_RATIO"] = volume / out["VOLUME_MA20"]
    
    # 5. OSCILLATORS
    
    # Commodity Channel Index
    out["CCI"] = ta.cci(high, low, close, length=INDICATOR_CONFIG['cci_period'])
    
    # Detrended Price Oscillator
    out["DPO"] = ta.dpo(close, length=20)
    
    # 6. SUPPORT/RESISTANCE & PATTERNS
    
    # Pivot Points (simplified daily)
    out["PIVOT"] = (high + low + close) / 3
    out["RESISTANCE1"] = 2 * out["PIVOT"] - low
    out["SUPPORT1"] = 2 * out["PIVOT"] - high
    
    # Candle patterns
    try:
        cdl_patterns = ta.cdl_pattern(open_, high, low, close, 
                                      name=["engulfing", "doji", "hammer", 
                                            "shootingstar", "morningstar",
                                            "eveningstar", "harami"])
        if cdl_patterns is not None:
            for col in cdl_patterns.columns:
                out[col] = cdl_patterns[col]
    except Exception:
        pass
    
    # 7. PRICE ACTION
    
    # Price position relative to indicators
    out["PRICE_VS_EMA20"] = (close - out["EMA20"]) / out["EMA20"] * 100
    out["PRICE_VS_EMA50"] = (close - out["EMA50"]) / out["EMA50"] * 100
    
    # Trend strength composite
    out["TREND_STRENGTH"] = (
        (out["ADX"].fillna(0) / 100) * 0.4 +
        (abs(out["MACD_HIST"] / close.max())).clip(0, 1) * 0.3 +
        (abs(out["RSI"] - 50) / 50) * 0.3
    )
    
    # Volume-Weighted Momentum
    out["VW_MOMENTUM"] = out["ROC"] * out["VOLUME_RATIO"]
    
    # Clean NaN values
    out = out.replace([np.inf, -np.inf], np.nan)
    
    return out

# ---------- Enhanced Divergence Detection ----------

def detect_multiple_divergences(df: pd.DataFrame, lookback: int = 30) -> Dict[str, List[str]]:
    """
    Detect divergences between price and multiple indicators.
    Returns dict with divergence types and descriptions.
    """
    if len(df) < lookback + 10:
        return {}
    
    divergences = {
        'bullish': [],
        'bearish': [],
        'hidden_bullish': [],
        'hidden_bearish': []
    }
    
    price = df["Close"].tail(lookback).values
    highs = df["High"].tail(lookback).values
    lows = df["Low"].tail(lookback).values
    
    # Indicators to check for divergence
    indicators_to_check = [
        ('RSI', df["RSI"].tail(lookback).values),
        ('MACD', df["MACD"].tail(lookback).values),
        ('STOCH_K', df.get("STOCH_K", pd.Series([0]*lookback)).tail(lookback).values),
        ('OBV', df["OBV"].tail(lookback).values),
        ('MFI', df.get("MFI", pd.Series([50]*lookback)).tail(lookback).values),
        ('CCI', df.get("CCI", pd.Series([0]*lookback)).tail(lookback).values)
    ]
    
    for ind_name, indicator in indicators_to_check:
        if len(indicator) < 5 or np.all(np.isnan(indicator)):
            continue
        
        # Regular divergences
        # Price makes lower low, indicator makes higher low = Bullish
        if (price[-1] < price[-5] and indicator[-1] > indicator[-5] and
            price[-2] < price[-6] and indicator[-2] > indicator[-6]):
            divergences['bullish'].append(f"Bullish {ind_name} divergence")
        
        # Price makes higher high, indicator makes lower high = Bearish
        if (price[-1] > price[-5] and indicator[-1] < indicator[-5] and
            price[-2] > price[-6] and indicator[-2] < indicator[-6]):
            divergences['bearish'].append(f"Bearish {ind_name} divergence")
        
        # Hidden divergences (continuation patterns)
        # Price makes higher low, indicator makes lower low = Hidden Bullish
        if (price[-1] > price[-5] and indicator[-1] < indicator[-5]):
            divergences['hidden_bullish'].append(f"Hidden bullish {ind_name} divergence")
        
        # Price makes lower high, indicator makes higher high = Hidden Bearish
        if (price[-1] < price[-5] and indicator[-1] > indicator[-5]):
            divergences['hidden_bearish'].append(f"Hidden bearish {ind_name} divergence")
    
    return divergences

# ---------- Volume Analysis ----------

def analyze_volume_signals(df: pd.DataFrame) -> Dict[str, List[str]]:
    """
    Analyze volume patterns and generate signals.
    """
    if len(df) < 50:
        return {'signals': [], 'volume_state': 'normal'}
    
    last = df.iloc[-1]
    prev = df.iloc[-2] if len(df) > 1 else last
    
    signals = []
    volume_state = 'normal'
    
    # Volume spike detection
    volume_ma20 = last.get("VOLUME_MA20", volume_ma20 if 'volume_ma20' in locals() else 0)
    current_volume = last["Volume"]
    
    if volume_ma20 > 0:
        volume_ratio = current_volume / volume_ma20
        if volume_ratio > 2.5:
            signals.append(f"Volume spike ({volume_ratio:.1f}x MA20)")
            volume_state = 'high'
        elif volume_ratio < 0.5:
            signals.append(f"Low volume ({volume_ratio:.1f}x MA20)")
            volume_state = 'low'
    
    # OBV trend analysis
    obv = last.get("OBV", 0)
    obv_ma = last.get("OBV_MA", 0)
    obv_prev = prev.get("OBV", 0)
    
    if obv > obv_ma and obv > obv_prev:
        signals.append("OBV trending up (bullish)")
    elif obv < obv_ma and obv < obv_prev:
        signals.append("OBV trending down (bearish)")
    
    # MFI analysis
    mfi = last.get("MFI", 50)
    if mfi < 20:
        signals.append(f"MFI oversold ({mfi:.1f})")
    elif mfi > 80:
        signals.append(f"MFI overbought ({mfi:.1f})")
    
    # CMF analysis
    cmf = last.get("CMF", 0)
    if cmf > 0.05:
        signals.append(f"Strong buying pressure (CMF: {cmf:.3f})")
    elif cmf < -0.05:
        signals.append(f"Strong selling pressure (CMF: {cmf:.3f})")
    
    # Volume-Price confirmation
    price_change = ((last["Close"] - prev["Close"]) / prev["Close"] * 100) if prev["Close"] > 0 else 0
    if abs(price_change) > 1 and volume_ratio > 1.5:
        direction = "up" if price_change > 0 else "down"
        signals.append(f"Volume confirms {direction} move ({price_change:+.1f}%)")
    
    return {'signals': signals, 'volume_state': volume_state}

# ---------- Trend Analysis ----------

def analyze_trend_alignment(df: pd.DataFrame) -> Tuple[str, float]:
    """
    Determine trend alignment across multiple timeframes.
    Returns (trend_alignment, confidence_score)
    """
    if len(df) < 50:
        return 'neutral', 0.5
    
    last = df.iloc[-1]
    close = last["Close"]
    
    # Check EMA alignment
    ema_scores = []
    ema_periods = [20, 50, 100, 200]
    
    for i, period in enumerate(ema_periods):
        ema_key = f"EMA{period}"
        if ema_key in last:
            if close > last[ema_key]:
                ema_scores.append(1.0)  # Bullish
            else:
                ema_scores.append(-1.0)  # Bearish
    
    # Check MACD
    macd_score = 0
    if "MACD" in last and "MACD_SIGNAL" in last:
        macd = last["MACD"]
        macd_signal = last["MACD_SIGNAL"]
        if not pd.isna(macd) and not pd.isna(macd_signal):
            macd_score = 1.0 if macd > macd_signal else -1.0
    
    # Check ADX trend
    adx_score = 0
    if "ADX" in last and "DMP" in last and "DMN" in last:
        adx = last["ADX"]
        dmp = last["DMP"]
        dmn = last["DMN"]
        if adx > 25:  #Strong trend
            adx_score = 1.0 if dmp > dmn else -1.0
    
    # Composite score
    weights = [0.3, 0.25, 0.25, 0.2]  # EMA20, EMA50, MACD, ADX
    scores = [ema_scores[0] if len(ema_scores) > 0 else 0,
              ema_scores[1] if len(ema_scores) > 1 else 0,
              macd_score,
              adx_score]
    
    composite = sum(s * w for s, w in zip(scores, weights))
    
    # Determine alignment
    if composite > 0.3:
        alignment = 'bullish'
    elif composite < -0.3:
        alignment = 'bearish'
    elif abs(composite) <= 0.1:
        alignment = 'neutral'
    else:
        alignment = 'mixed'
    
    confidence = min(abs(composite), 1.0)
    
    return alignment, confidence

# ---------- Enhanced Signal Generation ----------

def generate_signal_summary(df: pd.DataFrame) -> Signal:
    """
    Generate comprehensive trading signal based on all indicators.
    """
    if len(df) < 50:
        return Signal(
            bias='neutral',
            strength='weak',
            label='INSUFFICIENT_DATA',
            reasons=['Insufficient data for analysis'],
            score=50,
            confidence=0.0,
            indicators={},
            divergence_signals=[],
            volume_signals=[],
            trend_alignment='neutral',
            momentum_score=0,
            volatility_state='normal',
            support_resistance={}
        )
    
    last = df.iloc[-1]
    prev = df.iloc[-2] if len(df) > 1 else last
    
    def safe_get(key, default=0):
        val = last.get(key)
        return default if pd.isna(val) else float(val)
    
    # 1. Collect indicator values
    indicators = {
        'rsi': safe_get('RSI', 50),
        'macd': safe_get('MACD', 0),
        'macd_signal': safe_get('MACD_SIGNAL', 0),
        'macd_hist': safe_get('MACD_HIST', 0),
        'ema20': safe_get('EMA20', last['Close']),
        'ema50': safe_get('EMA50', last['Close']),
        'ema100': safe_get('EMA100', last['Close']),
        'ema200': safe_get('EMA200', last['Close']),
        'bb_upper': safe_get('BB_UPPER', last['Close'] * 1.1),
        'bb_lower': safe_get('BB_LOWER', last['Close'] * 0.9),
        'adx': safe_get('ADX', 0),
        'cci': safe_get('CCI', 0),
        'atr_percent': safe_get('ATR_PERCENT', 0),
        'mfi': safe_get('MFI', 50),
        'obv': safe_get('OBV', 0),
        'volume_ratio': safe_get('VOLUME_RATIO', 1),
        'williams_r': safe_get('WILLIAMS_R', -50),
        'supertrend_dir': safe_get('SUPERTREND_DIR', 1)
    }
    
    close = float(last['Close'])
    high = float(last['High'])
    low = float(last['Low'])
    
    # 2. Analyze components
    divergences = detect_multiple_divergences(df)
    volume_analysis = analyze_volume_signals(df)
    trend_alignment, trend_confidence = analyze_trend_alignment(df)
    
    # 3. Calculate composite score
    score_components = []
    reasons = []
    
    # RSI Scoring
    rsi = indicators['rsi']
    if rsi < 30:
        score = 15
        reasons.append(f"RSI oversold ({rsi:.1f})")
    elif rsi < 40:
        score = 8
        reasons.append(f"RSI near oversold ({rsi:.1f})")
    elif rsi > 70:
        score = -15
        reasons.append(f"RSI overbought ({rsi:.1f})")
    elif rsi > 60:
        score = -8
        reasons.append(f"RSI near overbought ({rsi:.1f})")
    else:
        score = 0
    score_components.append(score)
    
    # MACD Scoring
    macd_hist = indicators['macd_hist']
    if macd_hist > 0:
        score = 12 if macd_hist > prev.get('MACD_HIST', 0) else 8
        reasons.append("MACD histogram positive")
    elif macd_hist < 0:
        score = -12 if macd_hist < prev.get('MACD_HIST', 0) else -8
        reasons.append("MACD histogram negative")
    else:
        score = 0
    score_components.append(score)
    
    # Trend Alignment Scoring
    if trend_alignment == 'bullish':
        score = 15
        reasons.append("Multiple timeframes aligned bullish")
    elif trend_alignment == 'bearish':
        score = -15
        reasons.append("Multiple timeframes aligned bearish")
    else:
        score = 0
    score_components.append(score)
    
    # Volume Scoring
    volume_ratio = indicators['volume_ratio']
    if volume_ratio > 1.5 and close > prev['Close']:
        score = 10
        reasons.append(f"High volume on up move ({volume_ratio:.1f}x avg)")
    elif volume_ratio > 1.5 and close < prev['Close']:
        score = -10
        reasons.append(f"High volume on down move ({volume_ratio:.1f}x avg)")
    elif volume_ratio < 0.5:
        score = -5
        reasons.append(f"Low volume ({volume_ratio:.1f}x avg)")
    else:
        score = 0
    score_components.append(score)
    
    # Price Position Scoring
    bb_percent = (close - indicators['bb_lower']) / (indicators['bb_upper'] - indicators['bb_lower']) * 100
    if bb_percent < 20:
        score = 12
        reasons.append(f"Price near lower BB ({bb_percent:.1f}%)")
    elif bb_percent > 80:
        score = -12
        reasons.append(f"Price near upper BB ({bb_percent:.1f}%)")
    else:
        score = 0
    score_components.append(score)
    
    # CCI Scoring
    cci = indicators['cci']
    if cci < -100:
        score = 8
        reasons.append(f"CCI oversold ({cci:.1f})")
    elif cci > 100:
        score = -8
        reasons.append(f"CCI overbought ({cci:.1f})")
    else:
        score = 0
    score_components.append(score)
    
    # MFI Scoring
    mfi = indicators['mfi']
    if mfi < 20:
        score = 8
        reasons.append(f"MFI oversold ({mfi:.1f})")
    elif mfi > 80:
        score = -8
        reasons.append(f"MFI overbought ({mfi:.1f})")
    else:
        score = 0
    score_components.append(score)
    
    # Divergence Scoring
    div_score = 0
    div_reasons = []
    for div_type, div_list in divergences.items():
        if div_type == 'bullish' and div_list:
            div_score += len(div_list) * 6
            div_reasons.extend(div_list[:2])
        elif div_type == 'bearish' and div_list:
            div_score -= len(div_list) * 6
            div_reasons.extend(div_list[:2])
    score_components.append(div_score)
    reasons.extend(div_reasons)
    
    # Calculate total score
    total_score = 50 + sum(score_components)
    total_score = max(0, min(100, total_score))
    
    # 4. Determine bias and strength
    if total_score >= 75:
        bias = "bullish"
        strength = "strong"
        label = "STRONG_BULLISH"
    elif total_score >= 60:
        bias = "bullish"
        strength = "moderate"
        label = "BULLISH"
    elif total_score <= 25:
        bias = "bearish"
        strength = "strong"
        label = "STRONG_BEARISH"
    elif total_score <= 40:
        bias = "bearish"
        strength = "moderate"
        label = "BEARISH"
    else:
        bias = "neutral"
        strength = "weak"
        label = "NEUTRAL"
    
    # 5. Momentum score (-1 to 1)
    momentum_score = (total_score - 50) / 50
    
    # 6. Support/Resistance levels
    support_resistance = {
        'support1': float(safe_get('SUPPORT1', close * 0.98)),
        'resistance1': float(safe_get('RESISTANCE1', close * 1.02)),
        'pivot': float(safe_get('PIVOT', close)),
        'ema20': float(indicators['ema20']),
        'ema50': float(indicators['ema50'])
    }
    
    # 7. Volatility state
    atr_percent = indicators['atr_percent']
    if atr_percent > 3:
        volatility_state = 'high'
        reasons.append(f"High volatility (ATR: {atr_percent:.1f}%)")
    elif atr_percent < 1:
        volatility_state = 'low'
        reasons.append(f"Low volatility (ATR: {atr_percent:.1f}%)")
    else:
        volatility_state = 'normal'
    
    # 8. Confidence calculation
    confidence_factors = [
        trend_confidence * 0.3,
        (min(len(df) / 200, 1.0)) * 0.2,  # Data length
        (1.0 if volume_analysis['volume_state'] != 'normal' else 0.5) * 0.2,
        (abs(momentum_score)) * 0.3
    ]
    confidence = min(sum(confidence_factors), 1.0)
    
    # 9. Add volume signals to reasons
    reasons.extend(volume_analysis['signals'])
    
    return Signal(
        bias=bias,
        strength=strength,
        label=label,
        reasons=reasons[:10],  # Limit reasons
        score=total_score,
        confidence=confidence,
        indicators=indicators,
        divergence_signals=[d for div_list in divergences.values() for d in div_list],
        volume_signals=volume_analysis['signals'],
        trend_alignment=trend_alignment,
        momentum_score=momentum_score,
        volatility_state=volatility_state,
        support_resistance=support_resistance
    )

# ---------- Quick Analysis ----------

def quick_analysis(df: pd.DataFrame) -> Dict:
    """
    Quick analysis for display purposes.
    """
    if len(df) < 20:
        return {"error": "Insufficient data"}
    
    signal = generate_signal_summary(df)
    last = df.iloc[-1]
    
    return {
        "signal": signal.label,
        "score": round(signal.score, 1),
        "confidence": round(signal.confidence * 100, 1),
        "bias": signal.bias,
        "strength": signal.strength,
        "price": round(float(last["Close"]), 4),
        "volume_status": signal.volume_signals[0] if signal.volume_signals else "Normal",
        "trend": signal.trend_alignment,
        "key_levels": {
            "support": round(signal.support_resistance.get('support1', 0), 4),
            "resistance": round(signal.support_resistance.get('resistance1', 0), 4),
            "ema20": round(signal.support_resistance.get('ema20', 0), 4)
        },
        "top_reasons": signal.reasons[:3]
    }

# ---------- Risk Assessment ----------

def assess_risk(df: pd.DataFrame) -> Dict:
    """
    Assess trading risk based on indicators.
    """
    if len(df) < 50:
        return {"risk_level": "UNKNOWN", "factors": []}
    
    last = df.iloc[-1]
    
    risk_factors = []
    risk_score = 0
    
    # Volatility risk
    atr_percent = last.get("ATR_PERCENT", 0)
    if atr_percent > 4:
        risk_score += 30
        risk_factors.append(f"High volatility (ATR: {atr_percent:.1f}%)")
    elif atr_percent > 2:
        risk_score += 15
    
    # Volume risk
    volume_ratio = last.get("VOLUME_RATIO", 1)
    if volume_ratio < 0.3:
        risk_score += 20
        risk_factors.append(f"Very low volume ({volume_ratio:.1f}x avg)")
    
    # Trend risk
    adx = last.get("ADX", 0)
    if adx < 15:
        risk_score += 20
        risk_factors.append(f"Weak trend (ADX: {adx:.1f})")
    
    # Overbought/Oversold risk
    rsi = last.get("RSI", 50)
    if rsi > 80 or rsi < 20:
        risk_score += 25
        risk_factors.append(f"Extreme RSI ({rsi:.1f})")
    
    # Determine risk level
    if risk_score >= 60:
        risk_level = "HIGH"
    elif risk_score >= 40:
        risk_level = "MEDIUM"
    elif risk_score >= 20:
        risk_level = "LOW"
    else:
        risk_level = "VERY_LOW"
    
    return {
        "risk_level": risk_level,
        "risk_score": risk_score,
        "factors": risk_factors,
        "recommended_position_size": max(0.1, min(1.0, (100 - risk_score) / 100))
    }