// Position type tracking
let liqPositionType = 'long';
let pnlPositionType = 'long';

// Toggle position type selection
function selectPosition(button, calculator) {
    const group = button.parentElement;
    const buttons = group.querySelectorAll('.toggle-btn');
    buttons.forEach(btn => btn.classList.remove('active'));
    button.classList.add('active');
    
    const value = button.dataset.value;
    if (calculator === 'liq') {
        liqPositionType = value;
    } else if (calculator === 'pnl') {
        pnlPositionType = value;
    }
}

// Fetch current price
async function fetchPrice() {
    const symbol = document.getElementById('priceSymbol').value.trim().toUpperCase();
    const resultDiv = document.getElementById('priceResult');
    
    if (!symbol) {
        resultDiv.innerHTML = '<div class="error">Please enter a symbol</div>';
        return;
    }
    
    resultDiv.innerHTML = '<div class="loading"></div>';
    
    try {
        const response = await fetch(`/api/price/${symbol}`);
        const data = await response.json();
        
        if (response.ok) {
            resultDiv.innerHTML = `
                <div class="price-display">${formatPrice(data.price)}</div>
                <div class="info-text">${data.symbol}</div>
            `;
        } else {
            resultDiv.innerHTML = `<div class="error">${data.error}</div>`;
        }
    } catch (error) {
        resultDiv.innerHTML = `<div class="error">Network error: ${error.message}</div>`;
    }
}

// Fetch funding rate
async function fetchFunding() {
    const symbol = document.getElementById('fundingSymbol').value.trim().toUpperCase();
    const resultDiv = document.getElementById('fundingResult');
    
    if (!symbol) {
        resultDiv.innerHTML = '<div class="error">Please enter a symbol</div>';
        return;
    }
    
    resultDiv.innerHTML = '<div class="loading"></div>';
    
    try {
        const response = await fetch(`/api/funding/${symbol}`);
        const data = await response.json();
        
        if (response.ok) {
            const rateClass = data.funding_rate >= 0 ? 'funding-positive' : 'funding-negative';
            const rateSymbol = data.funding_rate >= 0 ? '+' : '';
            
            resultDiv.innerHTML = `
                <div class="result-item">
                    <span class="result-label">Funding Rate</span>
                    <span class="result-value ${rateClass}">${rateSymbol}${data.funding_rate.toFixed(4)}%</span>
                </div>
                <div class="result-item">
                    <span class="result-label">Mark Price</span>
                    <span class="result-value">${formatPrice(data.mark_price)}</span>
                </div>
                <div class="result-item">
                    <span class="result-label">Next Funding</span>
                    <span class="result-value" style="font-size: 0.85rem;">${data.next_funding_time}</span>
                </div>
            `;
        } else {
            resultDiv.innerHTML = `<div class="error">${data.error}</div>`;
        }
    } catch (error) {
        resultDiv.innerHTML = `<div class="error">Network error: ${error.message}</div>`;
    }
}

// Calculate liquidation price
async function calculateLiquidation() {
    const entryPrice = parseFloat(document.getElementById('liqEntryPrice').value);
    const leverage = parseFloat(document.getElementById('liqLeverage').value);
    const resultDiv = document.getElementById('liqResult');
    
    if (!entryPrice || !leverage) {
        resultDiv.innerHTML = '<div class="error">Please fill in all fields</div>';
        return;
    }
    
    if (leverage < 1 || leverage > 125) {
        resultDiv.innerHTML = '<div class="error">Leverage must be between 1 and 125</div>';
        return;
    }
    
    resultDiv.innerHTML = '<div class="loading"></div>';
    
    try {
        const response = await fetch('/api/liquidation', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                entry_price: entryPrice,
                leverage: leverage,
                position_type: liqPositionType
            })
        });
        
        const data = await response.json();
        
        if (response.ok) {
            const distance = ((Math.abs(data.liquidation_price - data.entry_price) / data.entry_price) * 100).toFixed(2);
            const direction = liqPositionType === 'long' ? 'below' : 'above';
            
            resultDiv.innerHTML = `
                <div class="highlight-box">
                    <div class="result-item">
                        <span class="result-label">Entry Price</span>
                        <span class="result-value">${formatPrice(data.entry_price)}</span>
                    </div>
                    <div class="result-item">
                        <span class="result-label">Liquidation Price</span>
                        <span class="result-value" style="color: var(--accent-red);">${formatPrice(data.liquidation_price)}</span>
                    </div>
                    <div class="result-item">
                        <span class="result-label">Distance</span>
                        <span class="result-value">${distance}% ${direction}</span>
                    </div>
                    <div class="result-item">
                        <span class="result-label">Position</span>
                        <span class="result-value">${data.position_type.toUpperCase()} ${data.leverage}x</span>
                    </div>
                </div>
            `;
        } else {
            resultDiv.innerHTML = `<div class="error">${data.error}</div>`;
        }
    } catch (error) {
        resultDiv.innerHTML = `<div class="error">Network error: ${error.message}</div>`;
    }
}

// Calculate PNL
async function calculatePNL() {
    const entryPrice = parseFloat(document.getElementById('pnlEntryPrice').value);
    const exitPrice = parseFloat(document.getElementById('pnlExitPrice').value);
    const positionSize = parseFloat(document.getElementById('pnlPositionSize').value);
    const leverage = parseFloat(document.getElementById('pnlLeverage').value);
    const resultDiv = document.getElementById('pnlResult');
    
    if (!entryPrice || !exitPrice || !positionSize || !leverage) {
        resultDiv.innerHTML = '<div class="error">Please fill in all fields</div>';
        return;
    }
    
    if (leverage < 1 || leverage > 125) {
        resultDiv.innerHTML = '<div class="error">Leverage must be between 1 and 125</div>';
        return;
    }
    
    resultDiv.innerHTML = '<div class="loading"></div>';
    
    try {
        const response = await fetch('/api/pnl', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                entry_price: entryPrice,
                exit_price: exitPrice,
                position_size: positionSize,
                position_type: pnlPositionType,
                leverage: leverage
            })
        });
        
        const data = await response.json();
        
        if (response.ok) {
            const pnlClass = data.pnl >= 0 ? 'profit' : 'loss';
            const pnlSymbol = data.pnl >= 0 ? '+' : '';
            
            resultDiv.innerHTML = `
                <div class="stat-grid">
                    <div class="stat-item">
                        <div class="stat-value ${pnlClass}">${pnlSymbol}$${Math.abs(data.pnl).toFixed(2)}</div>
                        <div class="stat-label">P&L (USD)</div>
                    </div>
                    <div class="stat-item">
                        <div class="stat-value ${pnlClass}">${pnlSymbol}${data.roi.toFixed(2)}%</div>
                        <div class="stat-label">ROI</div>
                    </div>
                </div>
                <div class="result-item" style="margin-top: 1rem;">
                    <span class="result-label">Price Change</span>
                    <span class="result-value ${pnlClass}">${pnlSymbol}${data.pnl_percentage.toFixed(2)}%</span>
                </div>
                <div class="result-item">
                    <span class="result-label">Contracts</span>
                    <span class="result-value">${data.contracts.toFixed(8)}</span>
                </div>
                <div class="result-item">
                    <span class="result-label">Position</span>
                    <span class="result-value">${data.position_type.toUpperCase()} ${data.leverage}x</span>
                </div>
                <div class="result-item">
                    <span class="result-label">Entry → Exit</span>
                    <span class="result-value" style="font-size: 0.85rem;">${formatPrice(data.entry_price)} → ${formatPrice(data.exit_price)}</span>
                </div>
            `;
        } else {
            resultDiv.innerHTML = `<div class="error">${data.error}</div>`;
        }
    } catch (error) {
        resultDiv.innerHTML = `<div class="error">Network error: ${error.message}</div>`;
    }
}

// Format price for display
function formatPrice(price) {
    if (price >= 1000) {
        return price.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    } else if (price >= 1) {
        return price.toFixed(4);
    } else {
        return price.toFixed(8);
    }
}

// Allow Enter key to trigger actions
document.addEventListener('DOMContentLoaded', () => {
    document.getElementById('priceSymbol').addEventListener('keypress', (e) => {
        if (e.key === 'Enter') fetchPrice();
    });
    
    document.getElementById('fundingSymbol').addEventListener('keypress', (e) => {
        if (e.key === 'Enter') fetchFunding();
    });
});
