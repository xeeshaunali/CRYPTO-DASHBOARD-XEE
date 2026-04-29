# Binance Futures Calculator

A comprehensive Flask web application for Binance futures trading calculations, including live price tracking, liquidation price calculations, profit/loss analysis, and funding rate monitoring.

## Features

### 1. **Live Price Tracker**
- Fetch real-time cryptocurrency prices from Binance Futures
- Support for all USDT perpetual futures pairs

### 2. **Liquidation Price Calculator**
- Calculate liquidation prices for both long and short positions
- Adjustable leverage (1x to 125x)
- Shows distance to liquidation percentage
- Uses 0.4% maintenance margin rate (standard for most pairs)

### 3. **P&L Calculator**
- Calculate profit/loss for futures positions
- Shows P&L in USD and percentage
- Displays ROI based on initial margin
- Calculates number of contracts
- Support for both long and short positions

### 4. **Funding Rate Monitor**
- View current funding rates for perpetual futures
- Display next funding time
- Show mark price vs spot price

## Installation

### Prerequisites
- Python 3.8 or higher
- pip (Python package installer)

### Setup

1. **Install dependencies:**
```bash
pip install -r requirements.txt
```

2. **Run the application:**
```bash
python app.py
```

3. **Access the application:**
Open your browser and navigate to:
```
http://localhost:5000
```

## Usage Guide

### Live Price
1. Enter the trading pair symbol (e.g., `BTCUSDT`, `ETHUSDT`)
2. Click "Get Price" to fetch the current price

### Funding Rate
1. Enter the trading pair symbol
2. Click "Get Funding" to see:
   - Current funding rate (%)
   - Next funding time
   - Mark price

### Liquidation Calculator
1. Enter your **Entry Price**
2. Enter your **Leverage** (1-125)
3. Select **Position Type** (Long or Short)
4. Click "Calculate Liquidation"

**Results show:**
- Liquidation price
- Distance to liquidation (%)
- Position details

### P&L Calculator
1. Enter your **Entry Price**
2. Enter your **Exit/Current Price**
3. Enter your **Position Size** in USD (your margin)
4. Enter your **Leverage**
5. Select **Position Type** (Long or Short)
6. Click "Calculate P&L"

**Results show:**
- Total P&L in USD
- ROI percentage (return on margin)
- Price change percentage
- Number of contracts
- Position summary

## Calculation Formulas

### Liquidation Price

**For Long Positions:**
```
Liquidation Price = Entry Price × (1 - 1/Leverage + MMR)
```

**For Short Positions:**
```
Liquidation Price = Entry Price × (1 + 1/Leverage - MMR)
```

Where MMR (Maintenance Margin Rate) = 0.4% = 0.004

### Profit/Loss

**Number of Contracts:**
```
Contracts = (Position Size × Leverage) / Entry Price
```

**For Long Positions:**
```
P&L = (Exit Price - Entry Price) × Contracts
ROI = (P&L / Position Size) × 100
```

**For Short Positions:**
```
P&L = (Entry Price - Exit Price) × Contracts
ROI = (P&L / Position Size) × 100
```

## API Endpoints

The application exposes the following REST API endpoints:

### GET `/api/price/<symbol>`
Fetch current price for a trading pair
```json
{
  "symbol": "BTCUSDT",
  "price": 50000.00
}
```

### GET `/api/funding/<symbol>`
Get funding rate information
```json
{
  "symbol": "BTCUSDT",
  "funding_rate": 0.0100,
  "next_funding_time": "2024-01-01 16:00:00 UTC",
  "mark_price": 50005.50
}
```

### POST `/api/liquidation`
Calculate liquidation price
```json
{
  "entry_price": 50000,
  "leverage": 10,
  "position_type": "long"
}
```

### POST `/api/pnl`
Calculate profit/loss
```json
{
  "entry_price": 50000,
  "exit_price": 51000,
  "position_size": 1000,
  "position_type": "long",
  "leverage": 10
}
```

## Common Trading Pairs

- `BTCUSDT` - Bitcoin
- `ETHUSDT` - Ethereum
- `BNBUSDT` - Binance Coin
- `SOLUSDT` - Solana
- `XRPUSDT` - Ripple
- `ADAUSDT` - Cardano
- `DOGEUSDT` - Dogecoin
- `MATICUSDT` - Polygon

## Important Notes

⚠️ **Risk Warning:**
- This calculator is for educational purposes only
- Futures trading involves substantial risk of loss
- Always use stop-loss orders
- Never risk more than you can afford to lose
- The liquidation calculations use a standard 0.4% maintenance margin rate, but actual rates may vary by position size and market conditions

📊 **Accuracy:**
- Prices are fetched in real-time from Binance API
- Calculations are accurate based on standard formulas
- Always verify critical calculations before trading

🔒 **Privacy:**
- This application does not require API keys
- No trading is executed through this app
- All calculations are performed locally

## Troubleshooting

**"Failed to fetch price" error:**
- Check your internet connection
- Verify the symbol is correct (e.g., `BTCUSDT` not `BTC`)
- Ensure the symbol exists on Binance Futures

**Network errors:**
- The app requires internet access to fetch data from Binance
- Check if Binance API is accessible in your region

## License

This project is for educational purposes only. Use at your own risk.

## Support

For issues or questions, please check:
- [Binance API Documentation](https://binance-docs.github.io/apidocs/futures/en/)
- [Binance Futures Trading Guide](https://www.binance.com/en/support/faq/futures)
