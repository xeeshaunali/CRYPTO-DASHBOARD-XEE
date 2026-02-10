// Change this if your Flask runs on different port/host
const API = "http://127.0.0.1:8000";

// === ALL YOUR ORIGINAL FUNCTIONS (unchanged) ===
// tab OHVCV START
async function fetchOHLCV() {
    const symbol = document.getElementById("symbol").value.trim();
    const timeframe = document.getElementById("timeframe").value;
    const fromYear = document.getElementById("fromYear").value;
    const toYear = document.getElementById("toYear").value;
    showAlert("ohlcvAlert", "Fetching from Binance...", "info");
    try {
        const res = await fetch(API + "/fetch_data", {
            method:"POST",
            headers:{"Content-Type":"application/json"},
            body: JSON.stringify({symbol, timeframe, from_year: fromYear, to_year: toYear})
        });
        const json = await res.json();
        if (json.success) {
            showAlert("ohlcvAlert", json.message, "success");
            displayOHLCV(json.data);
        } else {
            showAlert("ohlcvAlert", json.error || "Failed");
        }
    } catch(e) {
        showAlert("ohlcvAlert", "Error: "+e.message);
    }
}


async function loadFromDB() {
    const symbol = document.getElementById("symbol").value.trim().toUpperCase().replace(/[-_]/g, '/');
    const timeframe = document.getElementById("timeframe").value;
    const fromYear = document.getElementById("fromYear").value;
    const toYear = document.getElementById("toYear").value;

    let alertMsg = `Loading from DB: ${symbol} ${timeframe}`;
    if (fromYear) alertMsg += ` from ${fromYear}`;
    if (toYear) alertMsg += ` to ${toYear}`;
    showAlert("ohlcvAlert", alertMsg, "info");

    try {
        const payload = { symbol, timeframe };
        if (fromYear) payload.from_year = fromYear;
        if (toYear) payload.to_year = toYear;

        const res = await fetch(API + "/fetch_from_db", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload)
        });

        const json = await res.json();
        if (json.success) {
            showAlert("ohlcvAlert", `Loaded ${json.data.length} rows from DB`, "success");
            displayOHLCV(json.data);
        } else {
            showAlert("ohlcvAlert", json.error || "No data in database for selected range", "warning");
        }
    } catch (e) {
        showAlert("ohlcvAlert", "Error: " + e.message, "danger");
    }
}

function displayOHLCV(rows) {
    const tbody = document.getElementById("ohlcvBody");
    tbody.innerHTML = "";
    // Sort rows descending by time (newest first)
    rows.sort((a, b) => new Date(b["Time (UTC)"] || b.time_utc) - new Date(a["Time (UTC)"] || a.time_utc));
    rows.forEach((r, i) => {
        const previousVol = (i < rows.length - 1) ? Number(rows[i + 1].volume || rows[i + 1].Volume) : null;
        const currentVol = Number(r.volume || r.Volume);
        const diff = previousVol !== null ? currentVol - previousVol : null;
        let volChangeHtml = 'N/A';
        if (diff !== null) {
            const className = diff > 0 ? 'positive' : 'negative';
            const sign = diff > 0 ? '+' : '';
            volChangeHtml = `<span class="${className}">${sign}${diff.toLocaleString(undefined, {maximumFractionDigits: 2})}</span>`;
        }
        const tr = document.createElement("tr");
        tr.innerHTML = `
            <td>${i+1}</td>
            <td>${r.time_utc || r["Time (UTC)"]}</td>
            <td>${Number(r.open || r.Open).toFixed(4)}</td>
            <td>${Number(r.high || r.High).toFixed(4)}</td>
            <td>${Number(r.low || r.Low).toFixed(4)}</td>
            <td>${Number(r.close || r.Close).toFixed(4)}</td>
            <td>${currentVol.toLocaleString()}</td>
            <td>${volChangeHtml}</td>
        `;
        tbody.appendChild(tr);
    });
}


// tab OHVCV END


// tab SIGNALS Analyze Start
async function analyzeSymbol() {
    const symbol = document.getElementById("signalSymbol").value.trim();
    const timeframe = document.getElementById("signalTimeframe").value;
    if (!symbol) {
        showAlert("signalAlert", "Please enter a symbol");
        return;
    }
    showAlert("signalAlert", `Analyzing ${symbol} ${timeframe}...`, "info");
    try {
        const res = await fetch(API + "/analyze_symbol", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ symbol, timeframe })
        });
        
        const json = await res.json();
        
        if (!json.success) {
            showAlert("signalAlert", json.error || "Failed to analyze symbol");
            return;
        }
        
        // Safely handle the response
        let cls = "signal-neutral";
        if (json.signal && json.signal.startsWith("STRONG_BULLISH")) cls = "signal-strong-bullish";
        else if (json.signal && json.signal.startsWith("BULLISH")) cls = "signal-bullish";
        else if (json.signal && json.signal.startsWith("STRONG_BEARISH") || json.signal.startsWith("BEARISH")) cls = "signal-bearish";
        else if (json.signal && json.signal.startsWith("WATCH_")) cls = "signal-watch";
        
        const d = json;
        const ind = d.indicators || {};
        const c = d.last_candle || {};
        
        const html = `
            <p><strong>Symbol:</strong> ${d.symbol || 'N/A'} &nbsp; <strong>Timeframe:</strong> ${d.timeframe || 'N/A'}</p>
            <p><strong>Last Candle:</strong> ${c.time_utc || 'N/A'} |
               O: ${c.open ? c.open.toFixed(4) : 'N/A'} H: ${c.high ? c.high.toFixed(4) : 'N/A'}
               L: ${c.low ? c.low.toFixed(4) : 'N/A'} C: ${c.close ? c.close.toFixed(4) : 'N/A'}
               Vol: ${c.volume ? c.volume.toLocaleString() : 'N/A'}</p>
            <p><strong>RSI(14):</strong> ${ind.rsi ? ind.rsi.toFixed(2) : "n/a"} &nbsp;
               <strong>MACD:</strong> ${ind.macd ? ind.macd.toFixed(4) : "n/a"} &nbsp;
               <strong>Signal:</strong> ${ind.macd_signal ? ind.macd_signal.toFixed(4) : "n/a"}</p>
            <p><strong>EMA20:</strong> ${ind.ema20 ? ind.ema20.toFixed(4) : "n/a"} &nbsp;
               <strong>EMA50:</strong> ${ind.ema50 ? ind.ema50.toFixed(4) : "n/a"} &nbsp;
               <strong>EMA100:</strong> ${ind.ema100 ? ind.ema100.toFixed(4) : "n/a"} &nbsp;
               <strong>EMA200:</strong> ${ind.ema200 ? ind.ema200.toFixed(4) : "n/a"}</p>
            <p class="${cls}"><strong>Signal:</strong> ${d.signal || 'NEUTRAL'} (score ${d.score || 0})</p>
            <ul>${(d.reasons && Array.isArray(d.reasons) ? d.reasons.map(r => `<li>${r}</li>`).join("") : '<li>No analysis reasons available</li>')}</ul>
        `;
        document.getElementById("signalDetails").innerHTML = html;
        showAlert("signalAlert", "Analysis completed", "success");
    } catch (e) {
        console.error("Analyze symbol error:", e);
        showAlert("signalAlert", "Error: " + e.message);
    }
}
//end


// Gainers Losers Tab Start
async function refreshGainersLosers() {
    showAlert("gainersAlert", "Fetching from Binance...", "info");
    showAlert("losersAlert", "Fetching from Binance...", "info");
    try {
        const res = await fetch(API + "/fetch_gainers_losers");
        const json = await res.json();
        if (json.success) {
            showAlert("gainersAlert", json.message, "success");
            showAlert("losersAlert", json.message, "success");
            loadGainers();
            loadLosers();
        } else {
            showAlert("gainersAlert", json.error || "Failed");
            showAlert("losersAlert", json.error || "Failed");
        }
    } catch(e) {
        showAlert("gainersAlert", "Error: "+e.message);
        showAlert("losersAlert", "Error: "+e.message);
    }
}
//end


// tab Gainer start
async function loadGainers() {
    const res = await fetch(API + "/get_gainers");
    const json = await res.json();
    const tbody = document.getElementById("gainersBody");
    tbody.innerHTML = "";
    json.data.forEach((d, i) => {
        const tr = document.createElement("tr");
        tr.innerHTML = `
            <td>${i+1}</td>
            <td><strong>${d.symbol}</strong></td>
            <td>$${Number(d.price).toFixed(6)}</td>
            <td class="positive">+${d.price_change_percent.toFixed(2)}%</td>
            <td>$${Number(d.volume_24h).toLocaleString()}</td>
        `;
        tbody.appendChild(tr);
    });
}
//end

// tab Loser start
async function loadLosers() {
    const res = await fetch(API + "/get_losers");
    const json = await res.json();
    const tbody = document.getElementById("losersBody");
    tbody.innerHTML = "";
    json.data.forEach((d, i) => {
        const tr = document.createElement("tr");
        tr.innerHTML = `
            <td>${i+1}</td>
            <td><strong>${d.symbol}</strong></td>
            <td>$${Number(d.price).toFixed(6)}</td>
            <td class="negative">${d.price_change_percent.toFixed(2)}%</td>
            <td>$${Number(d.volume_24h).toLocaleString()}</td>
        `;
        tbody.appendChild(tr);
    });
}
//end


// Scan Gainer ON OHLCV Tab Signals Start
async function loadGainerSignals() {
    showAlert("gainerSignalsAlert", "Scanning gainers with full indicators...", "info");
    const tbody = document.getElementById("gainerSignalsBody");
    tbody.innerHTML = "";
    try {
        const res = await fetch(API + "/gainers_signals");
        const json = await res.json();
        if (!json.success) {
            showAlert("gainerSignalsAlert", "Search failed");
            return;
        }
        json.data.forEach((d, i) => {
            // Determine signal class
            let cls = "signal-neutral";
            if (d.signal.startsWith("STRONG_BULLISH")) cls = "signal-strong-bullish";
            else if (d.signal.startsWith("BULLISH")) cls = "signal-bullish";
            else if (d.signal.startsWith("STRONG_BEARISH") || d.signal.startsWith("BEARISH")) cls = "signal-bearish";
            else if (d.signal.startsWith("WATCH_")) cls = "signal-watch";
            
            // Risk level badge
            let riskBadge = 'secondary';
            let riskLevel = d.risk_level || 'N/A';
            if (riskLevel === 'HIGH') riskBadge = 'danger';
            else if (riskLevel === 'MEDIUM') riskBadge = 'warning';
            else if (riskLevel === 'LOW') riskBadge = 'success';
            else if (riskLevel === 'VERY_LOW') riskBadge = 'info';
            
            // Trend badge
            let trendBadge = 'secondary';
            let trend = d.trend || 'neutral';
            if (trend === 'bullish') trendBadge = 'success';
            else if (trend === 'bearish') trendBadge = 'danger';
            else if (trend === 'mixed') trendBadge = 'warning';
            
            const tr = document.createElement("tr");
            tr.innerHTML = `
                <td>${i+1}</td>
                <td><strong>${d.symbol}</strong></td>
                <td class="${d.price_change_percent >= 0 ? "positive" : "negative"}">
                    ${d.price_change_percent.toFixed(2)}%
                </td>
                <td>$${Number(d.volume_24h).toLocaleString()}</td>
                <td>${d.close.toFixed(6)}</td>
                <td>${d.rsi ? d.rsi.toFixed(2) : "n/a"}</td>
                <td class="${cls}">${d.signal}</td>
                <td>
                    <div class="progress" style="height: 20px; min-width: 60px;">
                        <div class="progress-bar ${cls.includes('bullish') ? 'bg-success' : cls.includes('bearish') ? 'bg-danger' : 'bg-secondary'}" 
                             style="width: ${d.score}%">
                            ${d.score}
                        </div>
                    </div>
                </td>
                <td>${d.confidence ? d.confidence.toFixed(1) + '%' : 'n/a'}</td>
                <td><span class="badge bg-${trendBadge}">${trend}</span></td>
                <td><span class="badge bg-${riskBadge}">${riskLevel}</span></td>
            `;
            tbody.appendChild(tr);
        });
        showAlert("gainerSignalsAlert", "Gainer signals ready", "success");
    } catch(e) {
        showAlert("gainerSignalsAlert", "Error: "+e.message);
    }
}
//end

// tab Rotation Start
async function loadRotation() {
    showAlert("rotationAlert", "Scanning rotation opportunities...", "info");
    const container = document.getElementById("rotationResults");
    container.innerHTML = "";
    try {
        const res = await fetch(API + "/rotation_signals");
        const json = await res.json();
        if (!json.success) {
            showAlert("rotationAlert", json.error || "Failed");
            return;
        }
        const data = json.data;
        if (!data.length) {
            showAlert("rotationAlert", "No rotation candidates found.", "warning");
            return;
        }
        data.forEach((block, idx) => {
            const div = document.createElement("div");
            div.className = "card mb-3";
            let html = `
                <div class="card-header">
                    Pumped: <strong>${block.pumped_symbol}</strong>
                    (Cat: ${block.pumped_category}) – ${block.pumped_change_pct.toFixed(2)}%,
                    Vol: $${Number(block.pumped_volume).toLocaleString()}
                </div>
                <div class="card-body">
                    <table class="table table-sm table-bordered">
                        <thead class="table-info">
                            <tr>
                                <th>#</th><th>Symbol</th><th>Score</th><th>Label</th><th>RSI</th><th>24h %</th><th>Vol</th><th>Close</th><th>Confidence</th><th>Trend</th><th>Risk</th>
                            </tr>
                        </thead>
                        <tbody>
            `;
            block.rotation_candidates.forEach((c, i) => {
                let cls = "signal-neutral";
                if (c.label.startsWith("STRONG_BULLISH")) cls = "signal-strong-bullish";
                else if (c.label.startsWith("BULLISH")) cls = "signal-bullish";
                else if (c.label.startsWith("STRONG_BEARISH") || c.label.startsWith("BEARISH")) cls = "signal-bearish";
                else if (c.label.startsWith("WATCH_")) cls = "signal-watch";
                
                // Risk level badge
                let riskBadge = 'secondary';
                let riskLevel = c.risk_level || 'N/A';
                if (riskLevel === 'HIGH') riskBadge = 'danger';
                else if (riskLevel === 'MEDIUM') riskBadge = 'warning';
                else if (riskLevel === 'LOW') riskBadge = 'success';
                else if (riskLevel === 'VERY_LOW') riskBadge = 'info';
                
                // Trend badge
                let trendBadge = 'secondary';
                let trend = c.trend || 'neutral';
                if (trend === 'bullish') trendBadge = 'success';
                else if (trend === 'bearish') trendBadge = 'danger';
                else if (trend === 'mixed') trendBadge = 'warning';
                
                html += `
                    <tr>
                        <td>${i+1}</td>
                        <td><strong>${c.symbol}</strong></td>
                        <td>
                            <div class="progress" style="height: 20px; min-width: 60px;">
                                <div class="progress-bar ${cls.includes('bullish') ? 'bg-success' : cls.includes('bearish') ? 'bg-danger' : 'bg-secondary'}" 
                                     style="width: ${c.score}%">
                                    ${c.score}
                                </div>
                            </div>
                        </td>
                        <td class="${cls}">${c.label}</td>
                        <td>${c.rsi ? c.rsi.toFixed(2) : "n/a"}</td>
                        <td>${c.today_change_pct.toFixed(2)}%</td>
                        <td>$${Number(c.today_volume).toLocaleString()}</td>
                        <td>${c.close.toFixed(6)}</td>
                        <td>${c.confidence ? c.confidence.toFixed(1) + '%' : 'n/a'}</td>
                        <td><span class="badge bg-${trendBadge}">${trend}</span></td>
                        <td><span class="badge bg-${riskBadge}">${riskLevel}</span></td>
                    </tr>
                `;
            });
            html += `</tbody></table></div>`;
            div.innerHTML = html;
            container.appendChild(div);
        });
        showAlert("rotationAlert", "Rotation candidates ready.", "success");
    } catch(e) {
        showAlert("rotationAlert", "Error: "+e.message);
    }
}
//end


// tab Trainbot start
async function trainBot() {
    const symbol = document.getElementById("trainSymbol").value.trim().toUpperCase().replace(/[-_]/g, '/');
    const timeframes = Array.from(document.getElementById("trainTimeframes").selectedOptions).map(opt => opt.value);
    const lookBack = parseInt(document.getElementById("trainLookBack").value);
    
    if (!symbol || timeframes.length === 0) {
        showAlert("trainAlert", "Select symbol and at least one timeframe", "danger");
        return;
    }
    
    showAlert("trainAlert", "Training model...", "info");
    try {
        const res = await fetch(API + "/train_bot", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ symbol, timeframes, look_back: lookBack })
        });
        const json = await res.json();
        if (json.success) {
            showAlert("trainAlert", json.message, "success");
        } else {
            showAlert("trainAlert", json.error, "danger");
        }
    } catch (e) {
        showAlert("trainAlert", "Error: " + e.message, "danger");
    }
}
// end


// tab Predict Candle Start
async function predictCandle() {
    const symbol = document.getElementById("predictSymbol").value.trim().toUpperCase().replace(/[-_]/g, '/');
    const timeframe = document.getElementById("predictTimeframe").value;
    const lookBack = parseInt(document.getElementById("predictLookBack").value);
    const expander = parseFloat(document.getElementById("predictExpander").value);
    
    if (!symbol) {
        showAlert("predictAlert", "Select symbol", "danger");
        return;
    }
    
    showAlert("predictAlert", "Predicting next candle...", "info");
    try {
        const res = await fetch(API + "/predict_candle", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ symbol, timeframe, look_back: lookBack, expander })
        });
        const json = await res.json();
        if (json.success) {
            showAlert("predictAlert", "Prediction ready", "success");
            displayPrediction(json.prediction);
        } else {
            showAlert("predictAlert", json.error, "danger");
        }
    } catch (e) {
        showAlert("predictAlert", "Error: " + e.message, "danger");
    }
}




function displayPrediction(pred) {
    const container = document.getElementById("predictResults");
    
    // Determine signal class based on bias and strength
    let signalClass = 'signal-neutral';
    let signalBadge = 'secondary';
    if (pred.bias === 'bullish' && pred.strength === 'strong') {
        signalClass = 'signal-strong-bullish';
        signalBadge = 'primary';
    } else if (pred.bias === 'bullish') {
        signalClass = 'signal-bullish';
        signalBadge = 'success';
    } else if (pred.bias === 'bearish') {
        signalClass = 'signal-bearish';
        signalBadge = 'danger';
    }
    
    // Risk level color
    let riskClass = 'info';
    if (pred.risk_level === 'HIGH') riskClass = 'danger';
    else if (pred.risk_level === 'MEDIUM') riskClass = 'warning';
    else if (pred.risk_level === 'LOW') riskClass = 'success';
    
    // Trend alignment badge
    let trendBadge = 'secondary';
    if (pred.trend === 'bullish') trendBadge = 'success';
    else if (pred.trend === 'bearish') trendBadge = 'danger';
    else if (pred.trend === 'mixed') trendBadge = 'warning';
    
    // Build top reasons list
    let reasonsList = '';
    if (pred.top_reasons && pred.top_reasons.length > 0) {
        reasonsList = pred.top_reasons.map(r => `<li>${r}</li>`).join('');
    }
    
    // Build volume signals
    let volumeSignals = '';
    if (pred.volume_signals && pred.volume_signals.length > 0) {
        volumeSignals = pred.volume_signals.map(v => `<span class="badge bg-info me-1">${v}</span>`).join('');
    }
    
    // Build divergence signals
    let divergenceSignals = '';
    if (pred.divergence_signals && pred.divergence_signals.length > 0) {
        divergenceSignals = pred.divergence_signals.map(d => `<span class="badge bg-warning text-dark me-1">${d}</span>`).join('');
    }
    
    container.innerHTML = `
        <div class="row">
            <!-- Main Signal Card -->
            <div class="col-lg-6 mb-3">
                <div class="card signal-card ${pred.bias || 'neutral'}">
                    <div class="card-header">
                        <h5 class="mb-0">
                            <span class="${signalClass}">${pred.signal || pred.label}</span>
                            <span class="badge bg-${signalBadge} float-end">${pred.strength ? pred.strength.toUpperCase() : ''}</span>
                        </h5>
                    </div>
                    <div class="card-body">
                        <div class="row mb-3">
                            <div class="col-6">
                                <div class="text-muted small">SIGNAL SCORE</div>
                                <div class="progress mb-2" style="height: 25px;">
                                    <div class="progress-bar bg-${signalBadge}" role="progressbar" 
                                         style="width: ${pred.score}%;" 
                                         aria-valuenow="${pred.score}" aria-valuemin="0" aria-valuemax="100">
                                        ${pred.score}%
                                    </div>
                                </div>
                            </div>
                            <div class="col-6">
                                <div class="text-muted small">CONFIDENCE</div>
                                <div class="progress mb-2" style="height: 25px;">
                                    <div class="progress-bar bg-info" role="progressbar" 
                                         style="width: ${pred.confidence}%;" 
                                         aria-valuenow="${pred.confidence}" aria-valuemin="0" aria-valuemax="100">
                                        ${pred.confidence}%
                                    </div>
                                </div>
                            </div>
                        </div>
                        
                        <div class="row mb-2">
                            <div class="col-6">
                                <strong>Current Price:</strong><br>
                                <span class="fs-4">${pred.price ? pred.price.toFixed(4) : 'N/A'}</span>
                            </div>
                            <div class="col-6">
                                <strong>Trend Alignment:</strong><br>
                                <span class="badge bg-${trendBadge} fs-6">${pred.trend || 'N/A'}</span>
                            </div>
                        </div>
                        
                        ${pred.volatility_state ? `
                        <div class="mt-2">
                            <strong>Volatility State:</strong> 
                            <span class="badge ${pred.volatility_state === 'high' ? 'bg-danger' : pred.volatility_state === 'low' ? 'bg-success' : 'bg-secondary'}">
                                ${pred.volatility_state.toUpperCase()}
                            </span>
                        </div>
                        ` : ''}
                        
                        ${pred.momentum_score !== undefined ? `
                        <div class="mt-2">
                            <strong>Momentum Score:</strong> 
                            <span class="${pred.momentum_score > 0 ? 'text-success' : 'text-danger'} fw-bold">
                                ${(pred.momentum_score * 100).toFixed(1)}%
                            </span>
                        </div>
                        ` : ''}
                    </div>
                </div>
            </div>
            
            <!-- Key Levels Card -->
            <div class="col-lg-6 mb-3">
                <div class="card">
                    <div class="card-header bg-primary text-white">
                        <h6 class="mb-0">Key Support & Resistance Levels</h6>
                    </div>
                    <div class="card-body">
                        ${pred.key_levels ? `
                        <table class="table table-sm table-borderless mb-0">
                            <tr>
                                <td><strong>Resistance:</strong></td>
                                <td class="text-end text-danger fw-bold">${pred.key_levels.resistance ? pred.key_levels.resistance.toFixed(4) : 'N/A'}</td>
                            </tr>
                            <tr>
                                <td><strong>Current Price:</strong></td>
                                <td class="text-end fw-bold">${pred.price ? pred.price.toFixed(4) : 'N/A'}</td>
                            </tr>
                            <tr>
                                <td><strong>EMA 20:</strong></td>
                                <td class="text-end text-primary">${pred.key_levels.ema20 ? pred.key_levels.ema20.toFixed(4) : 'N/A'}</td>
                            </tr>
                            <tr>
                                <td><strong>Support:</strong></td>
                                <td class="text-end text-success fw-bold">${pred.key_levels.support ? pred.key_levels.support.toFixed(4) : 'N/A'}</td>
                            </tr>
                        </table>
                        ` : '<p class="text-muted">No level data available</p>'}
                        
                        ${pred.volume_status ? `
                        <div class="mt-3 pt-3 border-top">
                            <strong>Volume Status:</strong><br>
                            <span class="badge bg-info">${pred.volume_status}</span>
                        </div>
                        ` : ''}
                    </div>
                </div>
            </div>
        </div>
        
        <!-- Risk Assessment -->
        ${pred.risk_level ? `
        <div class="card mb-3">
            <div class="card-header bg-${riskClass} text-white">
                <h6 class="mb-0">
                    Risk Assessment: <strong>${pred.risk_level}</strong>
                    ${pred.risk_score !== undefined ? `<span class="float-end">Score: ${pred.risk_score}</span>` : ''}
                </h6>
            </div>
            ${pred.risk_factors && pred.risk_factors.length > 0 ? `
            <div class="card-body">
                <ul class="mb-0">
                    ${pred.risk_factors.map(f => `<li>${f}</li>`).join('')}
                </ul>
                ${pred.recommended_position_size !== undefined ? `
                <div class="mt-3 p-2 bg-light rounded">
                    <strong>Recommended Position Size:</strong> 
                    <span class="badge bg-primary">${(pred.recommended_position_size * 100).toFixed(0)}%</span>
                </div>
                ` : ''}
            </div>
            ` : ''}
        </div>
        ` : ''}
        
        <!-- Top Reasons -->
        ${reasonsList ? `
        <div class="card mb-3">
            <div class="card-header">
                <h6 class="mb-0">Top Analysis Reasons</h6>
            </div>
            <div class="card-body">
                <ul class="mb-0">${reasonsList}</ul>
            </div>
        </div>
        ` : ''}
        
        <!-- Volume & Divergence Signals -->
        <div class="row">
            ${volumeSignals ? `
            <div class="col-md-6 mb-3">
                <div class="card">
                    <div class="card-header">
                        <h6 class="mb-0">Volume Signals</h6>
                    </div>
                    <div class="card-body">
                        ${volumeSignals}
                    </div>
                </div>
            </div>
            ` : ''}
            
            ${divergenceSignals ? `
            <div class="col-md-6 mb-3">
                <div class="card">
                    <div class="card-header">
                        <h6 class="mb-0">Divergence Signals</h6>
                    </div>
                    <div class="card-body">
                        ${divergenceSignals}
                    </div>
                </div>
            </div>
            ` : ''}
        </div>
        
        <!-- Original Prediction Data (if exists) -->
        ${pred.pct_close !== undefined ? `
        <div class="card">
            <div class="card-header">
                <h6 class="mb-0">Price Prediction Details</h6>
            </div>
            <div class="card-body">
                <p><strong>% Close Change:</strong> ${pred.pct_close.toFixed(2)}% (Bounds: ${pred.close_low.toFixed(2)}% to ${pred.close_high.toFixed(2)}%)</p>
                <p><strong>% High Change:</strong> ${pred.pct_high.toFixed(2)}% (Bounds: ${pred.high_low.toFixed(2)}% to ${pred.high_high.toFixed(2)}%)</p>
                <p><strong>% Low Change:</strong> ${pred.pct_low.toFixed(2)}% (Bounds: ${pred.low_low.toFixed(2)}% to ${pred.low_high.toFixed(2)}%)</p>
                <small>Based on ${pred.matches} historical matches.</small>
            </div>
        </div>
        ` : ''}
    `;
}
// end



// tab System Sync Binance Pairs start
async function syncBinanceSymbols() {
    showAlert("symbolSyncAlert", "Syncing Binance symbols...", "info");
    try {
        const res = await fetch(API + "/sync_binance_symbols", { method: "POST" });
        const json = await res.json();
        if (!json.success) {
            showAlert("symbolSyncAlert", json.error || "Sync failed");
            return;
        }
        document.getElementById("syncTotal").innerText = json.total_markets;
        document.getElementById("syncExisting").innerText = json.already_existing;
        document.getElementById("syncNew").innerText = json.newly_added;
        showAlert("symbolSyncAlert", `Sync complete. ${json.newly_added} new symbols added.`, "success");
    } catch (e) {
        showAlert("symbolSyncAlert", "Error: " + e.message);
    }
}
// end



// tab Symbols fetched from DB start
async function searchSymbols() {
    const q = document.getElementById("symbolSearch").value.trim();
    showAlert("symbolsAlert", "Searching symbols...", "info");
    try {
        const res = await fetch(`${API}/search_symbols?q=${encodeURIComponent(q)}`);
        const json = await res.json();
        if (!json.success) {
            showAlert("symbolsAlert", "Search failed");
            return;
        }
        const tbody = document.getElementById("symbolsBody");
        tbody.innerHTML = "";
        json.data.forEach((r, i) => {
            const tr = document.createElement("tr");
            tr.innerHTML = `
                <td>${i + 1}</td>
                <td><strong>${r.symbol}</strong></td>
                <td>${r.base || ""}</td>
                <td>${r.quote || ""}</td>
                <td>${r.active ? "Yes" : "No"}</td>
                <td>${r.created_at || ""}</td>
            `;
            tbody.appendChild(tr);
        });
        showAlert("symbolsAlert", `Loaded ${json.data.length} symbols`, "success");
    } catch (e) {
        showAlert("symbolsAlert", "Error: " + e.message);
    }
}
    // Export excel funtion start
function exportSymbolsExcel() {
    const q = document.getElementById("symbolSearch").value.trim();
    const url = `${API}/export_symbols_excel?q=${encodeURIComponent(q)}`;
    window.open(url, "_blank");
}
// End


function showAlert(id, msg, type = "danger") {
    const alertDiv = document.getElementById(id);
    if (alertDiv) {
        alertDiv.innerHTML = `
            <div class="alert alert-${type} alert-dismissible fade show">
                ${msg}
                <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
            </div>`;
    }
}

// Auto-load gainers/losers on tab open
document.querySelectorAll('#mainTabs a').forEach(tab => {
    tab.addEventListener('shown.bs.tab', e => {
        const href = e.target.getAttribute('href');
        if (href === '#gainers') loadGainers();
        if (href === '#losers') loadLosers();
        if (href === '#orderbook') updateExchangeStatus();
    });
});

// end





// tab Orde Book (Live) start

// === EXCHANGE CHECKBOX FUNCTIONS ===
function toggleAllExchanges() {
    const allCheckbox = document.getElementById("exchangeAll");
    const exchangeCheckboxes = document.querySelectorAll(".exchange-checkbox");
    
    exchangeCheckboxes.forEach(checkbox => {
        checkbox.checked = allCheckbox.checked;
    });
    
    updateExchangeStatus();
    updateRealTime();
}

function updateExchangeSelection() {
    const exchangeCheckboxes = document.querySelectorAll(".exchange-checkbox");
    const allCheckbox = document.getElementById("exchangeAll");
    
    // Check if all exchange checkboxes are checked
    let allChecked = true;
    exchangeCheckboxes.forEach(checkbox => {
        if (!checkbox.checked) allChecked = false;
    });
    
    allCheckbox.checked = allChecked;
    updateExchangeStatus();
    updateRealTime();
}

function updateExchangeStatus() {
    const exchangeCheckboxes = document.querySelectorAll(".exchange-checkbox:checked");
    const exchangeNames = Array.from(exchangeCheckboxes).map(cb => {
        const value = cb.value;
        // Format exchange names nicely
        const namesMap = {
            'binance': 'Binance',
            'bybit': 'Bybit',
            'okx': 'OKX',
            'gateio': 'Gate.io',
            'kucoin': 'KuCoin',
            'huobi': 'Huobi',
            'kraken': 'Kraken',
            'bitget': 'Bitget',
            'mexc': 'MEXC',
            'coinbase': 'Coinbase'
        };
        return namesMap[value] || value.charAt(0).toUpperCase() + value.slice(1);
    });
    
    const statusElement = document.getElementById("exchangeStatus");
    if (exchangeNames.length === 0) {
        statusElement.innerHTML = '<small class="text-danger">No exchanges selected. Please select at least one exchange.</small>';
    } else {
        statusElement.innerHTML = `<small>Selected: ${exchangeNames.join(', ')}</small>`;
    }
}

function getSelectedExchanges() {
    const exchangeCheckboxes = document.querySelectorAll(".exchange-checkbox:checked");
    return Array.from(exchangeCheckboxes).map(cb => cb.value);
}

// End


// tab Pattern and Volume Scan Start

// === BINANCE ALL PAIRS SCANNER FUNCTIONS ===
let scanLog = [];
let lastScanResults = null;

async function updateBinancePairs() {
    const spinner = document.getElementById("updatePairsSpinner");
    const button = document.getElementById("updatePairsBtn");
    
    // Show loading state
    spinner.classList.remove("d-none");
    button.disabled = true;
    
    try {
        const res = await fetch(API + "/update_binance_pairs", {
            method: "POST",
            headers: { "Content-Type": "application/json" }
        });
        
        const data = await res.json();
        
        if (data.success) {
            showStatus("pairsUpdateStatus", 
                `✅ Updated ${data.spot_count} spot and ${data.futures_count} futures pairs`, 
                "success");
            
            // Log
            addToScanLog({
                time: new Date().toLocaleTimeString(),
                symbol: "ALL",
                status: "SUCCESS",
                details: `Updated ${data.spot_count + data.futures_count} pairs`
            });
        } else {
            showStatus("pairsUpdateStatus", `❌ Error: ${data.error}`, "danger");
        }
        
    } catch (error) {
        console.error("Update error:", error);
        showStatus("pairsUpdateStatus", `❌ Connection error: ${error.message}`, "danger");
    } finally {
        // Hide loading state
        spinner.classList.add("d-none");
        button.disabled = false;
    }
}

async function getBinancePairsStatus() {
    try {
        const res = await fetch(API + "/get_binance_pairs?limit=5");
        const data = await res.json();
        
        if (data.success) {
            showStatus("pairsUpdateStatus", 
                `📊 Database has ${data.count} active pairs`, 
                "info");
        }
    } catch (error) {
        console.error("Status check error:", error);
    }
}


async function scanAllPairs() {
    const spinner = document.getElementById("scanAllSpinner");
    const button = document.getElementById("scanAllBtn");
    
    // Show loading state
    spinner.classList.remove("d-none");
    button.disabled = true;
    
    try {
        const pairType = document.getElementById("scanPairType").value;
        const timeframe = document.getElementById("scanTimeframe").value;
        const volumeThreshold = parseFloat(document.getElementById("volumeThreshold").value);
        const maxPairs = parseInt(document.getElementById("maxPairs").value);
        const quoteAsset = document.getElementById("quoteAsset").value;
        const delayMs = parseInt(document.getElementById("scanDelay").value);
        
        const res = await fetch(API + "/scan_all_pairs", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                timeframe: timeframe,
                pair_type: pairType,
                quote_asset: quoteAsset || "",
                max_pairs: maxPairs,
                delay_ms: delayMs
            })
        });
        
        const data = await res.json();
        
        if (data.success) {
            // Store results
            lastScanResults = data;
            
            // Update statistics
            document.getElementById("totalScanned").textContent = data.scanned_pairs;
            document.getElementById("volumeAlerts").textContent = data.volume_alerts;
            document.getElementById("patternAlerts").textContent = data.pattern_alerts;
            
            // Update dashboard stats
            document.getElementById("statTotalScanned").textContent = data.scanned_pairs;
            document.getElementById("statVolumeSpikes").textContent = data.volume_alerts;
            document.getElementById("statPatternsFound").textContent = data.pattern_alerts;
            document.getElementById("statSuccessRate").textContent = 
                `${Math.round((data.successful_scans / data.scanned_pairs) * 100)}%`;
            
            // Show/hide alerts sections
            const volumeSection = document.getElementById("volumeAlertsSection");
            const patternSection = document.getElementById("patternAlertsSection");
            
            if (data.volume_alerts > 0) {
                volumeSection.classList.remove("d-none");
                updateVolumeAlerts(data.volume_alerts_list);
            } else {
                volumeSection.classList.add("d-none");
            }
            
            if (data.pattern_alerts > 0) {
                patternSection.classList.remove("d-none");
                updatePatternAlerts(data.pattern_alerts_list);
            } else {
                patternSection.classList.add("d-none");
            }
            
            // Update results table
            updateScanResultsTable(data.results);
            
            // Log success
            addToScanLog({
                time: new Date().toLocaleTimeString(),
                symbol: "SCAN",
                status: "COMPLETED",
                volumeRatio: "-",
                pattern: "-",
                details: `Scanned ${data.scanned_pairs} pairs, found ${data.volume_alerts} volume spikes`
            });
            
            showStatus("continuousScanStatus", 
                `✅ Scan completed: ${data.successful_scans}/${data.scanned_pairs} successful`, 
                "success");
                
        } else {
            showStatus("continuousScanStatus", `❌ Scan failed: ${data.error}`, "danger");
        }
        
    } catch (error) {
        console.error("Scan error:", error);
        showStatus("continuousScanStatus", `❌ Connection error: ${error.message}`, "danger");
    } finally {
        // Hide loading state
        spinner.classList.add("d-none");
        button.disabled = false;
    }
}

function updateVolumeAlerts(alerts) {
    const tbody = document.getElementById("volumeAlertsBody");
    tbody.innerHTML = '';
    
    alerts.forEach(alert => {
        const row = document.createElement("tr");
        row.innerHTML = `
            <td>
                <strong>${alert.symbol}</strong>
                <span class="badge ${alert.pair_type === 'spot' ? 'bg-info' : 'bg-warning'} ms-1">
                    ${alert.pair_type}
                </span>
            </td>
            <td>${alert.pair_type}</td>
            <td class="text-success fw-bold">${alert.volume_ratio.toFixed(2)}x</td>
            <td>${formatVolume(alert.current_volume)}</td>
            <td>${alert.timeframe}</td>
            <td>
                <button class="btn btn-sm btn-outline-primary" onclick="analyzeSymbol('${alert.symbol}', '${alert.pair_type}')">
                    Analyze
                </button>
            </td>
        `;
        tbody.appendChild(row);
    });
}


function updatePatternAlerts(alerts) {
    const tbody = document.getElementById("patternAlertsBody");
    tbody.innerHTML = '';
    
    alerts.forEach(alert => {
        const row = document.createElement("tr");
        const priceChange = alert.price_change || 0;
        const priceClass = priceChange > 0 ? "text-success" : "text-danger";
        
        row.innerHTML = `
            <td>
                <strong>${alert.symbol}</strong>
                <span class="badge ${alert.pair_type === 'spot' ? 'bg-info' : 'bg-warning'} ms-1">
                    ${alert.pair_type}
                </span>
            </td>
            <td>${alert.pair_type}</td>
            <td><span class="badge bg-warning text-dark">${alert.pattern}</span></td>
            <td class="${priceClass}">${priceChange > 0 ? '+' : ''}${priceChange.toFixed(2)}%</td>
            <td>${alert.current_price?.toFixed(6) || 'N/A'}</td>
            <td>
                <button class="btn btn-sm btn-outline-primary" onclick="analyzeSymbol('${alert.symbol}', '${alert.pair_type}')">
                    Analyze
                </button>
            </td>
        `;
        tbody.appendChild(row);
    });
}


function updateScanResultsTable(results) {
    const tbody = document.getElementById("scanResultsBody");
    
    if (!results || results.length === 0) {
        tbody.innerHTML = `
            <tr>
                <td colspan="9" class="text-center text-muted">
                    No matching symbols found. Try adjusting your criteria.
                </td>
            </tr>
        `;
        return;
    }
    
    tbody.innerHTML = '';
    
    results.forEach((result, index) => {
        // Determine volume ratio color
        let volumeRatioClass = "text-muted";
        if (result.volume_ratio >= 3) {
            volumeRatioClass = "text-success fw-bold";
        } else if (result.volume_ratio >= 2) {
            volumeRatioClass = "text-warning";
        }
        
        // Determine price change color
        const priceChange = result.price_change || 0;
        let priceChangeClass = "text-muted";
        if (priceChange > 0) {
            priceChangeClass = "text-success";
        } else if (priceChange < 0) {
            priceChangeClass = "text-danger";
        }
        
        // Format patterns
        let patternsHtml = "None";
        if (result.pattern) {
            patternsHtml = `<span class="badge bg-warning text-dark">${result.pattern}</span>`;
        }
        
        const row = document.createElement("tr");
        row.innerHTML = `
            <td>${index + 1}</td>
            <td>
                <strong>${result.symbol}</strong>
                <span class="badge ${result.pair_type === 'spot' ? 'bg-info' : 'bg-warning'} ms-1">
                    ${result.pair_type}
                </span>
            </td>
            <td>${result.pair_type}</td>
            <td>${result.current_price?.toFixed(6) || 'N/A'}</td>
            <td class="${priceChangeClass}">
                ${priceChange > 0 ? '+' : ''}${priceChange.toFixed(2)}%
            </td>
            <td class="${volumeRatioClass}">
                ${result.volume_ratio?.toFixed(2) || 'N/A'}x
            </td>
            <td>${patternsHtml}</td>
            <td>
                <span class="badge ${result.volume_ratio >= 2 ? 'bg-success' : result.volume_ratio >= 1.5 ? 'bg-warning' : 'bg-secondary'}">
                    ${result.volume_ratio >= 2 ? 'SPIKE' : result.volume_ratio >= 1.5 ? 'HIGH' : 'NORMAL'}
                </span>
            </td>
            <td>
                <button class="btn btn-sm btn-primary" onclick="analyzeSymbol('${result.symbol}', '${result.pair_type}')">
                    Analyze
                </button>
            </td>
        `;
        tbody.appendChild(row);
    });
}


function addToScanLog(entry) {
    const tbody = document.getElementById("scanLogBody");
    
    // Create new row
    const row = document.createElement("tr");
    
    // Determine status badge
    let statusBadge = "bg-secondary";
    if (entry.status === "SUCCESS" || entry.status === "COMPLETED") {
        statusBadge = "bg-success";
    } else if (entry.status === "ERROR") {
        statusBadge = "bg-danger";
    }
    
    row.innerHTML = `
        <td>${entry.time}</td>
        <td><small>${entry.symbol}</small></td>
        <td><span class="badge ${statusBadge}">${entry.status}</span></td>
        <td>${entry.volumeRatio || "-"}</td>
        <td>${entry.pattern || "-"}</td>
        <td><small>${entry.details}</small></td>
    `;
    
    // Insert at top
    if (tbody.firstChild && tbody.firstChild.textContent.includes('No scan data')) {
        tbody.innerHTML = '';
    }
    tbody.insertBefore(row, tbody.firstChild);
    
    // Keep only last 15 entries
    const rows = tbody.getElementsByTagName('tr');
    if (rows.length > 15) {
        tbody.removeChild(rows[rows.length - 1]);
    }
    
    // Add to memory log
    scanLog.unshift(entry);
    if (scanLog.length > 50) {
        scanLog.pop();
    }
}


async function analyzeSymbol() {
    const symbol = document.getElementById("signalSymbol").value.trim();
    const timeframe = document.getElementById("signalTimeframe").value;
    
    if (!symbol) {
        showAlert("signalAlert", "Please enter a symbol", "danger");
        return;
    }
    
    showAlert("signalAlert", `Analyzing ${symbol} ${timeframe}...`, "info");
    
    try {
        const res = await fetch(API + "/analyze_symbol", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ 
                symbol: symbol.toUpperCase().replace(/[-_]/g, '/'), 
                timeframe: timeframe 
            })
        });
        
        const json = await res.json();
        
        if (!json.success) {
            showAlert("signalAlert", json.error || "Failed to analyze symbol", "danger");
            return;
        }
        
        // Safely handle the response
        let cls = "signal-neutral";
        const signalText = json.signal || "NEUTRAL";
        
        if (signalText.includes("STRONG_BULLISH") || signalText.includes("BULLISH")) {
            cls = signalText.includes("STRONG") ? "signal-strong-bullish" : "signal-bullish";
        } else if (signalText.includes("STRONG_BEARISH") || signalText.includes("BEARISH")) {
            cls = signalText.includes("STRONG") ? "signal-bearish" : "signal-bearish";
        } else if (signalText.includes("WATCH_")) {
            cls = "signal-watch";
        }
        
        const d = json;
        const ind = d.indicators || {};
        const c = d.last_candle || {};
        
        const html = `
            <div class="card">
                <div class="card-header">
                    <strong>${d.symbol || symbol}</strong> - ${d.timeframe || timeframe} Analysis
                </div>
                <div class="card-body">
                    <div class="row">
                        <div class="col-md-6">
                            <p><strong>Last Candle:</strong> ${c.time_utc || 'N/A'}</p>
                            <table class="table table-sm">
                                <tr>
                                    <td>Open:</td><td>${c.open ? parseFloat(c.open).toFixed(4) : 'N/A'}</td>
                                    <td>High:</td><td>${c.high ? parseFloat(c.high).toFixed(4) : 'N/A'}</td>
                                </tr>
                                <tr>
                                    <td>Low:</td><td>${c.low ? parseFloat(c.low).toFixed(4) : 'N/A'}</td>
                                    <td>Close:</td><td>${c.close ? parseFloat(c.close).toFixed(4) : 'N/A'}</td>
                                </tr>
                                <tr>
                                    <td>Volume:</td><td colspan="3">${c.volume ? parseInt(c.volume).toLocaleString() : 'N/A'}</td>
                                </tr>
                            </table>
                        </div>
                        <div class="col-md-6">
                            <p><strong>Indicators:</strong></p>
                            <table class="table table-sm">
                                <tr>
                                    <td>RSI(14):</td>
                                    <td class="${ind.rsi < 30 ? 'text-success' : ind.rsi > 70 ? 'text-danger' : ''}">
                                        ${ind.rsi ? ind.rsi.toFixed(2) : "N/A"}
                                    </td>
                                </tr>
                                <tr>
                                    <td>MACD:</td><td>${ind.macd ? ind.macd.toFixed(4) : "N/A"}</td>
                                </tr>
                                <tr>
                                    <td>Signal:</td><td>${ind.macd_signal ? ind.macd_signal.toFixed(4) : "N/A"}</td>
                                </tr>
                                <tr>
                                    <td>EMA20:</td><td>${ind.ema20 ? ind.ema20.toFixed(4) : "N/A"}</td>
                                </tr>
                                <tr>
                                    <td>EMA50:</td><td>${ind.ema50 ? ind.ema50.toFixed(4) : "N/A"}</td>
                                </tr>
                            </table>
                        </div>
                    </div>
                    
                    <div class="mt-3 text-center">
                        <div class="${cls} p-3 rounded">
                            <h4>${d.signal || 'NEUTRAL'}</h4>
                            <p class="mb-1">Bias: ${d.bias || 'neutral'}</p>
                            <p class="mb-1">Score: ${d.score || 0}/100</p>
                            ${d.reasons && d.reasons.length > 0 ? 
                                `<p class="mb-0"><small>${d.reasons.join(', ')}</small></p>` : 
                                ''}
                        </div>
                    </div>
                </div>
            </div>
        `;
        
        document.getElementById("signalDetails").innerHTML = html;
        showAlert("signalAlert", "Analysis completed", "success");
        
    } catch (e) {
        console.error("Analyze symbol error:", e);
        showAlert("signalAlert", "Error: " + e.message, "danger");
    }
}


async function startContinuousScan() {
    try {
        const interval = parseInt(document.getElementById("scanInterval").value);
        
        const res = await fetch(API + "/continuous_scan", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                interval: interval,
                max_pairs: 50,
                quote_asset: document.getElementById("quoteAsset").value
            })
        });
        
        const data = await res.json();
        
        if (data.success) {
            showStatus("continuousScanStatus", 
                `✅ Continuous scan started. Scanning every ${interval} minutes.`, 
                "success");
            
            // Update button states
            document.getElementById("continuousScanBtn").disabled = true;
            document.getElementById("stopScanBtn").disabled = false;
            
            // Start periodic status checks
            startStatusMonitoring();
            
        } else {
            showStatus("continuousScanStatus", `❌ Error: ${data.error}`, "danger");
        }
        
    } catch (error) {
        console.error("Start scan error:", error);
        showStatus("continuousScanStatus", `❌ Connection error: ${error.message}`, "danger");
    }
}


async function stopContinuousScan() {
    try {
        const res = await fetch(API + "/stop_continuous_scan", {
            method: "POST",
            headers: { "Content-Type": "application/json" }
        });
        
        const data = await res.json();
        
        if (data.success) {
            showStatus("continuousScanStatus", "⏹️ Continuous scan stopped", "info");
            
            // Update button states
            document.getElementById("continuousScanBtn").disabled = false;
            document.getElementById("stopScanBtn").disabled = true;
            
        }
        
    } catch (error) {
        console.error("Stop scan error:", error);
    }
}


async function getScanStatus() {
    try {
        const res = await fetch(API + "/get_scan_status");
        const data = await res.json();
        
        if (data.success) {
            if (data.active) {
                const nextScan = new Date(data.config.next_scan);
                const now = new Date();
                const minutesLeft = Math.round((nextScan - now) / (1000 * 60));
                
                showStatus("continuousScanStatus", 
                    `🔄 Scan active. Next scan in ${minutesLeft} minutes.`, 
                    "info");
            }
        }
    } catch (error) {
        console.error("Status check error:", error);
    }
}

function startStatusMonitoring() {
    // Check status every 30 seconds
    if (window.statusInterval) {
        clearInterval(window.statusInterval);
    }
    
    window.statusInterval = setInterval(() => {
        getScanStatus();
    }, 30000);
}


function showStatus(elementId, message, type = "info") {
    const element = document.getElementById(elementId);
    if (element) {
        element.innerHTML = `
            <div class="alert alert-${type} alert-dismissible fade show">
                ${message}
                <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
            </div>
        `;
    }
}



function formatVolume(volume) {
    if (volume >= 1000000) {
        return (volume / 1000000).toFixed(2) + 'M';
    } else if (volume >= 1000) {
        return (volume / 1000).toFixed(2) + 'K';
    }
    return volume.toFixed(2);
}


// Auto-run database check when tab opens
document.querySelector('#mainTabs a[href="#patternScanner"]').addEventListener('shown.bs.tab', function() {
    // Check database status after a delay
    setTimeout(() => {
        getBinancePairsStatus();
    }, 1000);
});

// Stop monitoring when leaving tab
document.querySelector('#mainTabs a[href="#patternScanner"]').addEventListener('hide.bs.tab', function() {
    if (window.statusInterval) {
        clearInterval(window.statusInterval);
        window.statusInterval = null;
    }
});

// End