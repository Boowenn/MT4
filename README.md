# QuantGod Multi-Strategy Trading Engine

MT4 quantitative trading system with 5 strategies, a Chinese real-time dashboard, and a virtual small-account research mode.

The repository now also includes an MT5 migration track that exports dashboard-compatible runtime JSON/CSV, plus a tightly constrained HFM Cent live pilot for `MA_Cross` at `0.01` lot while the rest of the MT5 execution engine is still being ported.

For HFM Cent live-account work, use the official HFM MT5 client at `C:\Program Files\HFM Metatrader 5`. The generic `C:\Program Files\MetaTrader 5` install may contain stale migration smoke data and should not be treated as the live-account source of truth.

## Default Mode

This repository is local-first by default.

- MT4 runs locally on Windows
- the dashboard reads the local `QuantGod_Dashboard.json`
- Cloudflare is optional and should stay off unless you explicitly need remote viewing

If you only want local research, you do not need any Cloudflare setup.

## What Changed In v2.6

- Added virtual research account mode with a default starting balance of `10 USD`
- Real demo execution now uses fixed micro-lots (`0.01`) for safer sampling
- Dashboard now shows research-account metrics first, with real broker-account values as reference
- Added a Node-based local dashboard server to avoid Windows file-lock issues from `python -m http.server`
- Added a one-click launcher for MT4 + dashboard

## Current Design Status

The onboarding information in this README is intentionally lightweight.

For the current implementation status, data-layer coverage, and the distinction between:

- already implemented
- partially implemented
- not implemented yet

see:

- `.codex/skills/quantgod-mt5-live-pilot/`

The repo-local skill is the durable operator guide for Codex-style maintenance work.

## MT5 Migration Status

The MT5 work is intentionally split into phases:

- Phase 1: available now
- `MQL5/Experts/QuantGod_MultiStrategy.mq5`
- exports `QuantGod_Dashboard.json`
- exports MT5 journaling CSVs for real-account observation
- supports a local-first launcher through `Start_QuantGod_MT5.bat`
- supports an HFM Cent shadow launcher through `Start_QuantGod_MT5_HFM_Shadow.bat`
- supports an HFM Cent live pilot launcher through `Start_QuantGod_MT5_HFM_LivePilot.bat`
- executes `MA_Cross` only in HFM live pilot mode with `0.01` lot, `M15` trigger + `H1` trend filter, one-position caps, hard `SL/TP`, kill switches, and a USD high-impact news filter
- includes HFM MT5 Backtest Lab V1 for `MA_Cross` on `EURUSDc` / `USDJPYc`, so strategy changes can be checked against both backtest evidence and live forward samples
- Phase 2: not done yet
- port the remaining strategy execution engines
- port adaptive controls and research statistics
- port trade labeling, linkage, and regime reports

Important: the current MT5 implementation is still a partial port. The only real-money automation currently enabled is the constrained HFM `MA_Cross` live pilot.

## Strategies

| # | Strategy | Description | Research Timeframe |
|---|----------|-------------|--------------------|
| 1 | MA_Cross | EMA(9/21) cross with higher-timeframe trend filter | M15 + H1 |
| 2 | RSI_Reversal | RSI extreme mean-reversion with Bollinger confirmation | H1 |
| 3 | BB_Triple | Bollinger + RSI + MACD confirmation | H1 |
| 4 | MACD_Divergence | Bullish / bearish divergence detection | H1 |
| 5 | SR_Breakout | Support / resistance breakout | M15 |

## Research Mode

- `VirtualStartingBalance`: `10`
- `VirtualRiskPercent`: `1%`
- `ResearchExecutionLot`: `0.01`
- `MaxDrawdownPercent`: `6%`
- `MaxTotalTrades`: `4`
- `IgnoreLegacyTradesInVirtualStats`: `true`

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
├─ MQL5/
│  └─ Experts/
│     └─ QuantGod_MultiStrategy.mq5
├─ Dashboard/
│  ├─ QuantGod_Dashboard.html
│  ├─ dashboard_server.js
│  └─ start_dashboard.bat
├─ Start_QuantGod.bat
└─ Start_QuantGod_MT5.bat
```

## MT4 Installation

Copy these files into your MT4 installation:

```text
MQL4/Experts/QuantGod_MultiStrategy.mq4  -> [MT4]/MQL4/Experts/
MQL4/Include/QuantEngine.mqh             -> [MT4]/MQL4/Include/
Dashboard/QuantGod_Dashboard.html        -> [MT4]/MQL4/Files/
Dashboard/dashboard_server.js            -> [MT4]/MQL4/Files/
Dashboard/start_dashboard.bat            -> [MT4]/MQL4/Files/
```

Compile `QuantGod_MultiStrategy.mq4` in MetaEditor after copying.

## MT5 Phase 1 Installation

Copy these files into your MT5 installation:

```text
MQL5/Experts/QuantGod_MultiStrategy.mq5  -> [MT5]/MQL5/Experts/
Dashboard/QuantGod_Dashboard.html        -> [MT5]/MQL5/Files/
Dashboard/dashboard_server.js            -> [MT5]/MQL5/Files/
```

Then compile `QuantGod_MultiStrategy.mq5` in MetaEditor64 and attach it to an MT5 chart.

Phase 1 now exports runtime snapshots plus broker-history journaling files for the dashboard/research layer:

- `QuantGod_TradeJournal.csv`
- `QuantGod_CloseHistory.csv`
- `QuantGod_TradeOutcomeLabels.csv`
- `QuantGod_TradeEventLinks.csv`
- `QuantGod_StrategyEvaluationReport.csv`
- `QuantGod_RegimeEvaluationReport.csv`

It still does not execute the full MT4 strategy set yet.

For HFM Cent live-account mode, the runtime export target is:

```text
C:\Program Files\HFM Metatrader 5\MQL5\Files\
```

That HFM directory is the correct live-account data source for the local dashboard.

## One-Click Startup

Recommended for MT4:

```bat
Start_QuantGod.bat
```

This will:

- start MT4
- start the local dashboard server
- keep Cloudflare sync off unless you explicitly create an enable file
- open `http://localhost:8080/QuantGod_Dashboard.html` with a cache-busting timestamp

For MT5 phase 1:

```bat
Start_QuantGod_MT5.bat
```

This will:

- sync the dashboard assets into `[MT5]/MQL5/Files/`
- sync the MT5 EA source into `[MT5]/MQL5/Experts/`
- sync the compiled `QuantGod_MultiStrategy.ex5` too, if it already exists in the repo
- start MT5
- use the official MT5 startup config mechanism to open `EURUSD M1` and auto-load `QuantGod_MultiStrategy`
- start the same local dashboard server against the MT5 files folder
- open the dashboard with a cache-busting timestamp

For HFM Cent read-only shadow mode:

```bat
Start_QuantGod_MT5_HFM_Shadow.bat
```

This will:

- sync the dashboard assets into `C:\Program Files\HFM Metatrader 5\MQL5\Files\`
- sync the MT5 skeleton EA and preset into the HFM client
- restart the official HFM MT5 client in read-only shadow mode
- keep strategy execution disabled while still exporting your real account, symbol, and open-position runtime
- start the local dashboard server against the HFM files folder
- open the dashboard with a cache-busting timestamp

For HFM Cent controlled live pilot mode:

```bat
Start_QuantGod_MT5_HFM_LivePilot.bat
```

This will:

- sync the dashboard assets into `C:\Program Files\HFM Metatrader 5\MQL5\Files\`
- sync the MT5 EA source, compiled `ex5`, and live pilot preset into the HFM client
- restart the official HFM MT5 client in live pilot mode
- arm `MA_Cross` only with `0.01` lot, `M15` trigger + `H1` trend filter, one-position caps, hard `SL/TP`, kill switches, USD high-impact news pre/post blocks, and post-release directional bias
- keep `USDJPYc` blocked if you already have a manual position on that symbol
- start the local dashboard server against the HFM files folder
- open the dashboard with a cache-busting timestamp

For HFM MT5 Backtest Lab V1:

```bat
Start_QuantGod_MT5_HFM_BacktestLab.bat
```

This prepares MT5 Strategy Tester configs for:

- `MA_Cross`
- `EURUSDc` and `USDJPYc`
- `0.01` lot only
- `M15` trigger with `H1` trend filter

By default it does not interrupt the live HFM terminal. It writes a local summary to:

```text
archive/backtests/latest/QuantGod_BacktestSummary.json
```

and copies that summary to the HFM Files folder so the dashboard can render the `回测 vs 实盘` comparison card.

If you intentionally want to launch the HFM MT5 Strategy Tester, run:

```powershell
powershell -ExecutionPolicy Bypass -File .\tools\run_mt5_backtest_lab.ps1 -RunTerminal
```

Strategy changes should now pass both checks before loosening risk:

- backtest evidence supports the idea
- live `0.01` forward samples do not contradict it

## MT4 Data Retention

Before deleting the MT4 install, archive the research assets into the repo-local archive area:

```powershell
powershell -ExecutionPolicy Bypass -File .\tools\archive_mt4_runtime.ps1
```

This creates a local snapshot under:

```text
archive/mt4-runtime-snapshots/
```

The snapshot folder is intentionally ignored by Git so the large private runtime datasets stay local by default.

If you only want the dashboard server:

```bat
Dashboard\start_dashboard.bat
```

## Optional Cloudflare Deployment

Cloudflare is not part of the default local workflow.

Only use this if you explicitly want a remote dashboard and understand that it adds external requests and quota usage.

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

If you do not want to rely on MT4 WebRequest allowlist handling, use the local uploader.

This is still opt-in. It will stay off unless you manually create the enable file:

- copy `Dashboard/cloud_sync_uploader.ps1` into `[MT4]/MQL4/Files/`
- create `[MT4]/MQL4/Files/quantgod_cloud_sync.enabled.json`
- `Start_QuantGod.bat` will auto-start the uploader only when that file exists

If you want to force local-only mode, make sure `quantgod_cloud_sync.enabled.json` does not exist.

## Dashboard

The dashboard shows:

- virtual research balance / equity / floating P&L / drawdown
- real broker-account balance / equity as reference
- per-symbol grouped strategy status
- open trades and closed trades
- research equity curve
- strategy profit distribution
- daily research P&L

In MT5 phase 1, the same dashboard renders from MT5 runtime files, but strategy evaluation and regime panels remain placeholder-only until the MT5 execution/statistics layers are ported.

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
