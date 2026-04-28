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

Current live-trading boundary:

- Live `0.01` routes remain limited to `MA_Cross` and `USDJPY RSI_Reversal H1`.
- `BB_Triple`, `MACD_Divergence`, and `SR_Breakout` remain candidate/backtest/simulation routes.
- Research tools do not mutate `QuantGod_MT5_HFM_LivePilot.set`.
- Research tools do not connect to HFM, store credentials, bypass EA `OrderSend`, or change lot size, account, server, SL/TP, position caps, kill switches, spread/session/news/cooldown/portfolio/order-send controls.

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
- Live preset is not copied over, mutated, or used as the output target.
- Report output path is unique per candidate/version.

Remaining runner work:

- Add no-open-position / isolated-terminal policy before unattended weekday or live-session tester automation.
- Add retry/budget controls and continuous polling.
- Add stronger terminal timeout vs tester-failure classification.

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

- Poll continuously during authorized tester windows instead of running as a one-shot builder.
- Detect terminal timeout separately from tester failure.
- Requeue retryable failures with a cap.

### 3. Backtest Budget and Experiment Control

Purpose:

- Avoid wasting tester time or overfitting.

Needed behavior:

- Per route run budget.
- Per parameter family run budget.
- Minimum trade count threshold.
- Maximum drawdown threshold.
- Sample-size penalty.
- Cooldown for repeatedly failing parameter families.
- Keep control-arm versions in the queue so Optimizer V2 does not chase noise.

### 4. Dashboard Run History / Audit Trail

Purpose:

- Make the automatic backtest loop transparent.

Needed dashboard surface:

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

1. Add Dashboard run-history panel with run ID, child process exit code, terminal/report state, and guard blockers.
2. Add retry/budget controls.
3. Re-evaluate whether isolated tester terminal support is needed before allowing unattended tester runs while live pilot is open.
4. Add explicit no-open-position / live-session compatibility policy before unattended execution.

## Immediate Next Step

Build the run-history / recovery layer next. Auto Scheduler chooses the next tester-only batch, AUTO_TESTER_WINDOW now gates whether it may run, and Report Watcher discovers/report-scores landed tester reports. The remaining gap for comfortable full automation is transparent run history plus retry/budget controls, not live-risk expansion.
