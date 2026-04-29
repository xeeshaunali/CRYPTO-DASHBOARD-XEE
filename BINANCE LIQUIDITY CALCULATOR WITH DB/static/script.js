// Position type and fee type tracking
let openPositionType = 'long';
let calcPositionType = 'long';
let feeType = 'taker';
let currentFundingRate = 0;

// Initialize on page load
document.addEventListener('DOMContentLoaded', () => {
    loadStats('daily');
    loadOpenPositions();
    
    // Auto-refresh stats every 30 seconds
    setInterval(() => loadStats(currentStatsTab), 30000);
    
    // Position select change handler
    document.getElementById('closePositionId').addEventListener('change', showPositionDetails);
});

let currentStatsTab = 'daily';

// Tab switching
function switchTab(tab) {
    document.querySelectorAll('.position-manager .tab').forEach(t => t.classList.remove('active'));
    document.querySelectorAll('.position-manager .tab-content').forEach(c => c.classList.remove('active'));
    
    event.target.classList.add('active');
    document.getElementById(tab + 'Tab').classList.add('active');
    
    if (tab === 'close') {
        loadOpenPositions();
    }
}

function switchHistoryTab(tab) {
    document.querySelectorAll('.history-card .tab').forEach(t => t.classList.remove('active'));
    document.querySelectorAll('.history-card .tab-content').forEach(c => c.classList.remove('active'));
    
    event.target.classList.add('active');
    
    if (tab === 'open') {
        document.getElementById('openPositionsTab').classList.add('active');
        loadOpenPositions();
    } else {
        document.getElementById('closedPositionsTab').classList.add('active');
        loadClosedPositions('all');
    }
}

// Position type selection
function selectPosition(button, context) {
    const group = button.parentElement;
    const buttons = group.querySelectorAll('.toggle-btn');
    buttons.forEach(btn => btn.classList.remove('active'));
    button.classList.add('active');
    
    const value = button.dataset.value;
    if (context === 'open') {
        openPositionType = value;
    } else if (context === 'calc') {
        calcPositionType = value;
    }
}

// Fee type selection
function selectFeeType(button) {
    const group = button.parentElement;
    const buttons = group.querySelectorAll('.toggle-btn');
    buttons.forEach(btn => btn.classList.remove('active'));
    button.classList.add('active');
    feeType = button.dataset.value;
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
            currentFundingRate = data.funding_rate_decimal;
            const rateClass = data.funding_rate >= 0 ? 'funding-positive' : 'funding-negative';
            const rateSymbol = data.funding_rate >= 0 ? '+' : '';
            
            resultDiv.innerHTML = `
                <div class="result-item">
                    <span class="result-label">Funding Rate</span>
                    <span class="result-value ${rateClass}">${rateSymbol}${data.funding_rate.toFixed(4)}%</span>
                </div>
                <div class="result-item">
                    <span class="result-label">Decimal (for calc)</span>
                    <span class="result-value">${data.funding_rate_decimal.toFixed(6)}</span>
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
            
            // Auto-fill funding rate in calculator
            document.getElementById('calcFundingRate').value = data.funding_rate_decimal.toFixed(6);
            document.getElementById('closeFundingRate').value = data.funding_rate_decimal.toFixed(6);
        } else {
            resultDiv.innerHTML = `<div class="error">${data.error}</div>`;
        }
    } catch (error) {
        resultDiv.innerHTML = `<div class="error">Network error: ${error.message}</div>`;
    }
}

// Calculate P&L with fees
async function calculatePNL() {
    const entryPrice = parseFloat(document.getElementById('calcEntryPrice').value);
    const exitPrice = parseFloat(document.getElementById('calcExitPrice').value);
    const positionSize = parseFloat(document.getElementById('calcPositionSize').value);
    const leverage = parseFloat(document.getElementById('calcLeverage').value);
    const holdingHours = parseFloat(document.getElementById('calcHoldingHours').value) || 0;
    const fundingRate = parseFloat(document.getElementById('calcFundingRate').value) || 0;
    const resultDiv = document.getElementById('calcResult');
    
    if (!entryPrice || !exitPrice || !positionSize || !leverage) {
        resultDiv.innerHTML = '<div class="error">Please fill in all required fields</div>';
        return;
    }
    
    resultDiv.innerHTML = '<div class="loading"></div>';
    
    try {
        const response = await fetch('/api/pnl', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                entry_price: entryPrice,
                exit_price: exitPrice,
                position_size: positionSize,
                position_type: calcPositionType,
                leverage: leverage,
                holding_hours: holdingHours,
                funding_rate: fundingRate,
                fee_type: feeType
            })
        });
        
        const data = await response.json();
        
        if (response.ok) {
            const pnlClass = data.net_pnl >= 0 ? 'profit' : 'loss';
            const pnlSymbol = data.net_pnl >= 0 ? '+' : '';
            
            resultDiv.innerHTML = `
                <div class="stat-grid">
                    <div class="stat-item">
                        <div class="stat-value ${pnlClass}">${pnlSymbol}$${Math.abs(data.net_pnl).toFixed(2)}</div>
                        <div class="stat-label">Net P&L</div>
                    </div>
                    <div class="stat-item">
                        <div class="stat-value ${pnlClass}">${pnlSymbol}${data.roi.toFixed(2)}%</div>
                        <div class="stat-label">ROI</div>
                    </div>
                </div>
                <div class="highlight-box" style="margin-top: 1rem;">
                    <div class="result-item">
                        <span class="result-label">Gross P&L</span>
                        <span class="result-value">$${data.gross_pnl.toFixed(2)}</span>
                    </div>
                    <div class="result-item">
                        <span class="result-label">Entry Fee (${feeType})</span>
                        <span class="result-value loss">-$${data.entry_fee.toFixed(2)}</span>
                    </div>
                    <div class="result-item">
                        <span class="result-label">Exit Fee (${feeType})</span>
                        <span class="result-value loss">-$${data.exit_fee.toFixed(2)}</span>
                    </div>
                    ${holdingHours > 0 ? `
                    <div class="result-item">
                        <span class="result-label">Funding Fees (${data.funding_payments} payments)</span>
                        <span class="result-value ${data.funding_fee >= 0 ? 'loss' : 'profit'}">
                            ${data.funding_fee >= 0 ? '-' : '+'}$${Math.abs(data.funding_fee).toFixed(2)}
                        </span>
                    </div>` : ''}
                    <div class="result-item">
                        <span class="result-label">Total Fees</span>
                        <span class="result-value loss">-$${data.total_fees.toFixed(2)}</span>
                    </div>
                    <div class="result-item">
                        <span class="result-label">Break-Even Price</span>
                        <span class="result-value">${formatPrice(data.breakeven_price)}</span>
                    </div>
                    <div class="result-item">
                        <span class="result-label">Contracts</span>
                        <span class="result-value">${data.contracts.toFixed(8)}</span>
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

// Open position
async function openPosition() {
    const symbol = document.getElementById('openSymbol').value.trim().toUpperCase();
    const entryPrice = parseFloat(document.getElementById('openEntryPrice').value);
    const positionSize = parseFloat(document.getElementById('openPositionSize').value);
    const leverage = parseFloat(document.getElementById('openLeverage').value);
    const notes = document.getElementById('openNotes').value.trim();
    const resultDiv = document.getElementById('openResult');
    
    if (!symbol || !entryPrice || !positionSize || !leverage) {
        resultDiv.innerHTML = '<div class="error">Please fill in all required fields</div>';
        return;
    }
    
    resultDiv.innerHTML = '<div class="loading"></div>';
    
    try {
        const response = await fetch('/api/position/open', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                symbol: symbol,
                position_type: openPositionType,
                entry_price: entryPrice,
                position_size: positionSize,
                leverage: leverage,
                notes: notes
            })
        });
        
        const data = await response.json();
        
        if (response.ok) {
            resultDiv.innerHTML = `
                <div class="success">${data.message}</div>
                <div class="highlight-box">
                    <div class="result-item">
                        <span class="result-label">Position ID</span>
                        <span class="result-value">#${data.position_id}</span>
                    </div>
                    <div class="result-item">
                        <span class="result-label">Liquidation Price</span>
                        <span class="result-value" style="color: var(--accent-red);">${formatPrice(data.liquidation_price)}</span>
                    </div>
                </div>
            `;
            
            // Clear form
            document.getElementById('openSymbol').value = '';
            document.getElementById('openEntryPrice').value = '';
            document.getElementById('openPositionSize').value = '';
            document.getElementById('openLeverage').value = '';
            document.getElementById('openNotes').value = '';
            
            // Refresh open positions list
            setTimeout(() => loadOpenPositions(), 500);
        } else {
            resultDiv.innerHTML = `<div class="error">${data.error}</div>`;
        }
    } catch (error) {
        resultDiv.innerHTML = `<div class="error">Network error: ${error.message}</div>`;
    }
}

// Close position
async function closePosition() {
    const positionId = document.getElementById('closePositionId').value;
    const exitPrice = parseFloat(document.getElementById('closeExitPrice').value);
    const fundingRate = parseFloat(document.getElementById('closeFundingRate').value) || 0;
    const resultDiv = document.getElementById('closeResult');
    
    if (!positionId || !exitPrice) {
        resultDiv.innerHTML = '<div class="error">Please select position and enter exit price</div>';
        return;
    }
    
    resultDiv.innerHTML = '<div class="loading"></div>';
    
    try {
        const response = await fetch(`/api/position/close/${positionId}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                exit_price: exitPrice,
                funding_rate: fundingRate
            })
        });
        
        const data = await response.json();
        
        if (response.ok) {
            const pnlClass = data.net_pnl >= 0 ? 'profit' : 'loss';
            const pnlSymbol = data.net_pnl >= 0 ? '+' : '';
            
            resultDiv.innerHTML = `
                <div class="success">${data.message}</div>
                <div class="stat-grid">
                    <div class="stat-item">
                        <div class="stat-value ${pnlClass}">${pnlSymbol}$${Math.abs(data.net_pnl).toFixed(2)}</div>
                        <div class="stat-label">Net P&L</div>
                    </div>
                    <div class="stat-item">
                        <div class="stat-value ${pnlClass}">${pnlSymbol}${data.roi.toFixed(2)}%</div>
                        <div class="stat-label">ROI</div>
                    </div>
                </div>
                <div class="highlight-box" style="margin-top: 1rem;">
                    <div class="result-item">
                        <span class="result-label">Holding Time</span>
                        <span class="result-value">${data.holding_hours.toFixed(2)} hours</span>
                    </div>
                    <div class="result-item">
                        <span class="result-label">Total Fees Paid</span>
                        <span class="result-value loss">-$${data.total_fees.toFixed(2)}</span>
                    </div>
                </div>
            `;
            
            // Clear form and refresh
            document.getElementById('closePositionId').value = '';
            document.getElementById('closeExitPrice').value = '';
            document.getElementById('positionDetails').style.display = 'none';
            
            setTimeout(() => {
                loadOpenPositions();
                loadStats(currentStatsTab);
            }, 1000);
        } else {
            resultDiv.innerHTML = `<div class="error">${data.error}</div>`;
        }
    } catch (error) {
        resultDiv.innerHTML = `<div class="error">Network error: ${error.message}</div>`;
    }
}

// Load open positions
async function loadOpenPositions() {
    try {
        const response = await fetch('/api/positions/open');
        const data = await response.json();
        
        const selectElement = document.getElementById('closePositionId');
        const listElement = document.getElementById('openPositionsList');
        
        if (data.positions && data.positions.length > 0) {
            // Update select dropdown
            selectElement.innerHTML = '<option value="">Select open position...</option>';
            data.positions.forEach(pos => {
                const option = document.createElement('option');
                option.value = pos.id;
                option.textContent = `#${pos.id} - ${pos.symbol} ${pos.position_type.toUpperCase()} ${pos.leverage}x @ ${formatPrice(pos.entry_price)}`;
                option.dataset.position = JSON.stringify(pos);
                selectElement.appendChild(option);
            });
            
            // Update positions list
            listElement.innerHTML = `
                <table class="position-table">
                    <thead>
                        <tr>
                            <th>ID</th>
                            <th>Symbol</th>
                            <th>Type</th>
                            <th>Entry</th>
                            <th>Size</th>
                            <th>Leverage</th>
                            <th>Liq Price</th>
                            <th>Opened</th>
                        </tr>
                    </thead>
                    <tbody>
                        ${data.positions.map(pos => `
                            <tr>
                                <td>#${pos.id}</td>
                                <td><strong>${pos.symbol}</strong></td>
                                <td><span class="position-badge badge-${pos.position_type}">${pos.position_type}</span></td>
                                <td>${formatPrice(pos.entry_price)}</td>
                                <td>$${pos.position_size.toFixed(2)}</td>
                                <td>${pos.leverage}x</td>
                                <td style="color: var(--accent-red);">${formatPrice(pos.liquidation_price)}</td>
                                <td>${new Date(pos.opened_at).toLocaleString()}</td>
                            </tr>
                        `).join('')}
                    </tbody>
                </table>
            `;
        } else {
            selectElement.innerHTML = '<option value="">No open positions</option>';
            listElement.innerHTML = '<div class="empty-state"><div class="empty-state-icon">📊</div><div class="empty-state-text">No open positions</div></div>';
        }
    } catch (error) {
        console.error('Error loading open positions:', error);
    }
}

// Load closed positions
async function loadClosedPositions(period) {
    const listElement = document.getElementById('closedPositionsList');
    listElement.innerHTML = '<div class="loading"></div>';
    
    try {
        const response = await fetch(`/api/positions/closed?period=${period}`);
        const data = await response.json();
        
        if (data.positions && data.positions.length > 0) {
            listElement.innerHTML = `
                <table class="position-table">
                    <thead>
                        <tr>
                            <th>ID</th>
                            <th>Symbol</th>
                            <th>Type</th>
                            <th>Entry/Exit</th>
                            <th>Size</th>
                            <th>Net P&L</th>
                            <th>ROI</th>
                            <th>Fees</th>
                            <th>Closed</th>
                        </tr>
                    </thead>
                    <tbody>
                        ${data.positions.map(pos => {
                            const pnlClass = pos.net_pnl >= 0 ? 'profit' : 'loss';
                            const totalFees = parseFloat(pos.entry_fee) + parseFloat(pos.exit_fee) + parseFloat(pos.funding_fee || 0);
                            return `
                                <tr>
                                    <td>#${pos.id}</td>
                                    <td><strong>${pos.symbol}</strong></td>
                                    <td><span class="position-badge badge-${pos.position_type}">${pos.position_type}</span></td>
                                    <td>${formatPrice(pos.entry_price)} → ${formatPrice(pos.exit_price)}</td>
                                    <td>$${parseFloat(pos.position_size).toFixed(2)}</td>
                                    <td class="${pnlClass}"><strong>${pos.net_pnl >= 0 ? '+' : ''}$${parseFloat(pos.net_pnl).toFixed(2)}</strong></td>
                                    <td class="${pnlClass}">${pos.roi >= 0 ? '+' : ''}${parseFloat(pos.roi).toFixed(2)}%</td>
                                    <td>$${totalFees.toFixed(2)}</td>
                                    <td>${new Date(pos.closed_at).toLocaleString()}</td>
                                </tr>
                            `;
                        }).join('')}
                    </tbody>
                </table>
            `;
        } else {
            listElement.innerHTML = '<div class="empty-state"><div class="empty-state-icon">📊</div><div class="empty-state-text">No closed positions for this period</div></div>';
        }
    } catch (error) {
        listElement.innerHTML = `<div class="error">Error loading positions: ${error.message}</div>`;
    }
}

// Load statistics
async function loadStats(period) {
    currentStatsTab = period;
    
    // Update active tab
    document.querySelectorAll('.stats-tab').forEach(tab => {
        tab.classList.toggle('active', tab.textContent.toLowerCase().includes(period) || 
                                       (period === 'alltime' && tab.textContent.toLowerCase().includes('all')));
    });
    
    const contentDiv = document.getElementById('statsContent');
    contentDiv.innerHTML = '<div class="loading"></div>';
    
    try {
        const response = await fetch('/api/statistics');
        const data = await response.json();
        
        const stats = data[period];
        const pnlClass = stats.total_pnl >= 0 ? 'positive' : 'negative';
        
        // Ensure win_rate is a number
        const winRate = parseFloat(stats.win_rate) || 0;
        const totalPnl = parseFloat(stats.total_pnl) || 0;
        const avgRoi = parseFloat(stats.avg_roi) || 0;
        const totalFees = parseFloat(stats.total_fees) || 0;
        
        contentDiv.innerHTML = `
            <div class="stat-card">
                <div class="stat-value ${pnlClass}">${totalPnl >= 0 ? '+' : ''}$${Math.abs(totalPnl).toFixed(2)}</div>
                <div class="stat-label">Total P&L</div>
            </div>
            <div class="stat-card">
                <div class="stat-value">${stats.total_trades || 0}</div>
                <div class="stat-label">Total Trades</div>
            </div>
            <div class="stat-card">
                <div class="stat-value positive">${stats.winning_trades || 0}</div>
                <div class="stat-label">Winning Trades</div>
            </div>
            <div class="stat-card">
                <div class="stat-value negative">${stats.losing_trades || 0}</div>
                <div class="stat-label">Losing Trades</div>
            </div>
            <div class="stat-card">
                <div class="stat-value">${winRate.toFixed(1)}%</div>
                <div class="stat-label">Win Rate</div>
            </div>
            <div class="stat-card">
                <div class="stat-value ${avgRoi >= 0 ? 'positive' : 'negative'}">
                    ${avgRoi >= 0 ? '+' : ''}${avgRoi.toFixed(2)}%
                </div>
                <div class="stat-label">Avg ROI</div>
            </div>
            <div class="stat-card">
                <div class="stat-value negative">$${totalFees.toFixed(2)}</div>
                <div class="stat-label">Total Fees</div>
            </div>
        `;
    } catch (error) {
        contentDiv.innerHTML = `<div class="error">Error loading statistics: ${error.message}</div>`;
    }
}

// Show position details when selected
function showPositionDetails() {
    const select = document.getElementById('closePositionId');
    const selectedOption = select.options[select.selectedIndex];
    const detailsDiv = document.getElementById('positionDetails');
    
    if (selectedOption.dataset.position) {
        const pos = JSON.parse(selectedOption.dataset.position);
        detailsDiv.style.display = 'block';
        detailsDiv.innerHTML = `
            <div class="result-item">
                <span class="result-label">Symbol</span>
                <span class="result-value">${pos.symbol}</span>
            </div>
            <div class="result-item">
                <span class="result-label">Position</span>
                <span class="result-value">${pos.position_type.toUpperCase()} ${pos.leverage}x</span>
            </div>
            <div class="result-item">
                <span class="result-label">Entry Price</span>
                <span class="result-value">${formatPrice(pos.entry_price)}</span>
            </div>
            <div class="result-item">
                <span class="result-label">Position Size</span>
                <span class="result-value">$${parseFloat(pos.position_size).toFixed(2)}</span>
            </div>
            <div class="result-item">
                <span class="result-label">Liquidation Price</span>
                <span class="result-value" style="color: var(--accent-red);">${formatPrice(pos.liquidation_price)}</span>
            </div>
        `;
    } else {
        detailsDiv.style.display = 'none';
    }
}

// Format price for display
function formatPrice(price) {
    price = parseFloat(price);
    if (price >= 1000) {
        return price.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    } else if (price >= 1) {
        return price.toFixed(4);
    } else {
        return price.toFixed(8);
    }
}

// Enter key handlers
document.addEventListener('DOMContentLoaded', () => {
    document.getElementById('priceSymbol')?.addEventListener('keypress', (e) => {
        if (e.key === 'Enter') fetchPrice();
    });
    
    document.getElementById('fundingSymbol')?.addEventListener('keypress', (e) => {
        if (e.key === 'Enter') fetchFunding();
    });
});
