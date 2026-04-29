# QuantGod Backtest Autonomy Plan

This plan tracks the remaining QuantDinger-inspired pieces that have not been fully migrated into QuantGod, and defines how to make the backtest loop increasingly automatic without weakening HFM live-pilot guardrails.

## Current State

Implemented:

- Param Optimization Plan: proposes tester-only parameter candidates and task metadata.
- ParamLab Runner: materializes tester-only `.set` and `.ini` files; direct Strategy Tester launch now also requires AUTO_TESTER_WINDOW lock/window/profile/config validation.
- ParamLab Report Watcher: discovers completed tester reports, scores PF, win rate, net profit, trade count, and drawdown, writes `QuantGod_ParamLabReportWatcher.json`, and updates the unified results ledger.
- ParamLab batch dashboard: shows runnable, waiting-report, scored, and route-filtered task state.
- Strategy Workspace: gives MA/RSI/BB/MACD/SR independent route cards.
- AI/Governance Feedback: explains why a route should keep live, stay simulation, retune, demote, or enter promotion review.
- Feedback to ParamLab task links: connects next-parameter advice to candidate/task/report state and tester-only commands.
- Strategy Version Registry: records current route versions, parameter hashes, live/candidate status, evidence, and tester-only child lineage.
- Optimizer V2: proposes next-generation tester-only parameters linked to parent strategy versions.
- Version Promotion Gate dry-run: writes `QuantGod_VersionPromotionGate.json` and `QuantGod_VersionPromotionGateLedger.csv`, judging each current route version and optimizer proposal by `versionId` without changing live switches.
- ParamLab Auto Scheduler config-only: writes `QuantGod_ParamLabAutoScheduler.json` and `QuantGod_ParamLabAutoSchedulerLedger.csv`, translating Gate `WAIT_REPORT`, `RETUNE`, and `WAIT_FORWARD` evidence into the next route-balanced tester-only queue without adding `-RunTerminal`.
- AUTO_TESTER_WINDOW guarded execution layer: writes `QuantGod_AutoTesterWindow.json` and `QuantGod_AutoTesterWindowLedger.csv`; default mode is evaluation-only, and run-terminal execution is blocked unless the Strategy Tester window, authorization lock, tester-only queue, HFM terminal/profile target, ParamLab config, report path, lot size, and position caps all pass.
- ParamLab Run History / Recovery: writes `QuantGod_ParamLabRunRecovery.json`, `QuantGod_ParamLabRunRecoveryLedger.csv`, and `QuantGod_ParamLabRunRecoveryDrilldown.csv`, summarizing each guarded/config run by runId, terminal exit code, report missing/parsed/malformed state, retry count, stop reason, and next recovery action, then aggregating each candidate into a red/yellow/green retry-budget and failure-reason drilldown.
- Executor-level retry enforcement: AUTO_TESTER_WINDOW now reads Run Recovery drilldown before launching the runner, writes a filtered `QuantGod_AutoTesterWindowExecutorPlan.json`, and excludes red candidates so they do not consume automatic tester retries.
- Backtest budget / experiment control: AUTO_TESTER_WINDOW enforces per-route, per-parameter-family, and per-failure-family budgets before the runner sees the queue. Optional overrides can be supplied with `QuantGod_ParamLabBacktestBudget.json`; defaults stay conservative.
- Continuous watcher bridge: AUTO_TESTER_WINDOW can run Report Watcher in a bounded polling loop after a guarded Strategy Tester run, so reports can be parsed during the same authorized tester window.
- MT5 Backend Backtest Loop: `tools/run_mt5_backend_backtest_loop.py` gives QuantGod a QuantDinger-style Python backend pre-screen that reads tester-only Scheduler/Optimizer tasks, loads MT5 rates read-only or offline bars fixtures, simulates MA/RSI/BB/MACD/SR routes, and writes `QuantGod_MT5BackendBacktest.json`, ledger CSV, and trade ledger CSV for Dashboard and Governance Advisor. It is Python-backtest-only and cannot place, close, cancel, select symbols, launch Strategy Tester, or mutate live presets.
- Isolated tester terminal/profile support: AUTO_TESTER_WINDOW now defaults to `runtime/HFM_MT5_Tester_Isolated`, requires an isolated root unless `--allow-shared-tester` is explicit, and can be prepared by `tools/prepare_isolated_mt5_tester.py`; this lets future tester execution target an isolated terminal/profile instead of the live HFM installation.
- No-open-position / live-session compatibility gate: AUTO_TESTER_WINDOW and the underlying ParamLab runner read the live `QuantGod_Dashboard.json` snapshot before any unattended `--run-terminal`; tester execution stays blocked while live open positions, margin usage, stale dashboard state, account/server mismatch, disconnected terminal state, or kill-switch state are detected.
- Polymarket research bridge: `tools/build_polymarket_research_bridge.py` reads `D:\polymarket\copybot.db` in SQLite read-only/query-only mode, optionally reads redacted `.env` values only to fetch a read-only CLOB account-cash snapshot, writes `QuantGod_PolymarketResearch.json`, and keeps a separate dashboard workspace. It does not import Polymarket executors, place orders, or mutate MT5.
- Polymarket Opportunity Radar V1: `tools/build_polymarket_market_radar.py` calls only the public Gamma API and writes `QuantGod_PolymarketMarketRadar.json` / CSV with market probability, volume, liquidity, divergence, AI/rule proxy score, risk flags, and suggested shadow track. It is discovery-only and does not use wallet/order APIs.
- Polymarket Single Market AI Analysis V1: `tools/analyze_polymarket_single_market.py` accepts a URL/title/marketId request or falls back to the top radar candidate, writes `QuantGod_PolymarketSingleMarketAnalysis.json` plus an analysis ledger, and explains market probability, AI/rule proxy probability, divergence, confidence, risk factors, and suggested shadow track while keeping wallet/order/MT5 writes disabled.
- Polymarket Retune Planner: `tools/build_polymarket_retune_planner.py` consumes `QuantGod_PolymarketResearch.json` and writes `QuantGod_PolymarketRetunePlanner.json` / CSV with shadow-only filter and parameter-retune suggestions. Every recommendation explicitly keeps `liveExecutionAllowed=false`.
- Polymarket Execution Gate V1: `tools/build_polymarket_execution_gate.py` consumes Research/Radar/Retune outputs and writes `QuantGod_PolymarketExecutionGate.json` plus ledger CSV. It defines allowed-bet conditions, reference stake, TP/SL, max daily loss, market blocklist, cancel/exit rules, and future audit ledgers, but keeps `walletWriteAllowed=false` and `canBet=false`.
- Polymarket Dry-Run Order Simulator + Execution Ledger schema: `tools/build_polymarket_dry_run_orders.py` consumes the Execution Gate and Radar outputs, writes `QuantGod_PolymarketDryRunOrders.json` and `QuantGod_PolymarketExecutionLedger.csv`, and records hypothetical stake, entry price, TP/SL price, cancel timing, max-hold exit, exit-before-resolution timing, blockers, and audit fields while keeping `walletWrite=false` and `orderSend=false`.
- Polymarket Dry-Run Outcome Watcher: `tools/watch_polymarket_dry_run_outcomes.py` consumes dry-run orders and the latest Radar prices, writes `QuantGod_PolymarketDryRunOutcomeWatcher.json` and `QuantGod_PolymarketDryRunOutcomeLedger.csv`, carries forward observed high/low prices by stable tracking key, and reports whether TP, SL, trailing exit, max-hold, or pre-resolution exits would have fired without placing or closing orders.
- Polymarket Cross-Market Linkage V1: `tools/build_polymarket_cross_market_linkage.py` maps radar/worker/analysis/AI-score market text into USD, JPY, XAU, rates, war/geopolitical, and macro risk awareness tags, writes `QuantGod_PolymarketCrossMarketLinkage.json/csv`, and keeps `walletWriteAllowed=false`, `orderSendAllowed=false`, and `mt5ExecutionAllowed=false`.
- Polymarket Canary / Wallet Executor Contract V1: `tools/build_polymarket_canary_executor_contract.py` defines an isolated canary root/profile, future env switch names, canary stake caps, daily loss, TP/SL, trailing, cancel, max-hold, exit-before-resolution, kill switch, and audit ledger requirements, writes `QuantGod_PolymarketCanaryExecutorContract.json` plus CSV, persists rows to `qd_polymarket_canary_contracts`, and keeps `readsPrivateKey=false`, `walletWriteAllowed=false`, `orderSendAllowed=false`, `callsClobApi=false`, and `startsExecutor=false`.
- Polymarket Auto Promotion / Demotion Governance V1: `tools/build_polymarket_auto_governance.py` consumes research, radar, Worker V2, retune, AI score, dry-run outcome, cross-linkage, and canary contract evidence, writes `QuantGod_PolymarketAutoGovernance.json/csv`, persists rows to `qd_polymarket_auto_governance`, folds governance into `/api/polymarket/search`, and keeps `walletWriteAllowed=false`, `orderSendAllowed=false`, `startsExecutor=false`, `mutatesMt5=false`, and `canPromoteToLiveExecution=false`.

Current live-trading boundary:

- Live `0.01` routes remain limited to `MA_Cross` and `USDJPY RSI_Reversal H1`.
- `BB_Triple`, `MACD_Divergence`, and `SR_Breakout` remain candidate/backtest/simulation routes.
- Research tools do not mutate `QuantGod_MT5_HFM_LivePilot.set`.
- Research tools do not connect to HFM, store credentials, bypass EA `OrderSend`, or change lot size, account, server, SL/TP, position caps, kill switches, spread/session/news/cooldown/portfolio/order-send controls.
- The Polymarket bridge/radar/single-market analyzer/planner/execution-gate/dry-run simulator/outcome watcher/cross-market linkage/canary contract/auto-governance layer are external evidence, contract, and recommendation layers only. Future Polymarket execution is allowed only as a separate promoted module with wallet isolation, TP/SL, max-loss, order-send audit, and kill-switch checks; it must not share loops, wallets, canary switches, or order paths with MT5/HFM.

## Remaining Migration Work

### 1. Fully Automatic Tester Runner

Purpose:

- Make the backtest execution loop automatic after candidates exist.
- Reduce manual weekend work from "find task, run tester, find report" to "approve/allow scheduler, inspect results."

Feasibility:

- Full-auto Strategy Tester execution is technically possible.
- It should be implemented as tester-only automation, not live-trading automation.
- The safe version should run only in an authorized tester window or explicit user-authorized session.

Implemented safety gates before `-RunTerminal`:

- HFM terminal path verified.
- Tester profile root verified: `C:\Program Files\HFM Metatrader 5\MQL5\Profiles\Tester`.
- Authorization lock file required: `QuantGod_AutoTesterWindow.lock.json`.
- Lock must be for `PARAM_LAB_STRATEGY_TESTER_ONLY`, authorized, tester-only, run-terminal allowed, not expired, and pinned to the expected HFM/runtime paths when those fields are present.
- Regular Strategy Tester window required by default; outside-window override requires both the CLI flag and a lock that explicitly allows it.
- Auto Scheduler queue must be tester-only, must not include `-RunTerminal` by default, and must not declare live-preset mutation.
- ParamLab config must set `AllowLiveTrading=0`, `AllowDllImport=0`, `Optimization=0`, `ShutdownTerminal=1`, and a report path under `archive/param-lab/runs/`.
- Candidate presets must keep `PilotLotSize<=0.01`, `PilotMaxTotalPositions<=1`, and `PilotMaxPositionsPerSymbol<=1`.
- Tester profile is validated against the generated ParamLab preset immediately before terminal launch.
- Live dashboard snapshot must be fresh and compatible: zero `openTrades`, zero symbol/strategy positions, no margin in use, expected account/server, connected terminal/account, and no pilot kill switch.
- Live preset is not copied over, mutated, or used as the output target.
- Report output path is unique per candidate/version.

Remaining runner work:

- Add stronger terminal timeout vs tester-failure classification after real guarded runs exist.
- Keep the physical isolated tester directory refreshed with `tools/prepare_isolated_mt5_tester.py` after EA/source/preset updates.

Proposed mode names:

- `AUTOPLAN_ONLY`: current default; generates candidates, scheduler queue, and configs, no tester launch.
- `AUTO_TESTER_WINDOW`: implemented as a guarded Strategy Tester bridge; default is evaluation-only, and `--run-terminal` requires lock/window/profile/config validation.
- `AUTO_TESTER_ISOLATED`: future stronger mode that runs against an isolated tester terminal/profile so live pilot remains untouched.
- `AUTO_PROMOTION_DRY_RUN`: creates version promotion recommendations only.
- `AUTO_LIVE_SWITCH`: not recommended now; would require a separate explicit rule change and stronger evidence gates.

### 2. Report Watcher and Recovery

Purpose:

- After a tester run starts, automatically detect whether the report was produced, parsed, missing, stale, or malformed.

Implemented behavior:

- Scans ParamLab run archives, current `QuantGod_ParamLabStatus.json`, Auto Scheduler queue records, and known report paths.
- Matches landed reports by candidate ID and expected report path.
- Parses partial reports when possible.
- Writes `QuantGod_ParamLabReportWatcher.json`, `QuantGod_ParamLabReportWatcherLedger.csv`, `QuantGod_ParamLabResults.json`, and `QuantGod_ParamLabResultsLedger.csv`.
- Marks pending reports as non-promotion evidence and malformed reports as blocked evidence.
- Never reuse stale reports from a previous candidate.

Remaining recovery work:

- Detect terminal timeout separately from tester failure.
- Requeue retryable failures from watcher output only when executor retry and budget controls still allow the candidate.
- Run history, dashboard recovery visibility, candidate drilldown, and executor-level red-skip enforcement are now implemented.

### 3. Backtest Budget and Experiment Control

Purpose:

- Avoid wasting tester time or overfitting.

Implemented behavior:

- Per route run budget.
- Per parameter family run budget.
- Per failure family run budget, based on Run Recovery risk reasons.
- Red drilldown candidates are skipped before budget accounting, preserving retries.
- Control-arm versions can remain queued as long as they pass retry and budget gates.

Remaining budget work:

- Add min-trade, maximum-drawdown, and sample-size penalty controls after more parsed reports exist.
- Add cooldown windows for repeatedly failing parameter families once terminal/report failure history is large enough.

### 4. Dashboard Run History / Audit Trail

Purpose:

- Make the automatic backtest loop transparent.

Implemented dashboard surface:

- Current run ID.
- Queue length.
- Active candidate/version.
- Last tester launch time.
- Terminal exit code.
- Report status.
- Parse status.
- Score and grade.
- Next automatic action.
- Why the scheduler stopped.

Remaining dashboard work:

- Add optional run-detail drilldown after real Strategy Tester runs exist.
- The AUTO_TESTER_WINDOW panel now shows executor filtering, red-skip count, budget decisions, isolation status, and continuous watcher status.

### 5. QuantDinger Pieces Not Worth Porting Now

Defer:

- Database-backed strategy CRUD.
- User/account/auth/product modules.
- Exchange/live connector modules.
- Websocket/SSE progress service.
- LLM-generated parameter spaces.
- Full backend task-service architecture.

Reason:

- QuantGod is currently a local MT5/HFM file-based system.
- Live execution must stay inside the EA.
- The useful QuantDinger concepts have already been migrated as file-based components: lifecycle view, strategy snapshots, version lineage, optimizer proposals, result scoring, and queue/status surfaces.
- The backend task-service idea is now represented by the local JSON/CSV `MT5 Backend Backtest Loop`, without importing QuantDinger's trading adapter or database requirement.

## Can The Backtest Loop Be Fully Automatic?

Yes, the backtest loop can be fully automatic if "fully automatic" means:

1. Optimizer V2 proposes candidate parameters.
2. ParamLab Scheduler selects a route-balanced run batch.
3. The runner generates tester-only configs and presets.
4. During an allowed window or explicit authorization, the runner launches MT5 Strategy Tester.
5. A report watcher discovers output.
6. Report Watcher scores reports into the unified results ledger.
7. Strategy Version Registry updates parent/child version state.
8. Optimizer V2 creates the next generation.
9. Governance Advisor and Version Promotion Gate produce dry-run recommendations.

No, it should not be fully automatic if "fully automatic" means:

- automatically writing winning parameters into the HFM live preset;
- automatically enabling a candidate route's live switch;
- automatically increasing lots or position caps;
- automatically bypassing the weekend/authorization boundary for Strategy Tester;
- automatically trading from a non-EA path.

The recommended target is:

- Fully automatic tester-only backtest execution during an approved safe window.
- Fully automatic parsing, scoring, versioning, and next-generation proposal.
- Dry-run promotion/demotion recommendations by `versionId`.
- Manual or separately authorized live-switch application after evidence review.

## Suggested Implementation Order

1. Prepare an isolated tester terminal/profile directory if fully unattended tester runs should happen while the live pilot is also open.
2. After the next authorized tester window produces reports, add timeout-vs-tester-failure classification and min-trade/drawdown budget rules.

## Immediate Next Step

Use the isolated tester root in `runtime/HFM_MT5_Tester_Isolated` as the guarded runner target. Auto Scheduler chooses the next tester-only batch, Run Recovery marks red/yellow/green risk, AUTO_TESTER_WINDOW removes red and over-budget candidates before runner launch, verifies the live session has no open positions or margin usage, and Report Watcher can poll continuously during an authorized tester window. The next safety step after real guarded runs exist is terminal-timeout vs tester-failure classification.
