# ============================================================
# ADDON: indicators_addon.py
# Add these imports and routes to your appp.py
# ============================================================
# 
# REQUIRED IMPORTS (add to top of appp.py if not present):
# from scipy.signal import find_peaks   (pip install scipy)
# import numpy as np  (already there)
#
# ============================================================

# ============================================================
# 1. VOLUME PROFILE
# ============================================================

@app.route("/volume_profile", methods=["POST"])
def volume_profile():
    """
    Calculate Volume Profile (TPO/Market Profile) for a symbol.
    Returns price levels with volume concentration (POC, VAH, VAL, HVN, LVN).
    """
    payload = request.get_json() or {}
    symbol  = payload.get("symbol", "BTC/USDT").upper()
    timeframe = payload.get("timeframe", "1h")
    limit   = int(payload.get("limit", 200))      # candles to analyse
    num_bins = int(payload.get("num_bins", 50))   # price buckets
    value_area_pct = float(payload.get("value_area_pct", 0.70))  # 70 % VA

    try:
        conn = get_conn()
        cur  = conn.cursor(dictionary=True)
        cur.execute("""
            SELECT time_utc, open, high, low, close, volume
            FROM ohlcv_data
            WHERE symbol=%s AND timeframe=%s
            ORDER BY time_utc DESC LIMIT %s
        """, (symbol, timeframe, limit))
        rows = cur.fetchall()
        cur.close(); conn.close()

        if len(rows) < 10:
            return jsonify({"success": False, "error": "Not enough data"}), 400

        df = pd.DataFrame(rows)
        for c in ["open","high","low","close","volume"]:
            df[c] = df[c].astype(float)
        df = df.sort_values("time_utc").reset_index(drop=True)

        price_min = df["low"].min()
        price_max = df["high"].max()
        price_range = price_max - price_min
        if price_range == 0:
            return jsonify({"success": False, "error": "Zero price range"}), 400

        bin_size  = price_range / num_bins
        bins      = np.linspace(price_min, price_max, num_bins + 1)
        bin_vol   = np.zeros(num_bins)

        for _, row in df.iterrows():
            # Distribute candle volume across touched bins (equal weight)
            lo, hi, vol = row["low"], row["high"], row["volume"]
            touched = []
            for i in range(num_bins):
                if bins[i] <= hi and bins[i+1] >= lo:
                    touched.append(i)
            if touched:
                share = vol / len(touched)
                for i in touched:
                    bin_vol[i] += share

        # POC – price of control (highest volume bin)
        poc_idx   = int(np.argmax(bin_vol))
        poc_price = float((bins[poc_idx] + bins[poc_idx+1]) / 2)

        # Value Area (70 % of total volume around POC)
        total_vol = bin_vol.sum()
        target_va = total_vol * value_area_pct
        va_vol    = bin_vol[poc_idx]
        lo_idx    = poc_idx
        hi_idx    = poc_idx

        while va_vol < target_va:
            up_gain = bin_vol[hi_idx+1] if hi_idx+1 < num_bins else 0
            dn_gain = bin_vol[lo_idx-1] if lo_idx-1 >= 0       else 0
            if up_gain >= dn_gain:
                hi_idx  = min(hi_idx+1, num_bins-1)
                va_vol += up_gain
            else:
                lo_idx  = max(lo_idx-1, 0)
                va_vol += dn_gain
            if hi_idx == num_bins-1 and lo_idx == 0:
                break

        vah = float((bins[hi_idx] + bins[hi_idx+1]) / 2)
        val = float((bins[lo_idx] + bins[lo_idx+1]) / 2)

        # HVN – High Volume Nodes (bins > 70th percentile)
        p70 = float(np.percentile(bin_vol[bin_vol > 0], 70))
        p30 = float(np.percentile(bin_vol[bin_vol > 0], 30))

        hvn = []
        lvn = []
        profile = []
        for i in range(num_bins):
            mid = float((bins[i] + bins[i+1]) / 2)
            v   = float(bin_vol[i])
            profile.append({"price": round(mid, 6), "volume": round(v, 4)})
            if v >= p70:
                hvn.append({"price": round(mid, 6), "volume": round(v, 4)})
            if v <= p30 and v > 0:
                lvn.append({"price": round(mid, 6), "volume": round(v, 4)})

        current_price = float(df["close"].iloc[-1])

        # Signal hint
        if current_price > vah:
            vp_signal = "BREAKOUT_ABOVE_VA"
        elif current_price < val:
            vp_signal = "BREAKDOWN_BELOW_VA"
        elif poc_price * 0.999 <= current_price <= poc_price * 1.001:
            vp_signal = "AT_POC"
        elif current_price > poc_price:
            vp_signal = "ABOVE_POC"
        else:
            vp_signal = "BELOW_POC"

        return jsonify({
            "success":       True,
            "symbol":        symbol,
            "timeframe":     timeframe,
            "candles_used":  len(df),
            "num_bins":      num_bins,
            "current_price": current_price,
            "poc":           round(poc_price, 6),
            "vah":           round(vah, 6),
            "val":           round(val, 6),
            "value_area_pct": value_area_pct,
            "hvn":           hvn[:10],
            "lvn":           lvn[:10],
            "profile":       profile,
            "vp_signal":     vp_signal,
            "timestamp":     datetime.utcnow().isoformat()
        })

    except Exception as e:
        import traceback; traceback.print_exc()
        return jsonify({"success": False, "error": str(e)}), 500


# ============================================================
# 2. ORDER BOOK FLOW (delta, cumulative delta, imbalance heatmap)
# ============================================================

@app.route("/order_book_flow", methods=["POST"])
def order_book_flow():
    """
    Analyses live order book + recent trades to compute:
    - Bid/Ask walls
    - Cumulative delta (buy vol - sell vol)
    - Absorption zones
    - Flow imbalance per price level
    """
    payload = request.get_json() or {}
    symbol  = payload.get("symbol", real_time_data["current_symbol"])
    selected_exchanges = payload.get(
        "exchanges",
        ["binance","bybit","okx","gateio","huobi","kraken","bitget","mexc","coinbase"]
    )
    time_window = int(payload.get("time_window", 60))   # seconds
    depth_levels = int(payload.get("depth_levels", 20))
    wall_multiplier = float(payload.get("wall_multiplier", 3.0))  # x avg volume to call a wall

    try:
        now = time.time()

        # ── Combine order books ────────────────────────────────
        bid_map = {}   # price -> total qty
        ask_map = {}

        for ex in selected_exchanges:
            book = real_time_data["order_book"].get(ex, {"bids":[],"asks":[]})
            for price, qty in book["bids"]:
                bid_map[price] = bid_map.get(price, 0) + qty
            for price, qty in book["asks"]:
                ask_map[price] = ask_map.get(price, 0) + qty

        sorted_bids = sorted(bid_map.items(), key=lambda x: x[0], reverse=True)[:depth_levels]
        sorted_asks = sorted(ask_map.items(), key=lambda x: x[0])[:depth_levels]

        # Avg volumes for wall detection
        avg_bid_vol = np.mean([q for _,q in sorted_bids]) if sorted_bids else 1
        avg_ask_vol = np.mean([q for _,q in sorted_asks]) if sorted_asks else 1

        bid_walls = [
            {"price": round(p,6), "volume": round(q,4), "strength": round(q/avg_bid_vol,2)}
            for p,q in sorted_bids if q >= avg_bid_vol * wall_multiplier
        ]
        ask_walls = [
            {"price": round(p,6), "volume": round(q,4), "strength": round(q/avg_ask_vol,2)}
            for p,q in sorted_asks if q >= avg_ask_vol * wall_multiplier
        ]

        # ── Cumulative delta from recent trades ────────────────
        recent_trades = [
            t for t in real_time_data["trades"]
            if t[4] in selected_exchanges and (now - t[2]) <= time_window
        ]

        buy_vol  = sum(t[1] for t in recent_trades if t[3]=='b')
        sell_vol = sum(t[1] for t in recent_trades if t[3]=='s')
        cum_delta = buy_vol - sell_vol
        total_vol = buy_vol + sell_vol + 1e-9

        # ── Per-level flow imbalance ───────────────────────────
        # Group trades into price buckets matching the order book
        flow_by_level = {}
        for trade in recent_trades:
            price = round(trade[0], 2)
            if price not in flow_by_level:
                flow_by_level[price] = {"buy":0,"sell":0}
            if trade[3]=='b':
                flow_by_level[price]["buy"] += trade[1]
            else:
                flow_by_level[price]["sell"] += trade[1]

        flow_levels = []
        for price, vols in sorted(flow_by_level.items(), reverse=True)[:20]:
            b,s = vols["buy"], vols["sell"]
            imb = (b-s)/(b+s+1e-9)
            flow_levels.append({
                "price":      round(price,6),
                "buy_vol":    round(b,4),
                "sell_vol":   round(s,4),
                "imbalance":  round(imb,4),
                "delta":      round(b-s,4)
            })

        # ── Absorption detection ───────────────────────────────
        # A bid wall that has recent sell-side trades against it = absorption
        absorptions = []
        for wall in bid_walls:
            wall_p = wall["price"]
            nearby = [l for l in flow_levels if abs(l["price"]-wall_p)/wall_p < 0.002]
            if nearby:
                sell_pressure = sum(l["sell_vol"] for l in nearby)
                if sell_pressure > 0:
                    absorptions.append({
                        "type":          "BID_ABSORPTION",
                        "price":         wall_p,
                        "wall_volume":   wall["volume"],
                        "sell_absorbed": round(sell_pressure, 4),
                        "signal":        "BULLISH"
                    })

        for wall in ask_walls:
            wall_p = wall["price"]
            nearby = [l for l in flow_levels if abs(l["price"]-wall_p)/wall_p < 0.002]
            if nearby:
                buy_pressure = sum(l["buy_vol"] for l in nearby)
                if buy_pressure > 0:
                    absorptions.append({
                        "type":        "ASK_ABSORPTION",
                        "price":       wall_p,
                        "wall_volume": wall["volume"],
                        "buy_absorbed": round(buy_pressure, 4),
                        "signal":      "BEARISH"
                    })

        # ── Current price ──────────────────────────────────────
        current_price = real_time_data.get("current_price", 0)
        if not current_price and sorted_bids and sorted_asks:
            current_price = (sorted_bids[0][0] + sorted_asks[0][0]) / 2

        # ── Overall flow signal ────────────────────────────────
        flow_ratio = buy_vol / total_vol
        if cum_delta > 0 and flow_ratio > 0.6:
            flow_signal = "STRONG_BUY_FLOW"
        elif cum_delta > 0:
            flow_signal = "BUY_FLOW"
        elif cum_delta < 0 and flow_ratio < 0.4:
            flow_signal = "STRONG_SELL_FLOW"
        elif cum_delta < 0:
            flow_signal = "SELL_FLOW"
        else:
            flow_signal = "NEUTRAL_FLOW"

        return jsonify({
            "success":        True,
            "symbol":         symbol,
            "current_price":  round(current_price, 6),
            "time_window_s":  time_window,
            "cumulative_delta": round(cum_delta, 4),
            "buy_volume":     round(buy_vol, 4),
            "sell_volume":    round(sell_vol, 4),
            "flow_ratio":     round(flow_ratio, 4),
            "flow_signal":    flow_signal,
            "bid_walls":      bid_walls[:5],
            "ask_walls":      ask_walls[:5],
            "absorptions":    absorptions[:5],
            "flow_levels":    flow_levels[:15],
            "order_book": {
                "bids": [{"price": round(p,6),"volume": round(q,4)} for p,q in sorted_bids[:10]],
                "asks": [{"price": round(p,6),"volume": round(q,4)} for p,q in sorted_asks[:10]]
            },
            "timestamp": datetime.utcnow().isoformat()
        })

    except Exception as e:
        import traceback; traceback.print_exc()
        return jsonify({"success": False, "error": str(e)}), 500


# ============================================================
# 3. LIQUIDITY SWEEP DETECTOR
# ============================================================

@app.route("/liquidity_sweep", methods=["POST"])
def liquidity_sweep():
    """
    Detects liquidity sweeps (stop hunts) from historical OHLCV:
    - Equal Highs / Equal Lows (inducement zones)
    - Wick sweeps above resistance / below support
    - Sweep + reversal patterns
    Returns recent sweeps and current inducement levels.
    """
    payload   = request.get_json() or {}
    symbol    = payload.get("symbol", "BTC/USDT").upper()
    timeframe = payload.get("timeframe", "1h")
    limit     = int(payload.get("limit", 200))
    wick_pct  = float(payload.get("wick_pct", 0.3))   # wick must be >=30 % of range
    eq_tol    = float(payload.get("eq_tolerance", 0.002))  # 0.2 % for "equal" levels

    try:
        conn = get_conn()
        cur  = conn.cursor(dictionary=True)
        cur.execute("""
            SELECT time_utc, open, high, low, close, volume
            FROM ohlcv_data
            WHERE symbol=%s AND timeframe=%s
            ORDER BY time_utc DESC LIMIT %s
        """, (symbol, timeframe, limit))
        rows = cur.fetchall()
        cur.close(); conn.close()

        if len(rows) < 20:
            return jsonify({"success": False, "error": "Not enough data"}), 400

        df = pd.DataFrame(rows)
        for c in ["open","high","low","close","volume"]:
            df[c] = df[c].astype(float)
        df = df.sort_values("time_utc").reset_index(drop=True)

        opens  = df["open"].values
        highs  = df["high"].values
        lows   = df["low"].values
        closes = df["close"].values
        times  = df["time_utc"].values

        sweeps = []
        inducement_highs = []
        inducement_lows  = []

        # ── Equal Highs / Lows (inducement zones) ─────────────
        for i in range(5, len(df)-1):
            # Compare last 5 candles for equal highs
            window_h = highs[max(0,i-10):i]
            window_l = lows[max(0,i-10):i]
            curr_h = highs[i]
            curr_l = lows[i]

            for prev_h in window_h:
                if prev_h > 0 and abs(curr_h - prev_h)/prev_h < eq_tol:
                    inducement_highs.append(round(float(curr_h), 6))
                    break

            for prev_l in window_l:
                if prev_l > 0 and abs(curr_l - prev_l)/prev_l < eq_tol:
                    inducement_lows.append(round(float(curr_l), 6))
                    break

        # Deduplicate inducement levels (cluster within eq_tol)
        def cluster_levels(levels):
            if not levels: return []
            levels = sorted(set(levels))
            clustered = [levels[0]]
            for lv in levels[1:]:
                if abs(lv - clustered[-1])/clustered[-1] > eq_tol:
                    clustered.append(lv)
            return clustered

        inducement_highs = cluster_levels(inducement_highs)[-10:]
        inducement_lows  = cluster_levels(inducement_lows)[:10]

        # ── Sweep Detection ────────────────────────────────────
        for i in range(10, len(df)-1):
            candle_range = highs[i] - lows[i]
            if candle_range == 0:
                continue

            upper_wick = highs[i] - max(opens[i], closes[i])
            lower_wick = min(opens[i], closes[i]) - lows[i]
            body       = abs(closes[i] - opens[i])

            time_str = str(times[i])

            # ── Bearish sweep: spike above then close back down ─
            if upper_wick / candle_range >= wick_pct:
                # Check if high swept a previous resistance
                prev_highs = highs[max(0,i-20):i]
                swept = [h for h in prev_highs if lows[i] < h < highs[i]]
                if swept:
                    # Confirmed if current close < swept level
                    if closes[i] < max(swept):
                        sweeps.append({
                            "type":         "BEARISH_SWEEP",
                            "time":         time_str,
                            "index":        i,
                            "sweep_price":  round(float(highs[i]), 6),
                            "close_price":  round(float(closes[i]), 6),
                            "swept_level":  round(float(max(swept)), 6),
                            "wick_pct":     round(upper_wick/candle_range*100, 1),
                            "volume":       round(float(df["volume"].iloc[i]), 4),
                            "signal":       "SHORT_OPPORTUNITY",
                            "description":  "Price swept above resistance and rejected – potential short"
                        })

            # ── Bullish sweep: spike below then close back up ──
            if lower_wick / candle_range >= wick_pct:
                prev_lows = lows[max(0,i-20):i]
                swept = [l for l in prev_lows if highs[i] > l > lows[i]]
                if swept:
                    if closes[i] > min(swept):
                        sweeps.append({
                            "type":         "BULLISH_SWEEP",
                            "time":         time_str,
                            "index":        i,
                            "sweep_price":  round(float(lows[i]), 6),
                            "close_price":  round(float(closes[i]), 6),
                            "swept_level":  round(float(min(swept)), 6),
                            "wick_pct":     round(lower_wick/candle_range*100, 1),
                            "volume":       round(float(df["volume"].iloc[i]), 4),
                            "signal":       "LONG_OPPORTUNITY",
                            "description":  "Price swept below support and recovered – potential long"
                        })

        # Keep only last 20 and sort newest first
        sweeps = sweeps[-20:][::-1]

        # ── Current bar sweep risk ─────────────────────────────
        current = df.iloc[-1]
        curr_range  = float(current["high"] - current["low"])
        curr_upper  = float(current["high"] - max(current["open"], current["close"]))
        curr_lower  = float(min(current["open"], current["close"]) - current["low"])

        sweep_risk = "NONE"
        if curr_range > 0:
            if curr_upper / curr_range > 0.5:
                sweep_risk = "POTENTIAL_BEARISH_SWEEP"
            elif curr_lower / curr_range > 0.5:
                sweep_risk = "POTENTIAL_BULLISH_SWEEP"

        # Proximity to inducement zones
        curr_price = float(closes[-1])
        near_high_zone = any(abs(curr_price - h)/h < 0.005 for h in inducement_highs)
        near_low_zone  = any(abs(curr_price - l)/l < 0.005 for l in inducement_lows)

        return jsonify({
            "success":           True,
            "symbol":            symbol,
            "timeframe":         timeframe,
            "current_price":     round(curr_price, 6),
            "sweeps":            sweeps,
            "total_sweeps":      len(sweeps),
            "bullish_sweeps":    sum(1 for s in sweeps if s["type"]=="BULLISH_SWEEP"),
            "bearish_sweeps":    sum(1 for s in sweeps if s["type"]=="BEARISH_SWEEP"),
            "inducement_highs":  inducement_highs,
            "inducement_lows":   inducement_lows,
            "sweep_risk":        sweep_risk,
            "near_high_zone":    near_high_zone,
            "near_low_zone":     near_low_zone,
            "timestamp":         datetime.utcnow().isoformat()
        })

    except Exception as e:
        import traceback; traceback.print_exc()
        return jsonify({"success": False, "error": str(e)}), 500


# ============================================================
# 4. ENHANCED SIGNAL GENERATOR (combines all 3 new indicators)
# ============================================================

@app.route("/enhanced_signal_v2", methods=["POST"])
def enhanced_signal_v2():
    """
    Full institutional-grade signal combining:
    - Classic TA (RSI, MACD, EMA, BB, ATR, ADX, CCI, Stoch)
    - Volume Profile (POC, VAH, VAL position)
    - Order Book Flow (cumulative delta, walls, absorption)
    - Liquidity Sweep (recent sweeps, inducement zones, sweep risk)
    Returns a composite signal with score 0-100 and detailed reasoning.
    """
    payload   = request.get_json() or {}
    symbol    = payload.get("symbol", "BTC/USDT").upper()
    timeframe = payload.get("timeframe", "4h")
    limit     = int(payload.get("limit", 100))
    selected_exchanges = payload.get(
        "exchanges",
        ["binance","bybit","okx","gateio","huobi","bitget","mexc","coinbase"]
    )

    try:
        # ── 1. Classic TA ──────────────────────────────────────
        ex = get_exchange()
        ohlcv = ex.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
        if not ohlcv:
            return jsonify({"success": False, "error": "No OHLCV data"}), 400

        df = pd.DataFrame(ohlcv, columns=["timestamp","open","high","low","close","volume"])
        df["time_utc"] = pd.to_datetime(df["timestamp"], unit="ms")
        df = df.sort_values("time_utc").reset_index(drop=True)

        close  = df["close"].astype(float)
        high   = df["high"].astype(float)
        low    = df["low"].astype(float)
        volume = df["volume"].astype(float)
        curr_price = float(close.iloc[-1])

        # RSI
        delta = close.diff()
        gain  = delta.where(delta>0,0).rolling(14).mean()
        loss  = (-delta.where(delta<0,0)).rolling(14).mean()
        rsi   = float((100 - 100/(1+gain/loss)).iloc[-1]) if float(loss.iloc[-1]) else 100.0

        # MACD
        ema12      = close.ewm(span=12,adjust=False).mean()
        ema26      = close.ewm(span=26,adjust=False).mean()
        macd_line  = ema12 - ema26
        macd_sig   = macd_line.ewm(span=9,adjust=False).mean()
        macd_hist  = float((macd_line - macd_sig).iloc[-1])
        macd_cross = "BULLISH" if float(macd_line.iloc[-1]) > float(macd_sig.iloc[-1]) else "BEARISH"

        # EMAs
        ema20  = float(close.ewm(span=20,adjust=False).mean().iloc[-1])
        ema50  = float(close.ewm(span=50,adjust=False).mean().iloc[-1])
        ema200 = float(close.ewm(span=200,adjust=False).mean().iloc[-1]) if len(close)>=200 else ema50

        # Bollinger
        bb_mid   = close.rolling(20).mean()
        bb_std   = close.rolling(20).std()
        bb_upper = float((bb_mid + 2*bb_std).iloc[-1])
        bb_lower = float((bb_mid - 2*bb_std).iloc[-1])

        # ATR
        tr1 = high - low
        tr2 = abs(high - close.shift())
        tr3 = abs(low  - close.shift())
        atr = float(pd.concat([tr1,tr2,tr3],axis=1).max(axis=1).rolling(14).mean().iloc[-1])
        atr_pct = atr / curr_price * 100

        # ADX (simplified)
        try:
            adx_df  = ta.adx(high, low, close, length=14)
            adx_val = float(adx_df.iloc[-1,0]) if not adx_df.empty else 20.0
            dip     = float(adx_df.iloc[-1,1]) if adx_df.shape[1]>1 else 20.0
            dim     = float(adx_df.iloc[-1,2]) if adx_df.shape[1]>2 else 20.0
        except Exception:
            adx_val, dip, dim = 20.0, 20.0, 20.0

        # Volume trend
        vol_avg20 = float(volume.rolling(20).mean().iloc[-1]) or 1
        vol_ratio = float(volume.iloc[-1]) / vol_avg20

        # ── 2. Volume Profile (in-process, no HTTP round-trip) ─
        vp_signal = "UNKNOWN"
        poc_price = curr_price
        vah_price = curr_price * 1.005
        val_price = curr_price * 0.995
        try:
            conn2 = get_conn()
            cur2  = conn2.cursor(dictionary=True)
            cur2.execute("""
                SELECT high,low,volume FROM ohlcv_data
                WHERE symbol=%s AND timeframe=%s
                ORDER BY time_utc DESC LIMIT 200
            """, (symbol, timeframe))
            vp_rows = cur2.fetchall()
            cur2.close(); conn2.close()

            if len(vp_rows) >= 20:
                num_bins   = 40
                ph = max(float(r["high"]) for r in vp_rows)
                pl = min(float(r["low"])  for r in vp_rows)
                bins = np.linspace(pl, ph, num_bins+1)
                bvol = np.zeros(num_bins)
                for r in vp_rows:
                    rh = float(r["high"]); rl = float(r["low"]); rv = float(r["volume"])
                    touched = [i for i in range(num_bins) if bins[i]<=rh and bins[i+1]>=rl]
                    if touched:
                        share = rv/len(touched)
                        for i in touched: bvol[i] += share
                poc_idx   = int(np.argmax(bvol))
                poc_price = float((bins[poc_idx]+bins[poc_idx+1])/2)
                # Quick 70% VA
                target = bvol.sum()*0.7; va_v=bvol[poc_idx]; li=poc_idx; hi2=poc_idx
                while va_v < target:
                    up = bvol[hi2+1] if hi2+1<num_bins else 0
                    dn = bvol[li-1]  if li-1>=0       else 0
                    if up>=dn: hi2=min(hi2+1,num_bins-1); va_v+=up
                    else:      li=max(li-1,0);            va_v+=dn
                    if hi2==num_bins-1 and li==0: break
                vah_price = float((bins[hi2]+bins[hi2+1])/2)
                val_price = float((bins[li]+bins[li+1])/2)

                if curr_price > vah_price:   vp_signal = "ABOVE_VA"
                elif curr_price < val_price: vp_signal = "BELOW_VA"
                elif abs(curr_price-poc_price)/poc_price < 0.002: vp_signal = "AT_POC"
                elif curr_price > poc_price: vp_signal = "ABOVE_POC"
                else:                        vp_signal = "BELOW_POC"
        except Exception as vpe:
            print(f"VP inline error: {vpe}")

        # ── 3. Order Book Flow ─────────────────────────────────
        now = time.time()
        recent_trades = [
            t for t in real_time_data["trades"]
            if t[4] in selected_exchanges and (now - t[2]) <= 120
        ]
        buy_vol_rt  = sum(t[1] for t in recent_trades if t[3]=='b')
        sell_vol_rt = sum(t[1] for t in recent_trades if t[3]=='s')
        cum_delta   = buy_vol_rt - sell_vol_rt
        flow_ratio  = buy_vol_rt / (buy_vol_rt + sell_vol_rt + 1e-9)

        # Walls
        bid_map = {}; ask_map = {}
        for ex_name in selected_exchanges:
            book = real_time_data["order_book"].get(ex_name, {"bids":[],"asks":[]})
            for p,q in book["bids"]: bid_map[p] = bid_map.get(p,0) + q
            for p,q in book["asks"]: ask_map[p] = ask_map.get(p,0) + q
        sorted_bids = sorted(bid_map.items(), key=lambda x:x[0], reverse=True)[:20]
        sorted_asks = sorted(ask_map.items(), key=lambda x:x[0])[:20]
        avg_bv = np.mean([q for _,q in sorted_bids]) if sorted_bids else 1
        avg_av = np.mean([q for _,q in sorted_asks]) if sorted_asks else 1
        bid_walls_exist = any(q>=avg_bv*3 for _,q in sorted_bids)
        ask_walls_exist = any(q>=avg_av*3 for _,q in sorted_asks)

        if   cum_delta > 0 and flow_ratio > 0.6: ob_signal = "STRONG_BUY_FLOW"
        elif cum_delta > 0:                       ob_signal = "BUY_FLOW"
        elif cum_delta < 0 and flow_ratio < 0.4: ob_signal = "STRONG_SELL_FLOW"
        elif cum_delta < 0:                       ob_signal = "SELL_FLOW"
        else:                                     ob_signal = "NEUTRAL"

        # ── 4. Liquidity Sweep (inline, no HTTP) ──────────────
        sweep_signal = "NONE"
        recent_sweep_type = "NONE"
        near_inducement = False
        try:
            conn3 = get_conn()
            cur3  = conn3.cursor(dictionary=True)
            cur3.execute("""
                SELECT open,high,low,close,volume FROM ohlcv_data
                WHERE symbol=%s AND timeframe=%s
                ORDER BY time_utc DESC LIMIT 50
            """, (symbol, timeframe))
            sw_rows = cur3.fetchall()
            cur3.close(); conn3.close()

            if len(sw_rows) >= 10:
                sw_df = pd.DataFrame(sw_rows)
                for c in ["open","high","low","close","volume"]: sw_df[c]=sw_df[c].astype(float)
                sw_df = sw_df.sort_values("open",ascending=False).reset_index(drop=True)  # newest first
                opens_  = sw_df["open"].values
                highs_  = sw_df["high"].values
                lows_   = sw_df["low"].values
                closes_ = sw_df["close"].values

                # Check last 5 candles for sweeps
                for i in range(1, min(5, len(sw_df))):
                    crange = highs_[i] - lows_[i]
                    if crange == 0: continue
                    uwik = highs_[i] - max(opens_[i], closes_[i])
                    lwik = min(opens_[i], closes_[i]) - lows_[i]
                    if lwik/crange > 0.4 and closes_[i] > min(opens_[i],closes_[i])*1.001:
                        recent_sweep_type = "BULLISH_SWEEP"
                        sweep_signal = "LONG_BIAS"
                        break
                    if uwik/crange > 0.4 and closes_[i] < max(opens_[i],closes_[i])*0.999:
                        recent_sweep_type = "BEARISH_SWEEP"
                        sweep_signal = "SHORT_BIAS"
                        break

                # Inducement proximity
                eq_tol = 0.002
                ind_h = []; ind_l = []
                for i in range(5, len(sw_df)):
                    wh = highs_[max(0,i-10):i]
                    wl = lows_[max(0,i-10):i]
                    for ph in wh:
                        if ph>0 and abs(highs_[i]-ph)/ph < eq_tol:
                            ind_h.append(highs_[i]); break
                    for pl in wl:
                        if pl>0 and abs(lows_[i]-pl)/pl < eq_tol:
                            ind_l.append(lows_[i]); break

                near_inducement = (
                    any(abs(curr_price-h)/h < 0.005 for h in ind_h) or
                    any(abs(curr_price-l)/l < 0.005 for l in ind_l)
                )
        except Exception as swe:
            print(f"Sweep inline error: {swe}")

        # ============================================================
        # COMPOSITE SIGNAL SCORING (0-100)
        # ============================================================
        score  = 50
        reasons = []

        # ── Classic TA scoring ───────────────────────────────
        # RSI
        if rsi < 30:
            score += 15; reasons.append(f"RSI oversold ({rsi:.1f})")
        elif rsi > 70:
            score -= 15; reasons.append(f"RSI overbought ({rsi:.1f})")
        elif rsi > 55:
            score += 5;  reasons.append(f"RSI bullish ({rsi:.1f})")
        elif rsi < 45:
            score -= 5;  reasons.append(f"RSI bearish ({rsi:.1f})")

        # MACD
        if macd_cross == "BULLISH" and macd_hist > 0:
            score += 12; reasons.append("MACD bullish crossover + positive hist")
        elif macd_cross == "BEARISH" and macd_hist < 0:
            score -= 12; reasons.append("MACD bearish crossover + negative hist")
        elif macd_cross == "BULLISH":
            score += 5;  reasons.append("MACD bullish cross")
        else:
            score -= 5;  reasons.append("MACD bearish cross")

        # EMA alignment
        if curr_price > ema20 > ema50 > ema200:
            score += 18; reasons.append("Strong uptrend: price>EMA20>EMA50>EMA200")
        elif curr_price < ema20 < ema50 < ema200:
            score -= 18; reasons.append("Strong downtrend: price<EMA20<EMA50<EMA200")
        elif curr_price > ema20 > ema50:
            score += 10; reasons.append("Uptrend: price>EMA20>EMA50")
        elif curr_price < ema20 < ema50:
            score -= 10; reasons.append("Downtrend: price<EMA20<EMA50")

        # Bollinger
        if curr_price < bb_lower:
            score += 10; reasons.append("Price below BB lower – oversold")
        elif curr_price > bb_upper:
            score -= 10; reasons.append("Price above BB upper – overbought")

        # ADX
        if adx_val > 25 and dip > dim:
            score += 8;  reasons.append(f"Strong uptrend ADX={adx_val:.1f} +DI>{dim:.1f}")
        elif adx_val > 25 and dim > dip:
            score -= 8;  reasons.append(f"Strong downtrend ADX={adx_val:.1f} -DI>{dip:.1f}")

        # Volume surge
        if vol_ratio > 1.5 and float(close.iloc[-1]) > float(close.iloc[-2]):
            score += 8;  reasons.append(f"Volume surge ({vol_ratio:.1f}x) on up candle")
        elif vol_ratio > 1.5 and float(close.iloc[-1]) < float(close.iloc[-2]):
            score -= 8;  reasons.append(f"Volume surge ({vol_ratio:.1f}x) on down candle")

        # ── Volume Profile scoring ────────────────────────────
        if vp_signal == "ABOVE_VA":
            score += 10; reasons.append("Price above Value Area (bullish breakout)")
        elif vp_signal == "BELOW_VA":
            score -= 10; reasons.append("Price below Value Area (bearish breakdown)")
        elif vp_signal == "AT_POC":
            score += 0;  reasons.append("Price at POC – key decision zone")
        elif vp_signal == "ABOVE_POC":
            score += 5;  reasons.append("Price above POC – slight bullish bias")
        elif vp_signal == "BELOW_POC":
            score -= 5;  reasons.append("Price below POC – slight bearish bias")

        # ── Order Book Flow scoring ───────────────────────────
        if ob_signal == "STRONG_BUY_FLOW":
            score += 15; reasons.append("Strong buy order flow + delta positive")
        elif ob_signal == "BUY_FLOW":
            score += 8;  reasons.append("Buy order flow dominance")
        elif ob_signal == "STRONG_SELL_FLOW":
            score -= 15; reasons.append("Strong sell order flow + delta negative")
        elif ob_signal == "SELL_FLOW":
            score -= 8;  reasons.append("Sell order flow dominance")

        if bid_walls_exist and not ask_walls_exist:
            score += 5;  reasons.append("Bid wall detected – support present")
        elif ask_walls_exist and not bid_walls_exist:
            score -= 5;  reasons.append("Ask wall detected – resistance present")

        # ── Liquidity Sweep scoring ───────────────────────────
        if sweep_signal == "LONG_BIAS":
            score += 12; reasons.append(f"Recent BULLISH sweep – smart money long entry")
        elif sweep_signal == "SHORT_BIAS":
            score -= 12; reasons.append(f"Recent BEARISH sweep – smart money short entry")

        if near_inducement:
            reasons.append("⚠ Price near inducement zone – sweep likely incoming")
            score = max(20, min(80, score))  # Force caution band

        # Cap and determine final label
        score = max(0, min(100, score))

        if score >= 80:
            label = "STRONG BUY";    rec = "GO LONG";        color = "success"
        elif score >= 65:
            label = "BUY";           rec = "Consider Long";  color = "info"
        elif score >= 50:
            label = "SLIGHT BULLISH";rec = "Hold / Small Long"; color = "info"
        elif score >= 40:
            label = "NEUTRAL";       rec = "Wait";           color = "secondary"
        elif score >= 30:
            label = "SLIGHT BEARISH";rec = "Hold / Small Short"; color = "warning"
        elif score >= 20:
            label = "SELL";          rec = "Consider Short"; color = "warning"
        else:
            label = "STRONG SELL";   rec = "GO SHORT";       color = "danger"

        # Stop loss & take profit based on ATR
        if "BUY" in label or "BULLISH" in label:
            stop_loss  = curr_price - 1.5 * atr
            tp1        = curr_price + 1.5 * atr
            tp2        = curr_price + 3.0 * atr
        else:
            stop_loss  = curr_price + 1.5 * atr
            tp1        = curr_price - 1.5 * atr
            tp2        = curr_price - 3.0 * atr

        risk_pct  = abs(curr_price - stop_loss) / curr_price * 100
        rr_ratio  = abs(tp1 - curr_price) / abs(curr_price - stop_loss) if abs(curr_price-stop_loss) > 0 else 1.0

        return jsonify({
            "success":        True,
            "symbol":         symbol,
            "timeframe":      timeframe,
            "current_price":  round(curr_price, 6),
            "signal":         label,
            "recommendation": rec,
            "score":          round(score, 1),
            "color":          color,
            "reasons":        reasons,
            "indicators": {
                "rsi":         round(rsi, 2),
                "macd_hist":   round(macd_hist, 6),
                "macd_cross":  macd_cross,
                "ema20":       round(ema20, 6),
                "ema50":       round(ema50, 6),
                "ema200":      round(ema200, 6),
                "bb_upper":    round(bb_upper, 6),
                "bb_lower":    round(bb_lower, 6),
                "adx":         round(adx_val, 2),
                "di_plus":     round(dip, 2),
                "di_minus":    round(dim, 2),
                "atr":         round(atr, 6),
                "atr_pct":     round(atr_pct, 3),
                "volume_ratio": round(vol_ratio, 2)
            },
            "volume_profile": {
                "signal": vp_signal,
                "poc":    round(poc_price, 6),
                "vah":    round(vah_price, 6),
                "val":    round(val_price, 6)
            },
            "order_book_flow": {
                "signal":        ob_signal,
                "cumulative_delta": round(cum_delta, 4),
                "flow_ratio":    round(flow_ratio, 4),
                "bid_walls":     bid_walls_exist,
                "ask_walls":     ask_walls_exist
            },
            "liquidity_sweep": {
                "signal":          sweep_signal,
                "recent_sweep":    recent_sweep_type,
                "near_inducement": near_inducement
            },
            "trading_levels": {
                "stop_loss":  round(stop_loss, 6),
                "take_profit_1": round(tp1, 6),
                "take_profit_2": round(tp2, 6),
                "risk_pct":   round(risk_pct, 3),
                "rr_ratio":   round(rr_ratio, 2)
            },
            "timestamp": datetime.utcnow().isoformat()
        })

    except Exception as e:
        import traceback; traceback.print_exc()
        return jsonify({"success": False, "error": str(e)}), 500
