from flask import Flask, render_template, request, jsonify
import requests
from decimal import Decimal, ROUND_DOWN
from datetime import datetime

app = Flask(__name__)

# Binance API endpoints
BINANCE_API_BASE = "https://fapi.binance.com"

def get_symbol_price(symbol):
    """Fetch current price for a symbol"""
    try:
        url = f"{BINANCE_API_BASE}/fapi/v1/ticker/price"
        params = {"symbol": symbol.upper()}
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
        return float(data['price'])
    except Exception as e:
        print(f"Error fetching price: {e}")
        return None

def get_funding_rate(symbol):
    """Fetch current funding rate and next funding time"""
    try:
        url = f"{BINANCE_API_BASE}/fapi/v1/premiumIndex"
        params = {"symbol": symbol.upper()}
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        funding_rate = float(data['lastFundingRate']) * 100  # Convert to percentage
        next_funding_time = datetime.fromtimestamp(int(data['nextFundingTime']) / 1000)
        
        return {
            'rate': funding_rate,
            'next_time': next_funding_time.strftime('%Y-%m-%d %H:%M:%S UTC'),
            'mark_price': float(data['markPrice'])
        }
    except Exception as e:
        print(f"Error fetching funding rate: {e}")
        return None

def calculate_liquidation_price(entry_price, leverage, position_type, maintenance_margin_rate=0.004):
    """
    Calculate liquidation price for a position
    
    Args:
        entry_price: Entry price of the position
        leverage: Leverage used (e.g., 10 for 10x)
        position_type: 'long' or 'short'
        maintenance_margin_rate: Maintenance margin rate (default 0.4%)
    """
    entry_price = Decimal(str(entry_price))
    leverage = Decimal(str(leverage))
    maintenance_margin_rate = Decimal(str(maintenance_margin_rate))
    
    if position_type.lower() == 'long':
        # Long liquidation: Entry Price * (1 - 1/Leverage + MMR)
        liq_price = entry_price * (1 - 1/leverage + maintenance_margin_rate)
    else:  # short
        # Short liquidation: Entry Price * (1 + 1/Leverage - MMR)
        liq_price = entry_price * (1 + 1/leverage - maintenance_margin_rate)
    
    return float(liq_price)

def calculate_pnl(entry_price, exit_price, position_size, position_type, leverage):
    """
    Calculate profit/loss for a futures position
    
    Args:
        entry_price: Entry price
        exit_price: Exit/current price
        position_size: Position size in USD
        position_type: 'long' or 'short'
        leverage: Leverage used
    """
    entry_price = Decimal(str(entry_price))
    exit_price = Decimal(str(exit_price))
    position_size = Decimal(str(position_size))
    leverage = Decimal(str(leverage))
    
    # Calculate number of contracts
    contracts = position_size * leverage / entry_price
    
    if position_type.lower() == 'long':
        # Long PNL: (Exit Price - Entry Price) * Contracts
        pnl = (exit_price - entry_price) * contracts
        pnl_percentage = ((exit_price - entry_price) / entry_price) * 100 * leverage
    else:  # short
        # Short PNL: (Entry Price - Exit Price) * Contracts
        pnl = (entry_price - exit_price) * contracts
        pnl_percentage = ((entry_price - exit_price) / entry_price) * 100 * leverage
    
    roi = (pnl / position_size) * 100
    
    return {
        'pnl': float(pnl),
        'pnl_percentage': float(pnl_percentage),
        'roi': float(roi),
        'contracts': float(contracts)
    }

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/price/<symbol>')
def get_price(symbol):
    """API endpoint to get current price"""
    price = get_symbol_price(symbol)
    if price:
        return jsonify({'symbol': symbol.upper(), 'price': price})
    return jsonify({'error': 'Failed to fetch price'}), 400

@app.route('/api/funding/<symbol>')
def get_funding(symbol):
    """API endpoint to get funding rate"""
    funding = get_funding_rate(symbol)
    if funding:
        return jsonify({
            'symbol': symbol.upper(),
            'funding_rate': funding['rate'],
            'next_funding_time': funding['next_time'],
            'mark_price': funding['mark_price']
        })
    return jsonify({'error': 'Failed to fetch funding rate'}), 400

@app.route('/api/liquidation', methods=['POST'])
def calculate_liq():
    """API endpoint to calculate liquidation price"""
    data = request.json
    
    try:
        entry_price = float(data['entry_price'])
        leverage = float(data['leverage'])
        position_type = data['position_type']
        
        liq_price = calculate_liquidation_price(entry_price, leverage, position_type)
        
        return jsonify({
            'liquidation_price': round(liq_price, 8),
            'entry_price': entry_price,
            'leverage': leverage,
            'position_type': position_type
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 400

@app.route('/api/pnl', methods=['POST'])
def calculate_profit():
    """API endpoint to calculate PNL"""
    data = request.json
    
    try:
        entry_price = float(data['entry_price'])
        exit_price = float(data['exit_price'])
        position_size = float(data['position_size'])
        position_type = data['position_type']
        leverage = float(data['leverage'])
        
        result = calculate_pnl(entry_price, exit_price, position_size, position_type, leverage)
        
        return jsonify({
            'pnl': round(result['pnl'], 2),
            'pnl_percentage': round(result['pnl_percentage'], 2),
            'roi': round(result['roi'], 2),
            'contracts': round(result['contracts'], 8),
            'entry_price': entry_price,
            'exit_price': exit_price,
            'position_size': position_size,
            'position_type': position_type,
            'leverage': leverage
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 400

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
