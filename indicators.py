# indicators.py
import pandas as pd
import pandas_ta as ta

# ---------- Indicator computation ----------

def add_all_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """
    Add a set of indicators to dataframe.
    Expects columns: Time (UTC), Open, High, Low, Close, Volume
    """
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

    # Candle patterns (a few common ones)
    try:
        cdl = ta.cdl_pattern(out["Open"], high, low, close,
                             name=["engulfing", "doji", "hammer", "shootingstar"])
        if cdl is not None and not cdl.empty:
            for col in cdl.columns:
                out[col] = cdl[col]
    except Exception:
        pass

    return out


# ---------- Simple divergence check ----------

def detect_divergence(price: pd.Series, indicator: pd.Series, lookback: int = 20):
    """
    Very simple divergence detector on the last `lookback` bars.
    Returns one of: 'bullish', 'bearish', None
    """
    if price is None or indicator is None:
        return None
    if len(price) < lookback + 2 or len(indicator) < lookback + 2:
        return None

    p = price.tail(lookback + 2)
    ind = indicator.tail(lookback + 2)

    # Higher high in price, lower high in indicator => bearish
    p_prev_high = p.iloc[-2]
    p_curr_high = p.iloc[-1]
    ind_prev = ind.iloc[-2]
    ind_curr = ind.iloc[-1]

    if p_curr_high > p_prev_high and ind_curr < ind_prev:
        return "bearish"

    # Lower low in price, higher low in indicator => bullish
    p_prev_low = p.iloc[-2]
    p_curr_low = p.iloc[-1]

    if p_curr_low < p_prev_low and ind_curr > ind_prev:
        return "bullish"

    return None


# ---------- Signal generation ----------

def generate_signal_summary(df: pd.DataFrame):
    """
    Takes DF with indicators and returns:
    - bias: 'bullish' / 'bearish' / 'neutral'
    - strength: 'strong', 'normal', 'weak'
    - label: text like 'STRONG_BULLISH', 'WATCH_LONG', etc.
    - reasons: list of strings
    - score: 0..100
    """
    last = df.iloc[-1]
    close = float(last["Close"])

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

    reasons = []
    score = 50  # neutral base

    # --- RSI ---
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

    # --- MACD ---
    if macd is not None and macd_sig is not None:
        if macd > macd_sig and macd_hist is not None and macd_hist > 0:
            reasons.append("MACD bullish (above signal & positive hist)")
            score += 8
        elif macd < macd_sig and macd_hist is not None and macd_hist < 0:
            reasons.append("MACD bearish (below signal & negative hist)")
            score -= 8

    # --- EMAs trend context ---
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

    # --- Bollinger Bands extremes ---
    if bb_up is not None and bb_low is not None:
        if close <= bb_low:
            reasons.append("Price at / below lower Bollinger band (mean reversion up)")
            score += 6
        elif close >= bb_up:
            reasons.append("Price at / above upper Bollinger band (mean reversion down)")
            score -= 6

    # --- ADX trend strength ---
    if adx is not None:
        if adx > 25:
            reasons.append(f"ADX {adx:.1f} strong trend")
            # amplify direction that EMAs/MACD chose
            if macd is not None and macd_sig is not None:
                if macd > macd_sig:
                    score += 4
                elif macd < macd_sig:
                    score -= 4

    # --- CCI extremes ---
    if cci is not None:
        if cci < -100:
            reasons.append(f"CCI {cci:.1f} oversold")
            score += 4
        elif cci > 100:
            reasons.append(f"CCI {cci:.1f} overbought")
            score -= 4

    # --- StochRSI ---
    if stoch_k is not None:
        if stoch_k < 20:
            reasons.append(f"StochRSI K {stoch_k:.1f} oversold")
            score += 3
        elif stoch_k > 80:
            reasons.append(f"StochRSI K {stoch_k:.1f} overbought")
            score -= 3

    # --- Volume / ATR sanity (we just report ATR) ---
    if atr is not None:
        reasons.append(f"ATR: {atr:.5f} (volatility unit)")

    # --- Simple divergence on RSI ---
    if "RSI" in df.columns:
        div = detect_divergence(df["Close"], df["RSI"], lookback=10)
        if div == "bullish":
            reasons.append("Bullish RSI divergence")
            score += 8
        elif div == "bearish":
            reasons.append("Bearish RSI divergence")
            score -= 8

    # Clamp score
    score = max(0, min(100, score))

    # Map to label
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

    # Add watch flags for extreme RSI
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
        "close": close
    }
