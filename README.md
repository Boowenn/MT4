# QuantGod Multi-Strategy Trading Engine

MT4 quantitative trading system with 5 strategies, a Chinese real-time dashboard, and a virtual small-account research mode.

The repository now also includes an MT5 migration track that exports dashboard-compatible runtime JSON/CSV, plus a tightly constrained HFM Cent live pilot at `0.01` lot. `MA_Cross` and the old strong `USDJPY RSI_Reversal H1` slice are the current real-money routes in the live preset. The old MT4 `BB_Triple`, `MACD_Divergence`, and `SR_Breakout` routes remain candidate/backtest routes until their iterated versions show enough evidence for live promotion. If a demoted route still has an old live pilot position, the EA exits it at breakeven or profit and also cuts it at a small demoted-route loss threshold instead of waiting for the original TP/SL.

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
- executes `MA_Cross` in HFM live pilot mode with `0.01` lot, `M15` trigger + `H1` trend filter, a 5-bar fresh-crossover lookback plus 24-bar pullback-continuation window, one-position caps, hard `SL/TP`, kill switches, a USD high-impact news filter, a 180-minute auto-resume cooldown after consecutive-loss pauses, and a demoted-route exit guard for old live positions whose route has since been returned to candidate/simulation
- ports the old MT4 `RSI_Reversal`, `BB_Triple`, `MACD_Divergence`, and `SR_Breakout` signal routes into MT5 as candidate/backtest/live-gated routes; the shipped HFM live preset enables `USDJPY RSI_Reversal H1` only among legacy routes, while `BB_Triple`, `MACD_Divergence`, and `SR_Breakout` stay candidate/backtest-only for iteration
- includes HFM MT5 Backtest Lab V1 for `MA_Cross` plus tester presets that can validate the legacy routes on `EURUSDc` / `USDJPYc`, so strategy changes can be checked against both backtest evidence and live forward samples
- includes an offline Param Optimization Plan for `RSI_Reversal`, `BB_Triple`, `MACD_Divergence`, and `SR_Breakout`; it proposes candidate parameter sets and Strategy Tester tasks, then feeds the top candidate back into Governance Advisor for ranking without mutating the live preset
- includes a controlled ParamLab Runner that materializes the ranked candidates into tester-only `.set` and `.ini` files, records `QuantGod_ParamLabStatus.json`, and only launches MT5 Strategy Tester when explicitly run with the Strategy Tester authorization flags
- includes a ParamLab Results Parser that scans ParamLab archives after Strategy Tester has produced reports, writes `QuantGod_ParamLabResults.json` / `QuantGod_ParamLabResultsLedger.csv`, scores each parameter version by PF, win rate, net profit, trade count, and drawdown, then feeds those scores back into Governance Advisor
- includes a Strategy Version Registry that writes `QuantGod_StrategyVersionRegistry.json` / `QuantGod_StrategyVersionRegistry.csv`, turning each MA/RSI/BB/MACD/SR route into a stable parameter-version record with a hash, live/candidate status, evidence, and tester-only child lineage
- includes Optimizer V2, which writes `QuantGod_OptimizerV2Plan.json` / `QuantGod_OptimizerV2Ledger.csv`; it proposes version-linked next-generation parameters for MA/RSI/BB/MACD/SR by combining live forward, candidate outcomes, ParamLab scores, and Governance actions, but remains tester-only and never mutates the HFM live preset
- includes a read-only Dashboard ParamLab batch panel that turns `QuantGod_ParamLabStatus.json` and `QuantGod_ParamLabResults.json` into an execution queue view: `可在授权窗口运行`, `已运行`, `等待报告`, and `已评分`, with one-click status/route filters, queue sorting, and the matching tester-only command plus report/config paths visible before weekend Strategy Tester sessions
- includes a read-only Dashboard Strategy Workspace that gives `MA_Cross`, `RSI_Reversal`, `BB_Triple`, `MACD_Divergence`, and `SR_Breakout` their own route cards with live/candidate authority, forward samples, candidate outcomes, ParamLab state, scored parameter versions, blockers, and the next Governance Advisor action
- includes a structured AI/Governance Feedback layer in `QuantGod_GovernanceAdvisor.json` plus a Dashboard panel that explains, per route, why the Advisor recommends keep/demote/iterate/promote, where the risks are, which parameter tests should run next, and the matching ParamLab candidate/task/report status plus one-click copy buttons for tester-only commands and report paths
- includes a Shadow Signal Ledger that records every M15 pilot evaluation, signal, and blocked opportunity into `QuantGod_ShadowSignalLedger.csv` for faster learning without increasing live risk
- includes a Shadow Outcome Ledger that labels those shadow events after 15/30/60 minutes in `QuantGod_ShadowOutcomeLedger.csv`, so range-blocked and no-trade opportunities can be judged by post-outcome evidence before any route change
- includes Shadow Candidate Router V1, a research layer that records MA continuation/range-soft candidates plus RSI, Bollinger, MACD, and support/resistance route candidates without enabling new live routes by default
- includes a Manual Alpha Ledger that turns manual trades such as XAUUSDc into learn-only route candidates without automatically expanding EA execution
- Phase 2: not done yet
- port the full adaptive controls and research statistics around the newly ported MT5 strategy routes
- port adaptive controls and research statistics
- port trade labeling, linkage, and regime reports

Important: the current MT5 implementation is still a partial port. In the shipped HFM live preset, real-money automation is limited to constrained `MA_Cross` plus `USDJPY RSI_Reversal H1`. `BB_Triple H1`, `MACD_Divergence H1`, and `SR_Breakout M15` are candidate/backtest iteration routes and cannot send live orders unless their explicit live switch is re-enabled after evidence improves.

Live route promotion and demotion are now evidence-driven automation decisions. A live route can be demoted quickly when its recent `0.01` forward results, order-send health, or shadow/candidate outcomes show weakness; it then stays in simulation/backtest and is iterated there. A candidate route can be promoted back to live only after old-history context, Backtest Lab, candidate/outcome ledgers, and fresh `0.01` forward-style evidence show a stable edge without obvious risk objections. Promotion never changes the lot size, account, server, single-symbol cap, hard SL/TP, spread/session/news/cooldown/portfolio/order-send controls, or kill switches. Consecutive-loss pauses are not permanent: the HFM live preset keeps `PilotMaxConsecutiveLosses=2` but now waits `PilotConsecutiveLossPauseMinutes=180` before automatically allowing the next guarded `0.01` evaluation. Daily realized-loss and floating-loss kill switches remain hard pauses.

The repo also includes a QuantDinger-inspired local Governance Advisor and light dashboard shell. It borrows the useful product ideas of a strategy lifecycle view, a clean app-style sidebar/header, a health snapshot with file freshness/circuit-style evidence states, an offline parameter-candidate loop, explicit strategy snapshots, and version-aware optimizer proposals. QuantGod's broker boundary stays intact: `tools/build_param_optimization_plan.py` writes `QuantGod_ParamOptimizationPlan.json`, `tools/run_param_lab.py` prepares tester-only ParamLab tasks and writes `QuantGod_ParamLabStatus.json`, `tools/collect_param_lab_results.py` parses completed tester reports into `QuantGod_ParamLabResults.json`, `tools/build_strategy_version_registry.py` writes versioned strategy records, `tools/build_optimizer_v2_plan.py` writes tester-only next-generation proposals, then `tools/build_governance_advisor.py` reads local HFM Files evidence and writes `QuantGod_GovernanceAdvisor.json` for dashboard review. These tools are read-only with respect to live trading: they never store credentials, open live positions, overwrite the live preset, or bypass the existing EA `OrderSend` guards. ParamLab can launch Strategy Tester only when explicitly called with `--run-terminal --authorized-strategy-tester`, and the default path is config-only.

The dashboard home Route Watchlist and the Strategy Workspace tabs are the main strategy focus controls. Clicking `MA`, `RSI`, `BB`, `MACD`, or `SR` filters the evidence cards, strategy workspace, strategy cards, regime research, and charts to that route; clicking `All routes` returns to the full-system view. This is a read-only review filter and does not change live switches or EA execution permissions.

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
- `QuantGod_GovernanceAdvisor.json` when the local governance builder has been run

It still does not port the full MT4 adaptive/research-statistics layer yet, but the legacy MT4 signal routes now exist in MT5 as candidate/backtest/live-gated evaluators.

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
- refresh `QuantGod_GovernanceAdvisor.json` from the latest local HFM runtime evidence when possible
- sync the MT5 EA source, compiled `ex5`, and live pilot preset into the HFM client
- restart the official HFM MT5 client in live pilot mode
- arm `MA_Cross` with `0.01` lot, `M15` trigger + `H1` trend filter, a 5-bar fresh-crossover lookback plus 24-bar pullback-continuation window, one-position caps, hard `SL/TP`, kill switches, a 180-minute auto-resume cooldown after consecutive-loss pauses, USD high-impact news pre/post blocks, and post-release directional bias
- load the legacy MT4 route ports with `USDJPY RSI_Reversal H1` live-gated on; `BB_Triple H1`, `MACD_Divergence H1`, and `SR_Breakout M15` remain candidate/backtest-only until their iterated versions meet live promotion criteria
- keep manual positions protected by the safety guard across all symbols, including XAUUSDc, while keeping them separate from EA pilot positions; manual trades no longer block same-symbol EA entries or count as EA research samples
- append Shadow Signal Ledger rows for each new M15 pilot evaluation, including signal, no-signal, range/spread/session/news/cooldown blocks, and order-send outcomes
- export Shadow Outcome Ledger rows for completed 15/30/60 minute horizons from the Shadow Signal Ledger; this is analysis-only and never changes live entry rules
- export Shadow Candidate Router V1 rows into `QuantGod_ShadowCandidateLedger.csv` plus 15/30/60 minute post-outcomes into `QuantGod_ShadowCandidateOutcomeLedger.csv`; candidates are shadow-only and cannot send orders
- export Manual Alpha Ledger rows for manual open/closed trades, including symbol, side, regime transition, duration, floating/realized profit, and learn-only status
- start the local dashboard server against the HFM files folder
- open the dashboard with a cache-busting timestamp

For HFM MT5 Backtest Lab V1:

```bat
Start_QuantGod_MT5_HFM_BacktestLab.bat
```

This prepares MT5 Strategy Tester configs for:

- `MA_Cross`
- `RSI_Reversal` H1, especially the old strong `USDJPY` slice
- `BB_Triple` H1
- `MACD_Divergence` H1
- `SR_Breakout` M15
- `EURUSDc` and `USDJPYc`
- `0.01` lot only
- `M15` / `H1` route timing, including the MA pilot plus legacy-route tester switches

By default it does not interrupt the live HFM terminal. It writes a local summary to:

```text
archive/backtests/latest/QuantGod_BacktestSummary.json
```

For the offline parameter-candidate loop:

```bat
tools\build_governance_advisor.bat
```

This first writes `QuantGod_ParamOptimizationPlan.json` under HFM Files, then rebuilds `QuantGod_GovernanceAdvisor.json`. The plan ranks `RSI_Reversal`, `BB_Triple`, `MACD_Divergence`, and `SR_Breakout` parameter candidates and emits pending Strategy Tester tasks. It does not launch MT5, copy anything into the live preset, or change real order permissions.

To materialize the ranked candidates into tester-only presets/configs without launching MT5:

```bat
tools\run_param_lab.bat --max-tasks 4
```

This writes `QuantGod_ParamLabStatus.json` under HFM Files and archives generated tester configs under `archive\param-lab\runs\`. The default selection is route-balanced, so RSI/BB/MACD/SR each get a top candidate before extra slots are filled by score. It may copy ParamLab candidate presets into the HFM `MQL5\Presets` folder for Strategy Tester use, but it does not overwrite `QuantGod_MT5_HFM_LivePilot.set`. To actually launch Strategy Tester, use the same command with `--run-terminal --authorized-strategy-tester` only in the authorized tester window or explicitly authorized session.

After Strategy Tester reports exist, collect and score parameter-version results:

```bat
tools\collect_param_lab_results.bat
tools\build_strategy_version_registry.bat
tools\build_optimizer_v2_plan.bat
tools\build_governance_advisor.bat
```

The parser writes `QuantGod_ParamLabResults.json` and `QuantGod_ParamLabResultsLedger.csv`, then annotates `QuantGod_ParamOptimizationPlan.json` with `resultScore`, `grade`, `promotionReadiness`, PF, win rate, net profit, trade count, and drawdown. `build_strategy_version_registry.bat` then snapshots each route into a stable parameter version, and `build_optimizer_v2_plan.bat` proposes the next tester-only generation against those parent versions. Pending reports remain `PENDING_REPORT` and do not count as promotion evidence.

and copies that summary to the HFM Files folder so the dashboard can render the `回测 vs 实盘` comparison card. A no-terminal config-only run archives its own `CONFIG_READY` summary under `archive/backtests/runs/`, but it does not overwrite the latest effective tester result already published to HFM Files.

If you intentionally want to launch the HFM MT5 Strategy Tester, run:

```powershell
powershell -ExecutionPolicy Bypass -File .\tools\run_mt5_backtest_lab.ps1 -RunTerminal
```

Strategy changes should now pass both checks before loosening risk:

- backtest evidence supports the idea
- live `0.01` forward samples do not contradict it

Shadow Signal Ledger:

- `QuantGod_ShadowSignalLedger.csv` is a no-trade, append-only learning surface.
- It records M15 MA_Cross evaluations even when no real order is placed.
- It lets the dashboard compare real closed trades with blocked opportunities, so range/news/spread/session guards can be reviewed with more evidence before any future strategy change.
- `QuantGod_ShadowOutcomeLedger.csv` labels completed 15/30/60 minute horizons from those shadow events, including close move, MFE/MAE, directional outcome, and best long/short opportunity.
- `QuantGod_ShadowCandidateLedger.csv` and `QuantGod_ShadowCandidateOutcomeLedger.csv` track shadow-only route candidates before any backtest or live pilot expansion.
- V1 candidate routes include `TREND_CONT_NO_CROSS`, `USDJPY_PULLBACK_BOUNCE`, `RANGE_SOFT`, `RSI_REVERSAL_SHADOW`, `BB_TRIPLE_SHADOW`, `MACD_MOMENTUM_TURN`, and `SR_BREAKOUT_SHADOW`.
- Candidate Router V1.1 adds soft shadow triggers for trend continuation, RSI reversal, MACD histogram turns, and near support/resistance breakouts to increase sample speed without changing live `OrderSend` gating.
- Candidate Router V1.2 keeps live entries unchanged while applying the 2026-04-25 evidence pass: `USDJPY_PULLBACK_BOUNCE` receives stricter low-spread Manual Alpha inspired samples, `RSI_REVERSAL_SHADOW` is limited to low-spread range regimes, and weak post-outcome routes (`RANGE_SOFT`, `MACD_MOMENTUM_TURN`, `SR_BREAKOUT_SHADOW`) are lower-score and require stronger confirmation.
- Legacy Route Port V1 adds executable MT5 signal evaluation for the old MT4 `RSI_Reversal`, `BB_Triple`, `MACD_Divergence`, and `SR_Breakout` routes. The live preset enables only `USDJPY RSI_Reversal H1` among legacy routes; BB/MACD/SR stay candidate/backtest-only while their stricter confirmation rules are iterated.
- It must not be used by itself to loosen risk; it is an additional evidence layer beside Backtest Lab and live `0.01` forward outcomes.

News Filter Visibility:

- `QuantGod_Dashboard.json` exports USD news filter status, MT5 event code/kind/label, event server time, countdown, tracked USD event count, block/bias state, and the current reason.
- The dashboard execution radar surfaces the current USD news filter state and next tracked event so operators can see why `NEWS_BLOCK` is active before it affects live pilot entries.

Manual Alpha Ledger:

- `QuantGod_ManualAlphaLedger.csv` records manual open and closed trades as learn-only examples.
- A strong manual trade can become a route candidate, but it cannot directly add a symbol, strategy, or lot size to EA execution.
- To promote a manual idea into automation, first create a shadow-only route, then require Shadow Ledger evidence, Backtest Lab support, and live `0.01` forward samples that do not refute it.

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
- a Strategy Workspace for MA/RSI/BB/MACD/SR that combines route authority, forward samples, ParamLab batch/result state, blockers, and Governance Advisor next steps without launching MT5 or changing live presets
- a Strategy Version Registry + Optimizer V2 panel that shows current route versions, parameter hashes, tester-only child versions, and the next version-linked optimizer proposal for each route
- an AI/Governance Feedback panel that turns each route action into `why / risk / next parameter tests`, with each parameter suggestion linked to candidate/task/report state and copyable tester-only commands/report paths so operators can prepare weekend tester runs without touching live settings
- per-symbol grouped strategy status
- open trades and closed trades
- research equity curve
- strategy profit distribution
- daily research P&L

In MT5 phase 1, the same dashboard renders from MT5 runtime files. `MA_Cross` and `USDJPY RSI_Reversal H1` are the current live routes, while `BB_Triple`, `MACD_Divergence`, and `SR_Breakout` expose candidate/backtest status for iteration instead of remaining pure placeholders.

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
