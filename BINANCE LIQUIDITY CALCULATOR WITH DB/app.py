from flask import Flask, render_template, request, jsonify
import requests
from decimal import Decimal, ROUND_DOWN
from datetime import datetime, timedelta
import mysql.connector
from mysql.connector import Error
import json

app = Flask(__name__)

# Database configuration
DB_CONFIG = {
    'host': 'localhost',
    'user': 'root',
    'password': 'toor',
    'database': 'binance_trading'
}

# Binance API endpoints
BINANCE_API_BASE = "https://fapi.binance.com"

# Fee rates (Binance standard)
MAKER_FEE = 0.0002  # 0.02%
TAKER_FEE = 0.0004  # 0.04%

def get_db_connection():
    """Create database connection"""
    try:
        connection = mysql.connector.connect(**DB_CONFIG)
        return connection
    except Error as e:
        print(f"Database connection error: {e}")
        return None

def init_database():
    """Initialize database and create tables"""
    try:
        # Connect without database to create it
        connection = mysql.connector.connect(
            host=DB_CONFIG['host'],
            user=DB_CONFIG['user'],
            password=DB_CONFIG['password']
        )
        cursor = connection.cursor()
        
        # Create database if not exists
        cursor.execute(f"CREATE DATABASE IF NOT EXISTS {DB_CONFIG['database']}")
        cursor.execute(f"USE {DB_CONFIG['database']}")
        
        # Create positions table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS positions (
                id INT AUTO_INCREMENT PRIMARY KEY,
                symbol VARCHAR(20) NOT NULL,
                position_type ENUM('long', 'short') NOT NULL,
                entry_price DECIMAL(20, 8) NOT NULL,
                exit_price DECIMAL(20, 8) DEFAULT NULL,
                position_size DECIMAL(20, 8) NOT NULL,
                leverage DECIMAL(5, 2) NOT NULL,
                contracts DECIMAL(20, 8) NOT NULL,
                liquidation_price DECIMAL(20, 8) NOT NULL,
                entry_fee DECIMAL(20, 8) NOT NULL,
                exit_fee DECIMAL(20, 8) DEFAULT NULL,
                funding_fee DECIMAL(20, 8) DEFAULT 0,
                gross_pnl DECIMAL(20, 8) DEFAULT NULL,
                net_pnl DECIMAL(20, 8) DEFAULT NULL,
                roi DECIMAL(10, 4) DEFAULT NULL,
                status ENUM('open', 'closed') DEFAULT 'open',
                opened_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                closed_at TIMESTAMP NULL DEFAULT NULL,
                holding_hours DECIMAL(10, 2) DEFAULT 0,
                notes TEXT,
                INDEX idx_symbol (symbol),
                INDEX idx_status (status),
                INDEX idx_opened_at (opened_at),
                INDEX idx_closed_at (closed_at)
            )
        """)
        
        connection.commit()
        cursor.close()
        connection.close()
        print("Database initialized successfully")
        return True
    except Error as e:
        print(f"Database initialization error: {e}")
        return False

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
        
        funding_rate = float(data['lastFundingRate'])
        next_funding_time = datetime.fromtimestamp(int(data['nextFundingTime']) / 1000)
        
        return {
            'rate': funding_rate * 100,  # Convert to percentage
            'rate_decimal': funding_rate,  # Keep decimal for calculations
            'next_time': next_funding_time.strftime('%Y-%m-%d %H:%M:%S UTC'),
            'mark_price': float(data['markPrice'])
        }
    except Exception as e:
        print(f"Error fetching funding rate: {e}")
        return None

def calculate_liquidation_price(entry_price, leverage, position_type, maintenance_margin_rate=0.004):
    """Calculate liquidation price for a position"""
    entry_price = Decimal(str(entry_price))
    leverage = Decimal(str(leverage))
    maintenance_margin_rate = Decimal(str(maintenance_margin_rate))
    
    if position_type.lower() == 'long':
        liq_price = entry_price * (1 - 1/leverage + maintenance_margin_rate)
    else:
        liq_price = entry_price * (1 + 1/leverage - maintenance_margin_rate)
    
    return float(liq_price)

def calculate_fees_and_pnl(entry_price, exit_price, position_size, position_type, leverage, 
                          holding_hours=0, funding_rate_decimal=0, fee_type='taker'):
    """
    Calculate comprehensive P&L including all fees
    """
    entry_price = Decimal(str(entry_price))
    exit_price = Decimal(str(exit_price))
    position_size = Decimal(str(position_size))
    leverage = Decimal(str(leverage))
    
    # Calculate number of contracts
    contracts = position_size * leverage / entry_price
    
    # Calculate gross P&L
    if position_type.lower() == 'long':
        gross_pnl = (exit_price - entry_price) * contracts
    else:
        gross_pnl = (entry_price - exit_price) * contracts
    
    # Fee rate selection
    fee_rate = Decimal(str(TAKER_FEE if fee_type == 'taker' else MAKER_FEE))
    
    # Calculate trading fees
    notional_value = contracts * entry_price
    entry_fee = notional_value * fee_rate
    exit_fee = contracts * exit_price * fee_rate
    total_trading_fees = entry_fee + exit_fee
    
    # Calculate funding fees (paid every 8 hours)
    funding_payments = int(holding_hours / 8) if holding_hours > 0 else 0
    funding_fee = Decimal(0)
    
    if funding_payments > 0 and funding_rate_decimal != 0:
        # Funding fee = Position Value × Funding Rate × Number of Payments
        position_value = contracts * entry_price
        funding_fee = position_value * Decimal(str(funding_rate_decimal)) * Decimal(str(funding_payments))
        
        # If short and funding is positive, or long and funding is negative, you receive funding
        if (position_type.lower() == 'short' and funding_rate_decimal > 0) or \
           (position_type.lower() == 'long' and funding_rate_decimal < 0):
            funding_fee = -funding_fee  # Negative means you receive
    
    # Calculate net P&L
    net_pnl = gross_pnl - total_trading_fees - funding_fee
    
    # Calculate ROI
    roi = (net_pnl / position_size) * 100
    
    # Calculate break-even price
    total_fees = total_trading_fees + funding_fee
    fee_per_contract = total_fees / contracts
    
    if position_type.lower() == 'long':
        breakeven_price = entry_price + fee_per_contract
    else:
        breakeven_price = entry_price - fee_per_contract
    
    return {
        'contracts': float(contracts),
        'gross_pnl': float(gross_pnl),
        'entry_fee': float(entry_fee),
        'exit_fee': float(exit_fee),
        'total_trading_fees': float(total_trading_fees),
        'funding_payments': funding_payments,
        'funding_fee': float(funding_fee),
        'total_fees': float(total_fees),
        'net_pnl': float(net_pnl),
        'roi': float(roi),
        'breakeven_price': float(breakeven_price)
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
            'funding_rate_decimal': funding['rate_decimal'],
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
    """API endpoint to calculate PNL with fees"""
    data = request.json
    
    try:
        entry_price = float(data['entry_price'])
        exit_price = float(data['exit_price'])
        position_size = float(data['position_size'])
        position_type = data['position_type']
        leverage = float(data['leverage'])
        holding_hours = float(data.get('holding_hours', 0))
        funding_rate = float(data.get('funding_rate', 0))
        fee_type = data.get('fee_type', 'taker')
        
        result = calculate_fees_and_pnl(
            entry_price, exit_price, position_size, position_type, 
            leverage, holding_hours, funding_rate, fee_type
        )
        
        return jsonify({
            **result,
            'entry_price': entry_price,
            'exit_price': exit_price,
            'position_size': position_size,
            'position_type': position_type,
            'leverage': leverage,
            'holding_hours': holding_hours
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 400

@app.route('/api/position/open', methods=['POST'])
def open_position():
    """Open a new position and save to database"""
    data = request.json
    
    try:
        symbol = data['symbol'].upper()
        position_type = data['position_type']
        entry_price = float(data['entry_price'])
        position_size = float(data['position_size'])
        leverage = float(data['leverage'])
        notes = data.get('notes', '')
        
        # Calculate contracts
        contracts = (position_size * leverage) / entry_price
        
        # Calculate liquidation price
        liq_price = calculate_liquidation_price(entry_price, leverage, position_type)
        
        # Calculate entry fee
        notional_value = contracts * entry_price
        entry_fee = notional_value * TAKER_FEE
        
        # Save to database
        connection = get_db_connection()
        if not connection:
            return jsonify({'error': 'Database connection failed'}), 500
        
        cursor = connection.cursor()
        query = """
            INSERT INTO positions 
            (symbol, position_type, entry_price, position_size, leverage, 
             contracts, liquidation_price, entry_fee, notes)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        """
        values = (symbol, position_type, entry_price, position_size, leverage,
                 contracts, liq_price, entry_fee, notes)
        
        cursor.execute(query, values)
        connection.commit()
        position_id = cursor.lastrowid
        
        cursor.close()
        connection.close()
        
        return jsonify({
            'success': True,
            'position_id': position_id,
            'message': f'Position #{position_id} opened successfully',
            'liquidation_price': round(liq_price, 8)
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 400

@app.route('/api/position/close/<int:position_id>', methods=['POST'])
def close_position(position_id):
    """Close an existing position"""
    data = request.json
    
    try:
        exit_price = float(data['exit_price'])
        funding_rate = float(data.get('funding_rate', 0))
        
        connection = get_db_connection()
        if not connection:
            return jsonify({'error': 'Database connection failed'}), 500
        
        cursor = connection.cursor(dictionary=True)
        
        # Get position details
        cursor.execute("SELECT * FROM positions WHERE id = %s AND status = 'open'", (position_id,))
        position = cursor.fetchone()
        
        if not position:
            return jsonify({'error': 'Position not found or already closed'}), 404
        
        # Calculate holding time
        opened_at = position['opened_at']
        closed_at = datetime.now()
        holding_time = closed_at - opened_at
        holding_hours = holding_time.total_seconds() / 3600
        
        # Calculate P&L with fees
        result = calculate_fees_and_pnl(
            position['entry_price'],
            exit_price,
            position['position_size'],
            position['position_type'],
            position['leverage'],
            holding_hours,
            funding_rate,
            'taker'
        )
        
        # Update position in database
        update_query = """
            UPDATE positions 
            SET exit_price = %s, exit_fee = %s, funding_fee = %s,
                gross_pnl = %s, net_pnl = %s, roi = %s,
                status = 'closed', closed_at = %s, holding_hours = %s
            WHERE id = %s
        """
        values = (exit_price, result['exit_fee'], result['funding_fee'],
                 result['gross_pnl'], result['net_pnl'], result['roi'],
                 closed_at, holding_hours, position_id)
        
        cursor.execute(update_query, values)
        connection.commit()
        
        cursor.close()
        connection.close()
        
        return jsonify({
            'success': True,
            'position_id': position_id,
            'message': f'Position #{position_id} closed successfully',
            **result,
            'holding_hours': round(holding_hours, 2)
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 400

@app.route('/api/positions/open')
def get_open_positions():
    """Get all open positions"""
    try:
        connection = get_db_connection()
        if not connection:
            return jsonify({'error': 'Database connection failed'}), 500
        
        cursor = connection.cursor(dictionary=True)
        cursor.execute("""
            SELECT id, symbol, position_type, entry_price, position_size, 
                   leverage, contracts, liquidation_price, entry_fee,
                   opened_at, notes
            FROM positions 
            WHERE status = 'open'
            ORDER BY opened_at DESC
        """)
        
        positions = cursor.fetchall()
        
        # Convert datetime to string
        for pos in positions:
            pos['opened_at'] = pos['opened_at'].strftime('%Y-%m-%d %H:%M:%S')
        
        cursor.close()
        connection.close()
        
        return jsonify({'positions': positions})
        
    except Exception as e:
        return jsonify({'error': str(e)}), 400

@app.route('/api/positions/closed')
def get_closed_positions():
    """Get all closed positions with optional date filter"""
    try:
        # Get filter parameters
        period = request.args.get('period', 'all')  # all, today, week, month
        
        connection = get_db_connection()
        if not connection:
            return jsonify({'error': 'Database connection failed'}), 500
        
        cursor = connection.cursor(dictionary=True)
        
        # Build query based on period
        base_query = """
            SELECT id, symbol, position_type, entry_price, exit_price,
                   position_size, leverage, contracts, liquidation_price,
                   entry_fee, exit_fee, funding_fee, gross_pnl, net_pnl, roi,
                   opened_at, closed_at, holding_hours, notes
            FROM positions 
            WHERE status = 'closed'
        """
        
        if period == 'today':
            base_query += " AND DATE(closed_at) = CURDATE()"
        elif period == 'week':
            base_query += " AND closed_at >= DATE_SUB(NOW(), INTERVAL 7 DAY)"
        elif period == 'month':
            base_query += " AND closed_at >= DATE_SUB(NOW(), INTERVAL 30 DAY)"
        
        base_query += " ORDER BY closed_at DESC"
        
        cursor.execute(base_query)
        positions = cursor.fetchall()
        
        # Convert datetime to string
        for pos in positions:
            pos['opened_at'] = pos['opened_at'].strftime('%Y-%m-%d %H:%M:%S')
            if pos['closed_at']:
                pos['closed_at'] = pos['closed_at'].strftime('%Y-%m-%d %H:%M:%S')
        
        cursor.close()
        connection.close()
        
        return jsonify({'positions': positions})
        
    except Exception as e:
        return jsonify({'error': str(e)}), 400

@app.route('/api/statistics')
def get_statistics():
    """Get trading statistics (daily, weekly, monthly)"""
    try:
        connection = get_db_connection()
        if not connection:
            return jsonify({'error': 'Database connection failed'}), 500
        
        cursor = connection.cursor(dictionary=True)
        
        # Today's stats
        cursor.execute("""
            SELECT 
                COUNT(*) as total_trades,
                SUM(CASE WHEN net_pnl > 0 THEN 1 ELSE 0 END) as winning_trades,
                SUM(CASE WHEN net_pnl < 0 THEN 1 ELSE 0 END) as losing_trades,
                COALESCE(SUM(net_pnl), 0) as total_pnl,
                COALESCE(SUM(entry_fee + exit_fee + funding_fee), 0) as total_fees,
                COALESCE(AVG(roi), 0) as avg_roi
            FROM positions
            WHERE status = 'closed' AND DATE(closed_at) = CURDATE()
        """)
        daily_stats = cursor.fetchone()
        
        # Weekly stats
        cursor.execute("""
            SELECT 
                COUNT(*) as total_trades,
                SUM(CASE WHEN net_pnl > 0 THEN 1 ELSE 0 END) as winning_trades,
                SUM(CASE WHEN net_pnl < 0 THEN 1 ELSE 0 END) as losing_trades,
                COALESCE(SUM(net_pnl), 0) as total_pnl,
                COALESCE(SUM(entry_fee + exit_fee + funding_fee), 0) as total_fees,
                COALESCE(AVG(roi), 0) as avg_roi
            FROM positions
            WHERE status = 'closed' AND closed_at >= DATE_SUB(NOW(), INTERVAL 7 DAY)
        """)
        weekly_stats = cursor.fetchone()
        
        # Monthly stats
        cursor.execute("""
            SELECT 
                COUNT(*) as total_trades,
                SUM(CASE WHEN net_pnl > 0 THEN 1 ELSE 0 END) as winning_trades,
                SUM(CASE WHEN net_pnl < 0 THEN 1 ELSE 0 END) as losing_trades,
                COALESCE(SUM(net_pnl), 0) as total_pnl,
                COALESCE(SUM(entry_fee + exit_fee + funding_fee), 0) as total_fees,
                COALESCE(AVG(roi), 0) as avg_roi
            FROM positions
            WHERE status = 'closed' AND closed_at >= DATE_SUB(NOW(), INTERVAL 30 DAY)
        """)
        monthly_stats = cursor.fetchone()
        
        # All-time stats
        cursor.execute("""
            SELECT 
                COUNT(*) as total_trades,
                SUM(CASE WHEN net_pnl > 0 THEN 1 ELSE 0 END) as winning_trades,
                SUM(CASE WHEN net_pnl < 0 THEN 1 ELSE 0 END) as losing_trades,
                COALESCE(SUM(net_pnl), 0) as total_pnl,
                COALESCE(SUM(entry_fee + exit_fee + funding_fee), 0) as total_fees,
                COALESCE(AVG(roi), 0) as avg_roi
            FROM positions
            WHERE status = 'closed'
        """)
        alltime_stats = cursor.fetchone()
        
        cursor.close()
        connection.close()
        
        # Calculate win rates
        for stats in [daily_stats, weekly_stats, monthly_stats, alltime_stats]:
            if stats['total_trades'] > 0:
                stats['win_rate'] = float((stats['winning_trades'] / stats['total_trades']) * 100)
            else:
                stats['win_rate'] = 0.0
            
            # Ensure all numeric fields are properly typed
            stats['total_pnl'] = float(stats['total_pnl']) if stats['total_pnl'] else 0.0
            stats['total_fees'] = float(stats['total_fees']) if stats['total_fees'] else 0.0
            stats['avg_roi'] = float(stats['avg_roi']) if stats['avg_roi'] else 0.0
            stats['total_trades'] = int(stats['total_trades']) if stats['total_trades'] else 0
            stats['winning_trades'] = int(stats['winning_trades']) if stats['winning_trades'] else 0
            stats['losing_trades'] = int(stats['losing_trades']) if stats['losing_trades'] else 0
        
        return jsonify({
            'daily': daily_stats,
            'weekly': weekly_stats,
            'monthly': monthly_stats,
            'alltime': alltime_stats
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 400

if __name__ == '__main__':
    # Initialize database on startup
    init_database()
    app.run(debug=True, host='0.0.0.0', port=5000)
