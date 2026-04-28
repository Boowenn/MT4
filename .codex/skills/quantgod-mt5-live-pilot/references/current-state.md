# QuantGod MT5 Live Pilot: Current Stable Map

## Purpose

Use this reference when working on the QuantGod repository so you do not need to rediscover where execution, statistics, presentation, and migration scaffolding live.

Keep this file stable. Put durable architecture and workflow facts here. Do not turn it into a hand-maintained snapshot of changing row counts.

Repository workflow:

- Codex-made changes should not remain local-only after verification. For code, configuration, dashboard, documentation, or automation edits, run the relevant self-tests/compile/syntax checks, then commit and push to GitHub `main` when those checks pass.
- Do not auto-push unverified changes or changes that intentionally remain experimental.

## Source of Truth Order

When project knowledge conflicts:

1. Runtime exports under `C:\Program Files\HFM Metatrader 5\MQL5\Files\`
2. Current MT5 live-pilot behavior in `MQL5/Experts/QuantGod_MultiStrategy.mq5`
3. Dashboard and local server rendering in `Dashboard/QuantGod_Dashboard.html` and `Dashboard/dashboard_server.js`
4. MT5 launch/config files such as `MQL5/Config/QuantGod_MT5_HFM_LivePilot.ini` and `MQL5/Presets/QuantGod_MT5_HFM_LivePilot.set`
5. Human-facing notes such as `README.md`

Use HFM MT5 runtime files for live counts, recent trades, pilot telemetry, and latest execution states.
Treat `QuantGod_GovernanceAdvisor.json`, `QuantGod_StrategyVersionRegistry.json`, `QuantGod_OptimizerV2Plan.json`, `QuantGod_VersionPromotionGate.json`, `QuantGod_ParamLabAutoScheduler.json`, `QuantGod_AutoTesterWindow.json`, `QuantGod_ParamLabRunRecovery.json`, and `QuantGod_ParamLabReportWatcher.json` as derived advisory/control-state snapshots from those files, not as direct live execution sources.
Do not assume the generic `C:\Program Files\MetaTrader 5\MQL5\Files\` directory is current for HFM live-account validation.
Treat MT4 as archive-only. If you need old MT4 evidence later, preserve or inspect it through `tools/archive_mt4_runtime.ps1` and `archive/mt4-runtime-snapshots/`, not as the current live source.

## Core Runtime Layers

### MT5 Live Pilot and HFM Runtime

- `MQL5/Experts/QuantGod_MultiStrategy.mq5`
- `MQL5/Config/QuantGod_MT5_Start.ini`
- `Start_QuantGod_MT5.bat`
- `MQL5/Config/QuantGod_MT5_HFM_Shadow.ini`
- `Start_QuantGod_MT5_HFM_Shadow.bat`
- `MQL5/Config/QuantGod_MT5_HFM_LivePilot.ini`
- `MQL5/Presets/QuantGod_MT5_HFM_LivePilot.set`
- `Start_QuantGod_MT5_HFM_LivePilot.bat`
- `tools/build_governance_advisor.py`
- `tools/build_governance_advisor.bat`
- `tools/build_strategy_version_registry.py`
- `tools/build_strategy_version_registry.bat`
- `tools/build_optimizer_v2_plan.py`
- `tools/build_optimizer_v2_plan.bat`

Responsibilities:

- Export an MT5 `QuantGod_Dashboard.json` with a dashboard-compatible shape
- Export MT5 broker-history journaling files such as `QuantGod_TradeJournal.csv`, `QuantGod_CloseHistory.csv`, `QuantGod_TradeOutcomeLabels.csv`, and `QuantGod_TradeEventLinks.csv`
- Export MT5 evaluation files such as `QuantGod_StrategyEvaluationReport.csv`, `QuantGod_RegimeEvaluationReport.csv`, and `QuantGod_OpportunityLabels.csv`
- Export `QuantGod_ShadowSignalLedger.csv` as an append-only, no-trade sample ledger for each new M15 `MA_Cross` pilot evaluation, including signals, no-cross observations, blockers, and order-send outcomes
- Export `QuantGod_ShadowOutcomeLedger.csv` as a no-trade post-outcome ledger that labels completed 15/30/60 minute horizons from Shadow Signal Ledger rows, including close move, MFE/MAE, directional outcome, and best long/short opportunity
- Export `QuantGod_ShadowCandidateLedger.csv` and `QuantGod_ShadowCandidateOutcomeLedger.csv` for Shadow Candidate Router V1.1, covering MA continuation/range-soft, RSI reversal, Bollinger reversal, MACD momentum turn, and support/resistance breakout candidates as shadow-only route hypotheses; soft shadow triggers intentionally increase trend-continuation, RSI, MACD, and support/resistance sample speed without changing live `OrderSend` gating
- Export `QuantGod_ManualAlphaLedger.csv` as a learn-only ledger for manual open/closed trades, including current XAUUSDc-style discretionary trades, so strong human entries can be studied without expanding EA permissions
- Reuse the existing dashboard assets against the active MT5 terminal files directory
- Reuse the existing dashboard assets against `C:\Program Files\HFM Metatrader 5\MQL5\Files\` for the HFM Cent live-account runtime path
- Use the official MT5 startup config mechanism to auto-open `EURUSD M1` and auto-load the phase 1 skeleton at terminal launch
- Run a constrained HFM Cent live pilot with `MA_Cross` enabled by default, `0.01` lot, `M15` trigger + `H1` trend filter, a 5-bar fresh-crossover lookback window plus a 24-bar pullback-continuation entry window after recent crosses, pilot-only one-position caps, hard `SL/TP`, kill switches, a same-symbol post-loss cooldown, a range-regime entry block, a 180-minute auto-resume cooldown after consecutive-loss pauses, breakeven plus trailing-stop profit protection for eligible profitable EA positions, conservative SL/max-loss/trailing safety protection for manual positions across all symbols, and a USD high-impact news filter driven by the MT5 economic calendar. Manual positions are protected but separate; they do not block same-symbol EA entries or pollute EA strategy statistics.
- Port the old MT4 `RSI_Reversal`, `BB_Triple`, `MACD_Divergence`, and `SR_Breakout` routes into MT5 as candidate/backtest/live-gated signal evaluators. The shipped HFM live preset enables only `USDJPY RSI_Reversal H1` among legacy routes. `BB_Triple`, `MACD_Divergence`, and `SR_Breakout` stay candidate/backtest-only while their stricter confirmation rules are iterated; Strategy Tester presets still validate the same route family in controlled backtests. If a live route is demoted while an old pilot position still exists, the demoted-route exit guard closes it at breakeven/profit or at the small demoted-route loss threshold rather than waiting for the old TP/SL.
- Provide Backtest Lab V1 for the constrained `MA_Cross` baseline plus the legacy route tester switches: generate MT5 Strategy Tester configs and presets for `EURUSDc` / `USDJPYc`, archive run artifacts under `archive/backtests/`, and publish `QuantGod_BacktestSummary.json` so the dashboard can compare backtest support against live forward samples
- Provide an offline Param Optimization Plan for `RSI_Reversal`, `BB_Triple`, `MACD_Divergence`, and `SR_Breakout`: propose candidate parameter sets and pending Strategy Tester tasks in `QuantGod_ParamOptimizationPlan.json`, then feed the top candidate per route into Governance Advisor. This is parameter review only and must not mutate the HFM live preset automatically.
- Provide a controlled ParamLab Runner for those offline candidates: `tools/run_param_lab.py` materializes ranked candidates into tester-only `.set` and `.ini` files, archives them under `archive/param-lab/runs/`, writes `QuantGod_ParamLabStatus.json`, and can parse reports back into the plan after an authorized Strategy Tester run. Its default mode is config-only, it must not overwrite the live preset, and direct `--run-terminal` is blocked unless AUTO_TESTER_WINDOW lock/window/profile/config validation passes.
- Provide a ParamLab Report Watcher for completed tester reports: `tools/watch_param_lab_reports.py` scans ParamLab run archives and known report paths, parses PF, win rate, net profit, trade count, max drawdown, relative drawdown, writes `QuantGod_ParamLabReportWatcher.json`, updates `QuantGod_ParamLabResults.json` plus `QuantGod_ParamLabResultsLedger.csv`, and annotates `QuantGod_ParamOptimizationPlan.json` plus the Auto Scheduler queue with result scores. Pending or malformed reports stay advisory rows and cannot promote a route.
- Provide a Strategy Version Registry for `MA_Cross`, `RSI_Reversal`, `BB_Triple`, `MACD_Divergence`, and `SR_Breakout`: `tools/build_strategy_version_registry.py` writes `QuantGod_StrategyVersionRegistry.json` plus `QuantGod_StrategyVersionRegistry.csv`, records the current parameter hash, live/candidate state, evidence, and tester-only child versions for each route, and never mutates the HFM live preset.
- Provide Optimizer V2 for version-aware offline iteration: `tools/build_optimizer_v2_plan.py` writes `QuantGod_OptimizerV2Plan.json` plus `QuantGod_OptimizerV2Ledger.csv`, proposes next-generation tester-only parameters from structured route spaces, links each proposal to a parent version, and never launches MT5 or changes live execution permissions.
- Provide ParamLab Auto Scheduler for config-only queueing: `tools/build_param_lab_auto_scheduler.py` writes `QuantGod_ParamLabAutoScheduler.json` plus `QuantGod_ParamLabAutoSchedulerLedger.csv`, translates Gate `WAIT_REPORT`, `RETUNE`, and `WAIT_FORWARD` decisions into ParamLab-compatible `backtestTasks`, and never adds `-RunTerminal` by default.
- Provide AUTO_TESTER_WINDOW for guarded Strategy Tester execution: `tools/run_param_lab_auto_tester_window.py` writes `QuantGod_AutoTesterWindow.json` plus `QuantGod_AutoTesterWindowLedger.csv`, evaluates the authorized tester window, `QuantGod_AutoTesterWindow.lock.json`, tester-only scheduler queue, HFM terminal/profile root, generated ParamLab config, report path, lot size, and position caps. It defaults to evaluation-only and is the only supported bridge for `--run-terminal`.
- Provide ParamLab Run History / Recovery: `tools/build_param_lab_run_recovery.py` writes `QuantGod_ParamLabRunRecovery.json`, `QuantGod_ParamLabRunRecoveryLedger.csv`, and `QuantGod_ParamLabRunRecoveryDrilldown.csv`, summarizing guarded/config runs by runId, terminal exit code, report missing/parsed/malformed state, retry count, stop reason, and recovery action, then aggregating each candidate into red/yellow/green retry-budget and failure-reason drilldown. It is read-only and never launches MT5.
- Provide Shadow Signal Ledger for the same constrained `MA_Cross` research path so blocked and non-traded M15 opportunities become reviewable evidence without increasing live risk
- Provide Shadow Outcome Ledger so range-blocked and no-trade M15 opportunities gain post-outcome labels before anyone considers a shadow-only route change
- Provide Shadow Candidate Router V1 so candidate routes can be compared by post-outcome evidence before they are eligible for Backtest Lab review
- Provide Manual Alpha Ledger as a separate learning surface for discretionary trades; promotion from manual alpha to EA automation requires a later shadow-only route plus backtest and live-forward validation
- Provide a QuantDinger-inspired Governance Advisor, Strategy Version Registry, Optimizer V2, Version Promotion Gate, ParamLab Auto Scheduler, AUTO_TESTER_WINDOW, Run History / Recovery, Report Watcher, and light dashboard shell as a local lifecycle snapshot. It combines Backtest Lab, live `0.01` forward results, Shadow Signal/Outcome, Shadow Candidate/Outcome, Manual Alpha, runtime file-health evidence, parameter hashes, version-linked tester-only optimizer proposals, dry-run promotion/demotion recommendations, config-only tester queues, guarded tester-window readiness, run recovery state, and landed Strategy Tester reports into `QuantGod_GovernanceAdvisor.json`, `QuantGod_StrategyVersionRegistry.json`, `QuantGod_OptimizerV2Plan.json`, `QuantGod_VersionPromotionGate.json`, `QuantGod_ParamLabAutoScheduler.json`, `QuantGod_AutoTesterWindow.json`, `QuantGod_ParamLabRunRecovery.json`, and `QuantGod_ParamLabReportWatcher.json`; it never connects to HFM for live orders, stores credentials, sends orders, mutates the HFM live preset, adds `-RunTerminal` by default, or bypasses EA `OrderSend` gating. ParamLab run-terminal execution requires the explicit lock/window/profile/config guard.
- Surface the MT5 USD news filter state in `QuantGod_Dashboard.json` and the dashboard execution radar, including event code/kind/label, countdown, server event time, tracked-event count, block state, and bias state

Non-responsibilities in phase 1:

- It does not execute the full five-strategy MT4 research engine
- It does not port adaptive controls
- It does not port research-account statistics, trade linkage, or regime evaluation
- Its MT5 evaluation/regime exports currently describe broker-history journaling and inferred labels, not a fully ported QuantGod execution-quality model

### Presentation Layer

- `Dashboard/QuantGod_Dashboard.html`
- `Dashboard/dashboard_server.js`

Responsibilities:

- Read `QuantGod_Dashboard.json`
- Read evaluation and labeling CSVs
- Render per-symbol and per-strategy status
- Render the regime research heatmap from `QuantGod_RegimeEvaluationReport.csv`
- Render advisory research recommendations derived from `strategy x symbol x regime` slices
- Render a server-time `昨晚 vs 今天` research summary card in the overview section, using `昨晚 20:00 -> 今天 08:00` versus `今天 08:00 -> 现在`
- Surface both closed-trade outcomes and window-scoped new opens on that summary card, so operators can see when the current day has started trading but has not produced exits yet
- Expose a left-navigation section layout so operators can jump between overview, monitor, trades, research, and reports
- In the trades section, render the HFM MT5 journal surface from `QuantGod_TradeJournal.csv`, `QuantGod_CloseHistory.csv`, `QuantGod_TradeOutcomeLabels.csv`, and `QuantGod_TradeEventLinks.csv`, including explicit empty states when the live account has not closed a trade yet
- In the overview section, render the Shadow Signal Ledger summary from `QuantGod_ShadowSignalLedger.csv` plus the Shadow Outcome/Candidate summaries from `QuantGod_ShadowOutcomeLedger.csv`, `QuantGod_ShadowCandidateLedger.csv`, and `QuantGod_ShadowCandidateOutcomeLedger.csv`, so sample speed, signal count, dominant blockers, range-blocked post-outcomes, and candidate route post-outcomes are visible beside backtest and live evidence
- In the overview section, render the Manual Alpha Ledger summary from `QuantGod_ManualAlphaLedger.csv`, so manual open/closed alpha is visible as route-candidate evidence without mixing it into EA statistics
- In the monitor section, each HFM symbol card now also renders a `Pilot 命中率` block from `symbols[].pilotTelemetry`, so operators can inspect daily evaluations, signal hits, WAIT_BAR frequency, no-crossover misses, news blocks, and order-send outcomes without opening raw JSON
- Reuse the same recommendation layer inside the strategy evaluation table so the live row for each current slice shows its current research action
- Reuse the same recommendation layer inside the symbol overview strategy chips so operators can see each live `strategy x symbol` slice's current action without leaving the monitoring section
- Let operators expand each symbol overview strategy chip to inspect the matched `strategy x symbol x regime` slice, sample metrics, and whether the displayed action came from an exact match or a fallback rule
- Let operators jump from that provenance panel directly into the research suggestion panel or the regime heatmap, with symbol filter sync and visual focus on the matching slice when available
- Let operators jump back from research suggestion cards and regime heatmap cells into the monitor section, where the corresponding symbol card and strategy chip are visually focused for fast cross-checking
- Explain that monitor-section focus with a breadcrumb, so the operator can tell whether the current highlight came from a research suggestion card or from a heatmap cell
- Render the Governance Advisor overview card from `QuantGod_GovernanceAdvisor.json`, showing route lifecycle actions, live-forward stats, candidate outcome evidence, open-position pressure, blockers, and guardrail reminders
- Render a read-only ParamLab batch panel from Governance Advisor's `ParamLabStatus` and `ParamLabResults` summaries, showing which tester-only parameter tasks are ready for an authorized Strategy Tester window, which have run, which are waiting for reports, and which are already scored. The panel has one-click status/route filters and queue sorting, may display suggested commands and report/config paths, but must not launch MT5 or mutate the live preset from the browser.
- Render a read-only Strategy Workspace for `MA_Cross`, `RSI_Reversal`, `BB_Triple`, `MACD_Divergence`, and `SR_Breakout`, giving each route an independent card with live/candidate authority, forward samples, candidate outcomes, ParamLab batch/result state, blockers, and Governance Advisor next steps. The workspace can focus dashboard evidence by route, but it must not launch MT5, mutate live presets, or change EA execution permissions.
- Render a read-only Strategy Version Registry + Optimizer V2 + Version Promotion Gate panel from `QuantGod_StrategyVersionRegistry.json`, `QuantGod_OptimizerV2Plan.json`, and `QuantGod_VersionPromotionGate.json`, showing current version IDs, parameter hashes, child candidate versions, result readiness, the top tester-only next-generation proposal, and the dry-run promotion/demotion decision per route.
- Render a read-only ParamLab Auto Scheduler panel from `QuantGod_ParamLabAutoScheduler.json`, showing the next config-only tester queue selected from Gate `WAIT_REPORT`, `RETUNE`, and `WAIT_FORWARD`, including route priority, parameter summary, gate reason, report hint, and copyable config-only command.
- Render a read-only AUTO_TESTER_WINDOW panel from `QuantGod_AutoTesterWindow.json`, showing whether Strategy Tester execution is currently blocked or allowed, with separate window, lock, queue, and profile/config indicators plus the guarded run command.
- Render a read-only Run History / Recovery panel from `QuantGod_ParamLabRunRecovery.json`, showing candidate red/yellow/green retry-budget risk, grouped failure reasons, runId, mode, terminal exit code, report missing/parsed/malformed counts, retry count, stop reason, recovery action, report path, and archived status path.
- Render a read-only ParamLab Report Watcher panel from `QuantGod_ParamLabReportWatcher.json`, showing discovered Strategy Tester reports, parser state, PF, win rate, net profit, drawdown, trade count, blocker state, and copyable report paths.
- Render a read-only AI/Governance Feedback panel from `QuantGod_GovernanceAdvisor.json`, showing each route's `why`, structured risk areas, next parameter tests, and the matching ParamLab candidate/task/report state with copyable tester-only commands and report paths. This is explanation and planning only; it does not promote routes, launch Strategy Tester, or write live configuration.

### Data Layer

Primary MT4 runtime files:

- `QuantGod_Dashboard.json`
- `QuantGod_TradeJournal.csv`
- `QuantGod_BalanceHistory.csv`
- `QuantGod_EquitySnapshots.csv`
- `QuantGod_SignalLog.csv`
- `QuantGod_SignalOpportunityQueue.csv`
- `QuantGod_OpportunityLabels.csv`
- `QuantGod_TradeEventLinks.csv`
- `QuantGod_TradeOutcomeLabels.csv`
- `QuantGod_AdaptiveStateHistory.csv`
- `QuantGod_StrategyEvaluationReport.csv`
- `QuantGod_RegimeEvaluationReport.csv`

MT5 phase 1 exports only:

- `QuantGod_Dashboard.json`
- `QuantGod_TradeJournal.csv`
- `QuantGod_CloseHistory.csv`
- `QuantGod_TradeOutcomeLabels.csv`
- `QuantGod_TradeEventLinks.csv`
- `QuantGod_StrategyEvaluationReport.csv`
- `QuantGod_RegimeEvaluationReport.csv`
- `QuantGod_OpportunityLabels.csv` (header placeholder)
- `QuantGod_ShadowSignalLedger.csv`
- `QuantGod_ShadowOutcomeLedger.csv`
- `QuantGod_ShadowCandidateLedger.csv`
- `QuantGod_ShadowCandidateOutcomeLedger.csv`
- `QuantGod_ManualAlphaLedger.csv`
- `QuantGod_GovernanceAdvisor.json` (derived by `tools/build_governance_advisor.py`, not exported by the EA)
- `QuantGod_StrategyVersionRegistry.json` (derived by `tools/build_strategy_version_registry.py`, not exported by the EA)
- `QuantGod_OptimizerV2Plan.json` (derived by `tools/build_optimizer_v2_plan.py`, not exported by the EA)
- `QuantGod_VersionPromotionGate.json` (derived by `tools/build_version_promotion_gate.py`, not exported by the EA)
- `QuantGod_ParamLabAutoScheduler.json` (derived by `tools/build_param_lab_auto_scheduler.py`, not exported by the EA)
- `QuantGod_AutoTesterWindow.json` (derived by `tools/run_param_lab_auto_tester_window.py`, not exported by the EA)
- `QuantGod_ParamLabRunRecovery.json` (derived by `tools/build_param_lab_run_recovery.py`, not exported by the EA)
- `QuantGod_ParamLabReportWatcher.json` (derived by `tools/watch_param_lab_reports.py`, not exported by the EA)

HFM Cent live runtime uses the same phase 1 export set, but writes it under:

- `C:\Program Files\HFM Metatrader 5\MQL5\Files\`

## Stable Design Facts

### Research Mode

- Research mode uses a virtual starting balance and risk model while executing real demo fills with a fixed micro lot.
- Demo account PnL is not the primary research metric.
- Research conclusions must follow the virtual-account pipeline, not raw broker profit alone.
- MT5 live pilot does not implement the old MT4 virtual research-account model; its dashboard export is broker-account runtime only.
- The HFM live pilot currently enables `MA_Cross` by default at `0.01` lot with `M15` trigger + `H1` trend filter + 5-bar fresh-crossover lookback plus a 24-bar pullback-continuation entry window, and it now also blocks new entries in `RANGE` / `RANGE_TIGHT`, enforces a same-symbol cooldown after a losing exit, converts consecutive-loss pauses into a `PilotConsecutiveLossPauseMinutes=180` timed cooldown before the next guarded probe, moves eligible profitable EA positions to breakeven plus trailing-stop profit protection, and applies a conservative safety/trailing guard to manual positions across all symbols without counting them in strategy/regime research reports or blocking same-symbol EA entries. Daily realized-loss and floating-loss kill switches remain hard pauses.
- The legacy MT4 routes are no longer pure dashboard placeholders on MT5. `USDJPY RSI_Reversal H1` is live-enabled in the HFM live preset; `BB_Triple`, `MACD_Divergence`, and `SR_Breakout` expose candidate/backtest runtime status until their iterated versions have enough evidence for live promotion. Every live route still must pass the shared `0.01`, single-position, spread/session/news/cooldown/portfolio/order-send, hard-SL, and kill-switch controls before sending an order. Demoted route leftovers are actively exited by `EnableDemotedPilotRouteExit`, with `DemotedPilotRouteProfitExitUSC=0.0` and `DemotedPilotRouteMaxLossUSC=0.50` in the HFM preset.
- The HFM live pilot now also exports a `news` state object and matching `news*` status lines so automation can react to USD event pre-blocks, post-release cooldowns, and short-lived directional bias windows.
- Backtest Lab V1 is a technical baseline, not permission to scale risk: future loosening should require both backtest support and live `0.01` forward evidence.
- Shadow Signal Ledger and Shadow Outcome Ledger are learning surfaces, not trading triggers: they can accelerate review of blocked/no-trade opportunities and their 15/30/60 minute post-outcomes, but cannot by themselves justify larger size, new symbols, new strategies, or relaxed guards.
- Manual Alpha Ledger is also a learning surface, not a trading trigger: manual XAUUSDc or other discretionary wins can seed route hypotheses, but cannot directly authorize EA expansion without shadow, backtest, and live-forward evidence.
- Route promotion and demotion are automation-governed: Codex may demote weak live routes back to simulation/backtest quickly, and may promote improved candidate routes only after old-history context, Backtest Lab, candidate/outcome ledgers, and fresh `0.01` forward-style evidence agree. These changes must keep the account, server, `0.01` lot, single-symbol cap, SL/TP, spread/session/news/cooldown/portfolio/order-send controls, and kill switches unchanged or stricter.
- The Governance Advisor is the durable local implementation of that lifecycle view. It can recommend `KEEP_LIVE`, `KEEP_LIVE_WATCH`, `DEMOTE_REVIEW`, `KEEP_SIM_COLLECT`, `KEEP_SIM_ITERATE`, `RETUNE_SIM`, or `PROMOTION_REVIEW`, but any live-switch change still must pass the normal verification, compile/test, commit, and push workflow.
- `tools/build_param_optimization_plan.py` is the durable local implementation of the offline parameter-candidate loop. It can rank tester-only parameter candidates and backtest tasks, but it does not launch MT5, does not write the live preset, and does not authorize live promotion by itself.
- `tools/run_param_lab.py` is the durable local implementation of the controlled ParamLab runner. It can create Strategy Tester candidate presets/configs and update `QuantGod_ParamLabStatus.json`; by default it picks a route-balanced set so RSI/BB/MACD/SR each get a top candidate before extra slots are filled by score. Launching MT5 requires `--run-terminal --authorized-strategy-tester`, a valid `QuantGod_AutoTesterWindow.lock.json`, the allowed tester window unless a locked override is present, and generated config/profile validation. Parsed ParamLab results remain advisory evidence and are not written into the live preset automatically.
- `tools/watch_param_lab_reports.py` is the durable local implementation of ParamLab report discovery and result回灌. It can parse tester reports and rank parameter versions by `resultScore`, but it never launches MT5 and never writes a live preset. Governance Advisor should use this layer to distinguish a pending candidate from a tested parameter version.
- `tools/build_strategy_version_registry.py` is the durable local implementation of strategy versioning. It snapshots route parameters into stable version IDs and candidate child lineage, but it never treats a version record as permission to trade.
- `tools/build_optimizer_v2_plan.py` is the durable local implementation of version-aware offline optimizer proposals. It can propose the next tester-only parameter generation for MA/RSI/BB/MACD/SR, but it does not launch MT5, does not write the live preset, and does not authorize promotion by itself.
- `tools/build_param_lab_auto_scheduler.py` is the durable local implementation of Gate-driven config-only scheduling. It can queue the next route-balanced tester-only batch from `WAIT_REPORT`, `RETUNE`, and `WAIT_FORWARD` evidence and expose a plan that `tools/run_param_lab.py --plan` can materialize, but it does not launch MT5, does not add `-RunTerminal`, and does not mutate live configuration.
- `tools/run_param_lab_auto_tester_window.py` is the durable local implementation of the guarded run-terminal window. It is evaluation-only by default, writes `QuantGod_AutoTesterWindow.json`, and only attempts Strategy Tester execution when explicitly called with `--run-terminal --authorized-strategy-tester` and all lock/window/profile/config guards pass.
- `tools/build_param_lab_run_recovery.py` is the durable local implementation of guarded-run recovery visibility. It reads ParamLab run archives, AUTO_TESTER_WINDOW status, and report watcher results, then writes run-level stop reasons, recovery actions, and candidate retry-budget drilldown without launching MT5 or mutating live configuration.
- `tools/build_version_promotion_gate.py` is the durable local implementation of dry-run version promotion/demotion review. It can label current versions and optimizer proposals as `PROMOTE_CANDIDATE`, `KEEP_SIM`, `RETUNE`, `DEMOTE_LIVE`, `WAIT_REPORT`, or `WAIT_FORWARD`, but it does not write the live preset, open live switches, launch MT5, or authorize promotion by itself.

### Adaptive Control

- Adaptive control is protective, not self-optimizing.
- It adjusts risk and activation state.
- It does not automatically mutate live strategy parameters. Parameter self-optimization is staged through `QuantGod_ParamOptimizationPlan.json`, `QuantGod_ParamLabReportWatcher.json`, `QuantGod_ParamLabRunRecovery.json`, `QuantGod_StrategyVersionRegistry.json`, `QuantGod_OptimizerV2Plan.json`, `QuantGod_VersionPromotionGate.json`, `QuantGod_ParamLabAutoScheduler.json`, `QuantGod_AutoTesterWindow.json`, and Governance Advisor review before any preset change is considered.
- The current implementation evaluates adaptive state independently for each `strategy x symbol` pair.
- `EURUSD / RSI_Reversal` also has an additional research-only execution guard: it requires an exact RSI threshold crossback, uses a tighter Bollinger touch, and skips new entries during `TREND_EXP*` regimes.
- `EURUSD / MACD_Divergence` now also has a research-only execution guard: it skips bullish divergence buys during `TREND_DOWN` and `TREND_EXP_DOWN`.
- `EURUSD / BB_Triple` now also has a research-only execution guard: it skips buy setups during `TREND_EXP_DOWN`.
- Dashboard root `strategies` is scoped to a representative in-scope symbol for route ports, so USDJPY-only RSI no longer appears disabled just because the dashboard focus symbol is EURUSD.
- Cross-symbol comparison should come from `QuantGod_StrategyEvaluationReport.csv` or `symbols[].strategies` in `QuantGod_Dashboard.json`.
- MT5 phase 1 still keeps some adaptive/research-stat objects lightweight, but the strategy objects now distinguish `MA_Cross` live execution from legacy-route candidate/backtest/live-gated status.
- In HFM live-pilot mode, `MA_Cross` and `USDJPY RSI_Reversal H1` are the real executable slices enabled by the shipped live preset. `BB_Triple H1`, `MACD_Divergence H1`, and `SR_Breakout M15` are candidate/backtest iteration routes and remain constrained away from live order sending until promotion criteria are met.

### Labeling and Attribution

- `SignalLog` captures signal-time features and context.
- `OpportunityLabels` measures delayed opportunity after a horizon.
- `TradeEventLinks` maps `EventId -> Ticket` for newer trades.
- `TradeOutcomeLabels` maps realized trade outcomes, with `UNLINKED` preserved for older trades.
- `RegimeEvaluationReport` groups closed research outcomes by `strategy x symbol x entry-time regime`.
- Dashboard heatmap further aggregates `RegimeEvaluationReport` into operator-facing `strategy x regime` slices, optionally filtered by symbol.
- Dashboard research suggestions consume the same regime report, but keep the finer `strategy x symbol x regime` slice when generating `KEEP / REDUCE / PAUSE` recommendations.
- Strategy evaluation rows consume the same recommendation layer, but match it to the current live `strategy x symbol x timeframe x regime` row and fall back to a 0-sample recommendation when that exact regime slice has not closed yet.
- Symbol overview strategy chips consume the same recommendation layer too, but summarize it at the live `strategy x symbol` monitoring surface so the operator can see the current action earlier in the workflow.
- The symbol overview chip detail panel exposes the recommendation provenance, including the exact live slice key and whether the displayed action was matched directly or produced by the fallback path.
- The jump links in that chip detail panel do not change trading behavior; they only sync dashboard filter/highlight state so the operator can inspect the aligned suggestion card or heatmap cell faster.
- Reverse jumps from the research section also do not change trading behavior; they only sync monitor-section highlight state so the operator can see which live symbol card and strategy chip correspond to the selected research slice.
- Monitor breadcrumbs are part of that non-trading UI state too; they exist only to explain the current highlight source and should be cleared when the user initiates a fresh jump into the research section.

## Working Rules

### When Investigating Statistics

- Verify how `researchLots` and `researchNet` are computed.
- Prefer ticket-linked metadata when it exists.
- Be suspicious of any metric that depends on parsing compressed `OrderComment` text.

### When Investigating Strategy Quality

- Check both:
  - the focus-symbol adaptive summary in dashboard root `strategies`
  - per-symbol slices in `QuantGod_StrategyEvaluationReport.csv`
- Use `QuantGod_RegimeEvaluationReport.csv` when the question is about which market regime a strategy is handling well or badly.
- Use `QuantGod_GovernanceAdvisor.json`, `QuantGod_ParamLabReportWatcher.json`, `QuantGod_ParamLabRunRecovery.json`, `QuantGod_StrategyVersionRegistry.json`, `QuantGod_OptimizerV2Plan.json`, `QuantGod_VersionPromotionGate.json`, `QuantGod_ParamLabAutoScheduler.json`, and `QuantGod_AutoTesterWindow.json` when the question is about promotion, demotion, strategy version lineage, tester execution readiness, recovery status, or which route should stay live versus simulation; regenerate them first if the runtime evidence has changed.
- If dashboard heatmap and raw CSV disagree, treat the CSV as the source of truth first and debug the frontend aggregation/filtering path.
- If research suggestions and heatmap disagree, debug the recommendation-threshold layer separately from the raw regime aggregation layer.
- Do not mix one symbol's adaptive state into another symbol's evaluation.

### When Updating Documentation

- Keep reusable operator guidance here in the skill.
- Keep lightweight human-facing notes in `README.md` when needed.
- Put volatile numbers in runtime exports, not canonical docs.
- Keep MT5 migration notes explicit about phase boundaries so the skeleton is not mistaken for a fully ported execution engine.
