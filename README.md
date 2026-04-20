# QuantGod Multi-Strategy Trading Engine v2.6

MT4 quantitative trading system with 5 strategies, a Chinese real-time dashboard, and a virtual small-account research mode.

## What Changed In v2.6

- Added **virtual research account** mode with a default starting balance of `10 USD`
- Real demo execution now uses **fixed micro-lots (`0.01`)** for safer sampling
- Dashboard now shows **research account** metrics first, with **real broker-account** values as reference
- Added a **Node-based local dashboard server** to avoid Windows file-lock issues from `python -m http.server`
- Added a **one-click launcher** for MT4 + dashboard

## Strategies

| # | Strategy | Description | Research Timeframe |
|---|----------|-------------|--------------------|
| 1 | MA_Cross | EMA(9/21) cross with higher-timeframe trend filter | M15 + H1 |
| 2 | RSI_Reversal | RSI extreme mean-reversion with Bollinger confirmation | H1 |
| 3 | BB_Triple | Bollinger + RSI + MACD confirmation | H1 |
| 4 | MACD_Divergence | Bullish / bearish divergence detection | H1 |
| 5 | SR_Breakout | Support / resistance breakout | M15 |

## Research Mode

- **VirtualStartingBalance**: `10`
- **VirtualRiskPercent**: `1%`
- **ResearchExecutionLot**: `0.01`
- **MaxDrawdownPercent**: `6%`
- **MaxTotalTrades**: `4`
- **IgnoreLegacyTradesInVirtualStats**: `true`

This means:

- the dashboard tracks the strategy as if it started from `10 USD`
- the real demo account only provides fills and market execution
- old oversized demo trades can be excluded from the current research sample

## Project Structure

```text
QuantGod_MT4/
├─ MQL4/
│  ├─ Experts/
│  │  └─ QuantGod_MultiStrategy.mq4
│  └─ Include/
│     └─ QuantEngine.mqh
├─ Dashboard/
│  ├─ QuantGod_Dashboard.html
│  ├─ dashboard_server.js
│  └─ start_dashboard.bat
└─ Start_QuantGod.bat
```

## Installation

Copy these files into your MT4 installation:

```text
MQL4/Experts/QuantGod_MultiStrategy.mq4  -> [MT4]/MQL4/Experts/
MQL4/Include/QuantEngine.mqh             -> [MT4]/MQL4/Include/
Dashboard/QuantGod_Dashboard.html        -> [MT4]/MQL4/Files/
Dashboard/dashboard_server.js            -> [MT4]/MQL4/Files/
Dashboard/start_dashboard.bat            -> [MT4]/MQL4/Files/
```

Compile `QuantGod_MultiStrategy.mq4` in MetaEditor after copying.

## One-Click Startup

Recommended:

```bat
Start_QuantGod.bat
```

This will:

- start MT4
- start the local dashboard server
- open `http://localhost:8080/QuantGod_Dashboard.html` with a cache-busting timestamp

If you only want the dashboard server:

```bat
Dashboard\start_dashboard.bat
```

## Cloudflare Deployment

The MT4 execution engine still runs on Windows / MT4. Cloudflare is used for:

- cloud dashboard hosting
- ingesting the latest MT4 snapshot
- exposing `/api/latest` for remote viewing

Project files are in:

```text
cloudflare/
```

Quick path:

1. Create a KV namespace with Wrangler
2. Fill the KV ids in `cloudflare/wrangler.jsonc`
3. Set `QG_INGEST_TOKEN` with `wrangler secret put`
4. Run `npx wrangler deploy`
5. In MT4 EA inputs, set:
   - `EnableCloudSync = true`
   - `CloudSyncEndpoint = https://<your-worker-domain>/api/ingest`
   - `CloudSyncToken = <same token>`
6. In MT4, allow the same domain under `Allow WebRequest for listed URL`

If you do not want to rely on MT4 WebRequest allowlist handling, use the local uploader:

- copy `Dashboard/cloud_sync_uploader.ps1` into `[MT4]/MQL4/Files/`
- create `[MT4]/MQL4/Files/quantgod_cloud_sync.json`
- `Start_QuantGod.bat` will auto-start the uploader when that file exists

## Dashboard

The dashboard shows:

- virtual research balance / equity / floating P&L / drawdown
- real broker-account balance / equity as reference
- per-symbol grouped strategy status
- open trades and closed trades
- research equity curve
- strategy profit distribution
- daily research P&L

## Key Parameters

| Parameter | Default | Meaning |
|-----------|---------|---------|
| RiskPercent | 0.04 | Used only when broker-balance mode is active |
| UseVirtualResearchAccount | true | Enable virtual small-account research |
| VirtualStartingBalance | 10 | Virtual starting balance |
| VirtualRiskPercent | 1 | Risk per trade on the virtual account |
| ResearchExecutionLot | 0.01 | Safe actual demo execution lot |
| MaxDrawdownPercent | 6 | Research drawdown guard |
| MaxTotalTrades | 4 | Portfolio-level concurrent position cap |

## Disclaimer

For demo testing and research only. No profitability guarantee. Do not treat virtual-account projections as live-trading expectations.

## License

MIT
