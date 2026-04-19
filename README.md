# QuantGod Multi-Strategy Trading Engine v2.0

A professional MT4 quantitative trading system with 5 integrated strategies and a real-time web monitoring dashboard.

## Strategies

| # | Strategy | Description | Timeframe | Win Rate* |
|---|----------|-------------|-----------|-----------|
| 1 | **MA Crossover** | EMA(9/21) crossover with 200 SMA trend filter + RSI confirmation | H1 | ~55% |
| 2 | **RSI Mean Reversion** | RSI(2) extreme reversal with Bollinger Band confirmation | H4 | ~60% |
| 3 | **BB Triple Confirm** | Bollinger Band + RSI(14) + MACD triple signal confirmation | H4 | ~78% |
| 4 | **MACD Divergence** | Price-MACD divergence detection (bullish/bearish) | H4 | ~58% |
| 5 | **S/R Breakout** | Support/Resistance breakout with volume confirmation | H1 | ~52% |

*Estimated based on strategy research. Actual results depend on market conditions.*

## Risk Management

- **Position Sizing**: 1-2% risk per trade (ATR-based stop loss calculation)
- **Max Drawdown**: Auto-pause at 15% drawdown
- **Max Positions**: 6 concurrent positions across all strategies
- **Trailing Stop**: Configurable trailing stop (default 25 pips)
- **Trade Sessions**: London + New York session filter

## Project Structure

```
QuantGod_MT4/
├── MQL4/
│   ├── Experts/
│   │   └── QuantGod_MultiStrategy.mq4    # Main EA (5 strategies)
│   ├── Include/
│   │   └── QuantEngine.mqh               # Core engine library
│   └── Files/
│       └── (runtime data: JSON/CSV exports)
├── Dashboard/
│   └── QuantGod_Dashboard.html           # Web monitoring panel
└── README.md
```

## Installation

### 1. Install EA
Copy the MQL4 files to your MetaTrader 4 directory:
```
MQL4/Experts/QuantGod_MultiStrategy.mq4  →  [MT4]/MQL4/Experts/
MQL4/Include/QuantEngine.mqh             →  [MT4]/MQL4/Include/
Dashboard/QuantGod_Dashboard.html        →  [MT4]/MQL4/Files/
```

### 2. Compile
Open MetaEditor (F4 in MT4), then open and compile `QuantGod_MultiStrategy.mq4`.

### 3. Attach to Chart
- Drag the EA onto any chart (recommended: EURUSD, H1/H4)
- Enable "Allow DLL imports" and "Allow live trading" in EA settings
- Configure strategy parameters as needed

### 4. Open Dashboard
Open `Dashboard/QuantGod_Dashboard.html` in a web browser. The EA exports data to `MQL4/Files/QuantGod_Dashboard.json` every 30 seconds.

For real-time data loading, run a local HTTP server in the `MQL4/Files/` folder:
```bash
# Python
python -m http.server 8080

# Node.js
npx serve .
```
Then open `http://localhost:8080/QuantGod_Dashboard.html`.

## Dashboard Features

- Real-time account stats (balance, equity, P&L, drawdown)
- Live open positions with strategy labels
- Trade history with filtering
- Equity curve chart
- Strategy performance breakdown (pie chart)
- Daily P&L bar chart
- Strategy win rate tracking
- Auto-refresh every 5 seconds
- Beautiful dark theme UI
- Demo data preview when EA is not running

## Configuration

All parameters are configurable via MT4's EA input panel:

| Parameter | Default | Description |
|-----------|---------|-------------|
| RiskPercent | 1.5% | Risk per trade |
| MaxDrawdownPercent | 15% | Max drawdown before pause |
| MaxTotalTrades | 6 | Max concurrent positions |
| TrailingStopPips | 25 | Trailing stop distance |
| Enable_MA/RSI/BB/MACD/SR | true | Toggle each strategy |

## Disclaimer

This system is for **educational and demo testing purposes only**. Past performance does not guarantee future results. Always test thoroughly on a demo account before considering any real trading. The authors assume no responsibility for any financial losses.

## License

MIT License
