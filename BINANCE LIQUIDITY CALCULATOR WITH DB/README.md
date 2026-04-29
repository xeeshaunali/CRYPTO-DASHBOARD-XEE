# Binance Futures Trading Journal 📊

A comprehensive Flask web application for managing Binance futures trades with complete position tracking, fee calculations, database storage, and performance analytics.

## 🚀 Features

### ✅ Complete Position Management
- **Open Positions**: Track all active trades with entry price, leverage, and liquidation price
- **Close Positions**: Exit trades and automatically calculate P&L with all fees
- **Position History**: View all past trades with detailed metrics

### 💰 Advanced P&L Calculations
- **Trading Fees**: Automatically calculates maker (0.02%) and taker (0.04%) fees
- **Funding Rate Fees**: Calculates funding payments based on holding time
- **Break-Even Price**: Shows exact price needed to cover all fees
- **Net P&L**: Total profit/loss after all fees deducted
- **ROI**: Return on investment percentage

### 📈 Real-Time Market Data
- **Live Prices**: Fetch current cryptocurrency prices from Binance
- **Funding Rates**: Monitor funding rates and next funding time
- **Mark Price**: View mark prices used for liquidations

### 📊 Performance Analytics
- **Daily Statistics**: Today's trading performance
- **Weekly Statistics**: Last 7 days performance
- **Monthly Statistics**: Last 30 days performance
- **All-Time Statistics**: Complete trading history
- **Win Rate**: Track winning vs losing trades
- **Total Fees Paid**: Monitor all trading costs

### 💾 Database Storage
- **MySQL Database**: All positions stored permanently
- **phpMyAdmin**: Web interface for database management
- **Data Persistence**: Never lose your trading history

## 📦 Installation

### Option 1: Docker (Recommended)

**Prerequisites:**
- Docker installed
- Docker Compose installed

**Steps:**

1. **Extract all files to a folder**

2. **Start the application:**
```bash
docker-compose up -d
```

3. **Access the applications:**
- **Trading Journal**: http://localhost:5000
- **phpMyAdmin**: http://localhost:8080
  - Username: `root`
  - Password: `root`

4. **Stop the application:**
```bash
docker-compose down
```

### Option 2: Manual Installation

**Prerequisites:**
- Python 3.8+
- MySQL Server 8.0+

**Steps:**

1. **Install MySQL:**
```bash
# Ubuntu/Debian
sudo apt-get install mysql-server

# macOS
brew install mysql

# Windows
Download from https://dev.mysql.com/downloads/mysql/
```

2. **Start MySQL and create database:**
```bash
mysql -u root -p

CREATE DATABASE binance_trading;
CREATE USER 'trader'@'localhost' IDENTIFIED BY 'trader123';
GRANT ALL PRIVILEGES ON binance_trading.* TO 'trader'@'localhost';
FLUSH PRIVILEGES;
EXIT;
```

3. **Install Python dependencies:**
```bash
pip install -r requirements.txt
```

4. **Update database configuration in app.py:**
```python
DB_CONFIG = {
    'host': 'localhost',
    'user': 'root',
    'password': 'root',  # Change this to your MySQL password
    'database': 'binance_trading'
}
```

5. **Run the application:**
```bash
python app.py
```

6. **Access the application:**
- Open browser: http://localhost:5000

## 📖 User Guide

### 1. Opening a Position

1. Click **"Open Position"** tab
2. Enter:
   - Symbol (e.g., BTCUSDT)
   - Entry Price
   - Position Size (your margin in USD)
   - Leverage (1-125x)
   - Select Long or Short
   - Add notes (optional)
3. Click **"Open Position"**
4. Position is saved to database

### 2. Closing a Position

1. Click **"Close Position"** tab
2. Click **"Refresh List"** to load open positions
3. Select position from dropdown
4. Enter exit price
5. Enter funding rate (optional, use 0 if unknown)
6. Click **"Close Position"**
7. View detailed P&L breakdown

### 3. Using P&L Calculator

1. Click **"P&L Calculator"** tab
2. Enter:
   - Entry Price
   - Exit/Current Price
   - Position Size (USD)
   - Leverage
   - Holding Hours (for funding fee calculation)
   - Funding Rate (in decimal, e.g., 0.0001)
   - Select Long/Short
   - Select Maker/Taker fee type
3. Click **"Calculate P&L"**
4. View complete breakdown:
   - Net P&L (after all fees)
   - Gross P&L (before fees)
   - Entry & Exit fees
   - Funding fees
   - Break-even price
   - ROI

### 4. Viewing Statistics

- **Dashboard shows**: Daily/Weekly/Monthly/All-time stats
- Click tabs to switch between periods
- Metrics include:
  - Total P&L
  - Total Trades
  - Win/Loss count
  - Win Rate %
  - Average ROI
  - Total Fees Paid

### 5. Position History

**Open Positions Tab:**
- Shows all active trades
- Displays liquidation prices
- Real-time position tracking

**Closed Positions Tab:**
- Filter by: All / Today / This Week / This Month
- View complete trade history
- See P&L and fees for each trade

## 💡 How Fees Are Calculated

### Trading Fees

**Entry Fee:**
```
Entry Fee = (Position Size × Leverage) × Fee Rate
```

**Exit Fee:**
```
Exit Fee = (Contracts × Exit Price) × Fee Rate
```

**Fee Rates:**
- Taker: 0.04% (default, when taking liquidity)
- Maker: 0.02% (when providing liquidity)

### Funding Fees

```
Funding Payments = Holding Hours ÷ 8 (rounded down)
Funding Fee = Position Value × Funding Rate × Payments

Position Value = Contracts × Entry Price
```

**Notes:**
- Funding occurs every 8 hours
- Positive rate = Long pays Short
- Negative rate = Short pays Long
- Rate is typically between -0.03% to +0.03%

### Net P&L

```
Net P&L = Gross P&L - Entry Fee - Exit Fee - Funding Fee
ROI = (Net P&L ÷ Position Size) × 100
```

### Break-Even Price

The price needed to cover all fees:

**For Long:**
```
Break-Even = Entry Price + (Total Fees ÷ Contracts)
```

**For Short:**
```
Break-Even = Entry Price - (Total Fees ÷ Contracts)
```

## 🗄️ Database Schema

### positions Table

| Column | Type | Description |
|--------|------|-------------|
| id | INT | Position ID (auto-increment) |
| symbol | VARCHAR(20) | Trading pair (e.g., BTCUSDT) |
| position_type | ENUM | 'long' or 'short' |
| entry_price | DECIMAL(20,8) | Entry price |
| exit_price | DECIMAL(20,8) | Exit price (NULL if open) |
| position_size | DECIMAL(20,8) | Margin amount (USD) |
| leverage | DECIMAL(5,2) | Leverage used |
| contracts | DECIMAL(20,8) | Number of contracts |
| liquidation_price | DECIMAL(20,8) | Liquidation price |
| entry_fee | DECIMAL(20,8) | Entry trading fee |
| exit_fee | DECIMAL(20,8) | Exit trading fee |
| funding_fee | DECIMAL(20,8) | Total funding fees paid |
| gross_pnl | DECIMAL(20,8) | P&L before fees |
| net_pnl | DECIMAL(20,8) | P&L after fees |
| roi | DECIMAL(10,4) | Return on investment % |
| status | ENUM | 'open' or 'closed' |
| opened_at | TIMESTAMP | When position opened |
| closed_at | TIMESTAMP | When position closed |
| holding_hours | DECIMAL(10,2) | How long held |
| notes | TEXT | Trade notes |

## 🔌 API Endpoints

### Market Data

**GET /api/price/<symbol>**
- Fetch current price
- Example: `/api/price/BTCUSDT`

**GET /api/funding/<symbol>**
- Get funding rate information
- Example: `/api/funding/BTCUSDT`

### Calculations

**POST /api/pnl**
- Calculate P&L with fees
- Body: `{entry_price, exit_price, position_size, leverage, holding_hours, funding_rate, position_type, fee_type}`

**POST /api/liquidation**
- Calculate liquidation price
- Body: `{entry_price, leverage, position_type}`

### Position Management

**POST /api/position/open**
- Open new position
- Body: `{symbol, position_type, entry_price, position_size, leverage, notes}`

**POST /api/position/close/<position_id>**
- Close existing position
- Body: `{exit_price, funding_rate}`

**GET /api/positions/open**
- Get all open positions

**GET /api/positions/closed?period=<all|today|week|month>**
- Get closed positions

**GET /api/statistics**
- Get trading statistics

## 📊 Accessing phpMyAdmin

1. Open: http://localhost:8080
2. Login:
   - Username: `root`
   - Password: `root`
3. Select `binance_trading` database
4. View/edit positions table
5. Run custom SQL queries
6. Export data to CSV/Excel

## ⚙️ Configuration

### Database Settings (app.py)

```python
DB_CONFIG = {
    'host': 'localhost',      # Database host
    'user': 'root',           # Database user
    'password': 'root',       # Database password
    'database': 'binance_trading'  # Database name
}
```

### Fee Rates (app.py)

```python
MAKER_FEE = 0.0002  # 0.02%
TAKER_FEE = 0.0004  # 0.04%
```

## 🛠️ Troubleshooting

### Database Connection Failed

**Solution 1: Check MySQL is running**
```bash
# Ubuntu/Debian
sudo service mysql status
sudo service mysql start

# macOS
brew services list
brew services start mysql
```

**Solution 2: Verify credentials**
```bash
mysql -u root -p
# Enter your password and check connection
```

**Solution 3: Reset MySQL password**
```bash
sudo mysql
ALTER USER 'root'@'localhost' IDENTIFIED BY 'root';
FLUSH PRIVILEGES;
EXIT;
```

### Port Already in Use

**Change Flask port in app.py:**
```python
app.run(debug=True, host='0.0.0.0', port=5001)  # Use different port
```

**Change phpMyAdmin port in docker-compose.yml:**
```yaml
ports:
  - "8081:80"  # Use 8081 instead of 8080
```

### Cannot Fetch Price from Binance

- Check internet connection
- Verify symbol is correct (must be uppercase: BTCUSDT)
- Ensure symbol exists on Binance Futures
- Check if Binance API is accessible in your region

## 📈 Trading Pair Examples

Common USDT perpetual futures:

- `BTCUSDT` - Bitcoin
- `ETHUSDT` - Ethereum
- `BNBUSDT` - Binance Coin
- `SOLUSDT` - Solana
- `XRPUSDT` - Ripple
- `ADAUSDT` - Cardano
- `DOGEUSDT` - Dogecoin
- `MATICUSDT` - Polygon
- `AVAXUSDT` - Avalanche
- `DOTUSDT` - Polkadot

## ⚠️ Important Notes

### Risk Warning
- This is a **tracking and calculation tool only**
- **No actual trading** is executed
- Always verify calculations before real trading
- Futures trading involves substantial risk
- Never risk more than you can afford to lose

### Data Accuracy
- Prices are real-time from Binance API
- Calculations use standard formulas
- Liquidation prices use 0.4% maintenance margin (standard for most pairs)
- Actual liquidation prices may vary based on position size and market conditions
- Always check official Binance platform for exact values

### Database Backups
```bash
# Export database
docker exec binance_mysql mysqldump -u root -proot binance_trading > backup.sql

# Import database
docker exec -i binance_mysql mysql -u root -proot binance_trading < backup.sql
```

## 📝 Version History

### v2.0 (Current)
- ✅ Complete database integration with MySQL
- ✅ phpMyAdmin for database management
- ✅ Position tracking (open/close)
- ✅ Fee calculations (trading + funding)
- ✅ Performance statistics
- ✅ Daily/Weekly/Monthly analytics
- ✅ Break-even price calculator
- ✅ Docker support

### v1.0
- Basic price fetching
- Liquidation calculator
- Simple P&L calculator
- Funding rate display

## 🤝 Support

For issues or questions:
1. Check [Binance API Documentation](https://binance-docs.github.io/apidocs/futures/en/)
2. Review [Binance Futures Trading Guide](https://www.binance.com/en/support/faq/futures)
3. Verify database connection and credentials

## 📄 License

Educational purposes only. Use at your own risk.

---

**Happy Trading! 🚀📈**
