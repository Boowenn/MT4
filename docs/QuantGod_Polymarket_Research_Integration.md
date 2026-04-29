# QuantGod Polymarket Research Integration

This document records how the local `D:\polymarket` project is integrated into QuantGod without conflicting with MT5/HFM execution.

## Boundary

The integration is research-only by default. A guarded Polymarket canary executor exists, but it stays plan-only/audit-only unless strict evidence thresholds, isolated runtime switches, a lock file, and kill-switch checks all pass.

- Reads `D:\polymarket\copybot.db` through SQLite `mode=ro` and `PRAGMA query_only=ON`.
- Does not import Polymarket application modules.
- Reads `D:\polymarket\.env` only for the optional account-cash snapshot, redacts secret values, and never writes them to dashboard output.
- Does not start Polymarket `main.py`, `web.py`, legacy executor loops, legacy canary loops, or MT5 order-send code.
- Does not mutate MT5 EA source, live presets, account/server settings, lot size, SL/TP, kill switches, or order paths.

The generated file is only a dashboard evidence supplement:

- `QuantGod_PolymarketResearch.json`
- `QuantGod_PolymarketResearchLedger.csv`
- `QuantGod_PolymarketMarketRadar.json`
- `QuantGod_PolymarketMarketRadar.csv`
- `QuantGod_PolymarketMarketCatalog.json`
- `QuantGod_PolymarketMarketCatalog.csv`
- `QuantGod_PolymarketAssetOpportunities.json`
- `QuantGod_PolymarketAssetOpportunities.csv`
- `QuantGod_PolymarketRadarWorkerV2.json`
- `QuantGod_PolymarketRadarWorkerV2.csv`
- `QuantGod_PolymarketRadarTrendCache.json`
- `QuantGod_PolymarketRadarCandidateQueue.json`
- `QuantGod_PolymarketRadarCandidateQueue.csv`
- `QuantGod_PolymarketSingleMarketAnalysis.json`
- `QuantGod_PolymarketSingleMarketAnalysisLedger.csv`
- `QuantGod_PolymarketRetunePlanner.json`
- `QuantGod_PolymarketRetunePlanner.csv`
- `QuantGod_PolymarketExecutionGate.json`
- `QuantGod_PolymarketExecutionGateLedger.csv`
- `QuantGod_PolymarketDryRunOrders.json`
- `QuantGod_PolymarketExecutionLedger.csv`
- `QuantGod_PolymarketDryRunOutcomeWatcher.json`
- `QuantGod_PolymarketDryRunOutcomeLedger.csv`
- `QuantGod_PolymarketHistoryDb.json`
- `QuantGod_PolymarketHistoryDb.csv`
- `QuantGod_PolymarketAiScoreV1.json`
- `QuantGod_PolymarketAiScoreV1.csv`
- `QuantGod_PolymarketAiSemanticReview.json`
- `QuantGod_PolymarketCrossMarketLinkage.json`
- `QuantGod_PolymarketCrossMarketLinkage.csv`
- `QuantGod_PolymarketCanaryExecutorContract.json`
- `QuantGod_PolymarketCanaryExecutorLedger.csv`
- `QuantGod_PolymarketCanaryExecutorRun.json`
- `QuantGod_PolymarketCanaryOrderAuditLedger.csv`
- `QuantGod_PolymarketCanaryPositionLedger.csv`
- `QuantGod_PolymarketCanaryExitLedger.csv`
- `QuantGod_PolymarketAutoGovernance.json`
- `QuantGod_PolymarketAutoGovernanceLedger.csv`

## Bridge

Run:

```bat
tools\build_polymarket_research_bridge.bat
```

Optional form:

```bat
tools\build_polymarket_research_bridge.bat "C:\Program Files\HFM Metatrader 5\MQL5\Files" "D:\polymarket"
```

The bridge writes the snapshot to both:

- HFM runtime files directory, for the MT5-local dashboard data layer.
- `Dashboard\`, for the local `http://localhost:8080/vue/` static Vue dashboard server.

## Opportunity Radar V1

Run:

```bat
tools\build_polymarket_market_radar.bat
```

The radar uses only the public Gamma API active-market endpoint. It writes `QuantGod_PolymarketMarketRadar.json` and CSV with market, probability, volume, liquidity, divergence, rule-proxy score, risk flags, and the suggested shadow track.

Current radar behavior is deliberately `SHADOW_ONLY_MARKET_RADAR_NO_BETTING`:

- no `.env` load;
- no wallet read/write;
- no CLOB order calls;
- no Polymarket executor or canary loop;
- no MT5 mutation.

If Polymarket execution is added later, it should be a separate promoted module gated by Strategy Version Registry, Governance Advisor, bankroll isolation, position sizing, per-market max loss, take-profit/stop-loss exit rules, order-send audit, and a kill switch. The radar is the discovery layer, not the execution layer.

## QuantDinger-Style Market Catalog / Related Assets

Run:

```bat
tools\build_polymarket_quantdinger_parity.bat
```

The parity builder uses only public Gamma API data. It writes a market catalog plus related-asset opportunity rows:

- `QuantGod_PolymarketMarketCatalog.json`
- `QuantGod_PolymarketMarketCatalog.csv`
- `QuantGod_PolymarketAssetOpportunities.json`
- `QuantGod_PolymarketAssetOpportunities.csv`

The market catalog carries event/market id, question, URL, category, probability, volume, liquidity, spread, divergence, rule score, risk, suggested shadow track, and related-asset tags. The related-asset output maps market wording to research-only symbols such as `XAUUSD`, `USDJPY`, BTC/ETH/SOL, rates, and selected equities when event keywords justify the link.

These links are risk context only:

- no `.env` secret read;
- no wallet write;
- no CLOB order calls;
- no executor/canary start;
- no MT5 mutation;
- no MT5 trade permission change.

The dashboard server exposes:

```text
GET /api/polymarket/markets
GET /api/polymarket/market?id=...
GET /api/polymarket/asset-opportunities
```

The Dashboard Polymarket workspace now includes a market browser with search, category/risk/sort filters, selected-market detail cards, and related-asset opportunity cards. These rows also persist into the history DB and the unified search facade so the catalog is auditable instead of being a transient latest JSON snapshot.

## Batch Opportunity Radar V2 / Worker

Run:

```bat
tools\run_polymarket_radar_worker_v2.bat
```

Optional bounded worker form:

```bat
set QG_POLYMARKET_RADAR_WORKER_CYCLES=4
set QG_POLYMARKET_RADAR_WORKER_INTERVAL_SECONDS=900
tools\run_polymarket_radar_worker_v2.bat
```

Worker V2 wraps Gamma Radar V1 with a controlled cadence, trend cache, market deduplication, and a shadow-only candidate queue. The default is one cycle, so normal manual use refreshes evidence once and exits. Longer runs are bounded by `--max-cycles`; there is no unbounded daemon by default.

It writes:

- `QuantGod_PolymarketRadarWorkerV2.json`
- `QuantGod_PolymarketRadarWorkerV2.csv`
- `QuantGod_PolymarketRadarTrendCache.json`
- `QuantGod_PolymarketRadarCandidateQueue.json`
- `QuantGod_PolymarketRadarCandidateQueue.csv`

It also refreshes the V1 `QuantGod_PolymarketMarketRadar.json/csv` outputs with Worker trend annotations, so the existing dashboard radar remains compatible.

The queue state is `SHADOW_ANALYSIS_READY` only. It is for single-market analysis or AI score review, not execution:

- no `.env` load;
- no private key reads;
- no wallet writes;
- no CLOB order calls;
- no executor/canary start;
- no MT5 mutation.

This closes the QuantDinger-style batch-radar gap without restoring Polymarket betting. Any future real order executor must still pass the separate Execution Gate, dry-run outcome evidence, bankroll budget, TP/SL rules, and explicit canary controls.

## Single Market AI Analysis V1

Run:

```bat
tools\analyze_polymarket_single_market.bat
```

Optional with a specific market URL/title/market id:

```bat
tools\analyze_polymarket_single_market.bat "C:\Program Files\HFM Metatrader 5\MQL5\Files" "https://polymarket.com/event/example-market"
```

If no CLI query is supplied, the analyzer first looks for `QuantGod_PolymarketSingleMarketRequest.json` in `Dashboard\` or the HFM runtime files directory. The request can contain `query`, `url`, `marketUrl`, `polymarketUrl`, `marketId`, `slug`, `title`, or `question`. If no request exists, it falls back to the top `QuantGod_PolymarketMarketRadar.json` candidate.

The Dashboard Polymarket workspace also has a local input control. When the dashboard is served through `Dashboard\start_dashboard.bat`, the button posts to:

```text
POST /api/polymarket/single-market-request
```

That endpoint writes `QuantGod_PolymarketSingleMarketRequest.json` into `Dashboard\` and the HFM runtime files directory, then runs the same read-only analyzer. If the page is opened through `file://` or another static server without the endpoint, the button falls back to downloading the request JSON so it can still be generated without hand-writing it.

The analyzer writes:

- `QuantGod_PolymarketSingleMarketAnalysis.json`
- `QuantGod_PolymarketSingleMarketAnalysisLedger.csv`

It is still research-only:

- uses public Gamma active-market data;
- uses a deterministic `RULE_PROXY_NO_LLM` AI/rule probability proxy until an explicit AI service is added;
- outputs market probability, AI/rule probability, divergence, recommendation, confidence, risk factors, and suggested shadow track;
- keeps `walletWriteAllowed=false`, `orderSendAllowed=false`, `startsExecutor=false`, and `mutatesMt5=false`.

This layer is useful for inspecting a single market before it is allowed into dry-run or execution-gate review. It must not directly restore betting.

## Execution Gate V1

Run:

```bat
tools\build_polymarket_execution_gate.bat
```

The gate consumes the research bridge, Gamma radar, and retune planner outputs. V1 is intentionally a contract shell:

- defines when betting could be allowed;
- defines reference single-bet size, max single-market exposure, max daily loss, max open positions;
- defines TP/SL, trailing-profit, max-hold, cancel-unfilled, and exit-before-resolution rules;
- defines blocklisted market risk flags and route conditions;
- defines required future order, position, and exit ledgers;
- writes per-market `canBet=false` decisions and blockers.

It still does not load private keys, write wallets, call CLOB order APIs, start an executor, or mutate MT5. The current decision remains `BLOCKED_CONTRACT_ONLY_NO_WALLET_WRITE` until a separate execution module is explicitly promoted and wired through this gate.

## Dry-Run Order Simulator and Execution Ledger

Run:

```bat
tools\build_polymarket_dry_run_orders.bat
```

The simulator consumes `QuantGod_PolymarketExecutionGate.json` and `QuantGod_PolymarketMarketRadar.json`, then writes:

- `QuantGod_PolymarketDryRunOrders.json`
- `QuantGod_PolymarketExecutionLedger.csv`

This layer answers "if a market eventually passed the gate, what would the order and exit plan look like?" without touching money:

- calculates the reference stake and the actual dry-run stake;
- records entry/limit price from market probability;
- calculates TP price, SL price, trailing trigger, cancel-unfilled time, max-hold exit, and exit-before-resolution time;
- writes the reusable execution-ledger schema that a future real executor would have to fill;
- keeps `walletWrite=false`, `orderSend=false`, `startsExecutor=false`, and `mutatesMt5=false`.

Blocked gate candidates still get a hypothetical plan, but `simulatedStakeUSDC=0` and `decision=DRY_RUN_BLOCKED_BY_GATE`. This prevents an eventual executor from appearing before the audit schema and exit rules are visible.

## Dry-Run Outcome Watcher

Run:

```bat
tools\watch_polymarket_dry_run_outcomes.bat
```

The watcher consumes `QuantGod_PolymarketDryRunOrders.json` and the latest `QuantGod_PolymarketMarketRadar.json`, then writes:

- `QuantGod_PolymarketDryRunOutcomeWatcher.json`
- `QuantGod_PolymarketDryRunOutcomeLedger.csv`

It keeps a stable tracking key per `market + track + side` and carries forward observed high/low prices from the previous watcher output. This lets the system validate whether the dry-run exit rules would have worked:

- current price and unrealized percentage;
- MFE/MAE since first observation;
- whether TP, SL, trailing exit, max-hold exit, or pre-resolution exit would have fired;
- ambiguous TP/SL triggers when sparse polling cannot prove which happened first;
- persistent `walletWrite=false`, `orderSend=false`, `startsExecutor=false`, and `mutatesMt5=false`.

This is still an observation layer. It does not place, cancel, or close any order.

## Historical Analysis DB V1

Run:

```bat
tools\build_polymarket_history_db.bat
```

The history builder consumes the already-generated Polymarket research files and stores them in a local SQLite database under:

```text
archive\polymarket\history\QuantGod_PolymarketHistory.sqlite
```

It writes dashboard/runtime summaries:

- `QuantGod_PolymarketHistoryDb.json`
- `QuantGod_PolymarketHistoryDb.csv`

The V7 tables are:

- `qd_polymarket_runs`
- `qd_polymarket_asset_opportunities`
- `qd_polymarket_market_analysis`
- `qd_polymarket_execution_simulations`
- `qd_polymarket_research_snapshots`
- `qd_polymarket_radar_worker_runs`
- `qd_polymarket_radar_trends`
- `qd_polymarket_radar_queue`
- `qd_polymarket_cross_market_linkage`
- `qd_polymarket_canary_contracts`
- `qd_polymarket_canary_executor_runs`
- `qd_polymarket_canary_order_audit`
- `qd_polymarket_auto_governance`
- `qd_polymarket_markets`
- `qd_polymarket_related_asset_opportunities`

This closes the first persistence gap from the QuantDinger-style workflow: opportunity radar rows, market catalog rows, related-asset opportunity rows, Worker V2 batch runs, trend-cache rows, shadow queue rows, cross-market linkage rows, canary contract rows, canary executor run/audit rows, auto-governance rows, single-market analysis rows, dry-run/outcome rows, and high-level research snapshots are no longer only latest JSON/CSV snapshots. They can be searched, counted, reviewed later, and used as the stable input for future AI scoring and governance.

Safety boundary remains unchanged: the history builder does not read private keys, does not write wallets, does not call CLOB order APIs, does not start executors, and does not mutate MT5. It is a local research memory, not an execution trigger.

## Search / History API V1

The local dashboard server now exposes the history DB through a read-only API:

```text
GET /api/polymarket/history?table=all&q=keyword&limit=50
```

Supported `table` values:

- `all`
- `opportunities`
- `analyses`
- `simulations`
- `runs`
- `snapshots`
- `worker-runs`
- `worker-trends`
- `worker-queue`
- `cross-linkage`
- `canary-contracts`
- `canary-executor-runs`
- `canary-order-audit`
- `auto-governance`
- `markets`
- `related-assets`

Implementation files:

- `Dashboard\dashboard_server.js`
- `tools\query_polymarket_history_api.py`

The server spawns the Python helper instead of adding a native Node sqlite dependency. The helper opens `archive\polymarket\history\QuantGod_PolymarketHistory.sqlite` with SQLite `mode=ro` and `PRAGMA query_only=ON`, returns JSON, and never writes to the database.

Dashboard behavior is now API-first:

- `Historical Analysis DB` calls `/api/polymarket/history` for row counts, recent rows, and keyword search.
- The panel has a local search control for history type and query text.
- If the local API is unavailable, the dashboard falls back to `QuantGod_PolymarketHistoryDb.json`.

The endpoint is still research-only: no private-key read, no wallet write, no CLOB order call, no executor start, and no MT5 mutation.

## Unified Read-Only Service API V1

The dashboard server also exposes the active Polymarket research artifacts through one read-only service layer:

```text
GET /api/polymarket/radar
GET /api/polymarket/markets
GET /api/polymarket/market?id=...
GET /api/polymarket/asset-opportunities
GET /api/polymarket/cross-linkage
GET /api/polymarket/canary-executor-contract
GET /api/polymarket/auto-governance
GET /api/polymarket/analyze/history?limit=80&q=keyword
GET /api/polymarket/ai-score
GET /api/polymarket/search?q=keyword&limit=36
```

These endpoints are API-first replacements for direct dashboard reads of:

- `QuantGod_PolymarketMarketRadar.json`
- `QuantGod_PolymarketCrossMarketLinkage.json`
- `QuantGod_PolymarketCanaryExecutorContract.json`
- `QuantGod_PolymarketAutoGovernance.json`
- `QuantGod_PolymarketSingleMarketAnalysis.json`
- `QuantGod_PolymarketSingleMarketAnalysisLedger.csv`
- `QuantGod_PolymarketAiScoreV1.json`

`/api/polymarket/analyze/history` combines the latest single-market analysis snapshot with historical rows from the read-only SQLite history helper. The Dashboard now prefers these endpoints and only falls back to local JSON/CSV files if the service is unavailable.

`/api/polymarket/search` is a unified search facade over the history DB, current opportunity radar, cross-market linkage, canary executor contract, auto-governance recommendations, latest single-market analysis/history, AI score snapshot, and persisted Worker V2 evidence. It returns `groupedResults`/`results` as market-level evidence groups, with duplicate radar/history/analysis/AI-score/worker/linkage/canary/governance rows folded into one comprehensive card per market. Worker run/trend/queue rows are a dedicated `worker` section with source labels, score, probability, trend direction, candidate id, queue state, next action, and run id carried into each compact evidence row. Cross-market linkage rows are a dedicated `crossLinkage` section carrying risk tags, matched keywords, linked MT5 symbols, macro risk state, and explicit `mt5ExecutionAllowed=false`. Canary contract rows are a dedicated `canary` section carrying contract id, isolated root/profile, canary stake limits, TP/SL, blockers, and `walletWriteAllowed=false` / `orderSendAllowed=false`. Auto-governance rows are a dedicated `autoGovernance` section carrying governance state, recommended action, risk level, blockers, next test, and closed wallet/order switches. Each group keeps its complete compact `evidence` list, and the response also keeps `rawResults` plus per-source counts so the Dashboard can expand all source evidence without rendering the same market repeatedly. The Dashboard detail layer supports per-source filtering and a copyable audit summary, so folded cards remain traceable when one market has radar, history, analysis, AI-score, dry-run, Worker V2, linkage, canary contract, and governance evidence at the same time.

This layer is intentionally a facade, not an executor: it does not read private keys, does not write wallets, does not call CLOB order APIs, does not start betting workers, and does not mutate MT5.

## History-Aware AI Score V1 + Semantic Reviewer

Run:

```bat
tools\score_polymarket_ai_v1.bat
```

The scorer consumes `archive\polymarket\history\QuantGod_PolymarketHistory.sqlite` and writes:

- `QuantGod_PolymarketAiScoreV1.json`
- `QuantGod_PolymarketAiScoreV1.csv`
- `QuantGod_PolymarketAiSemanticReview.json`

V1 is a transparent, history-aware scoring layer plus an optional LLM semantic reviewer. It always runs the deterministic history feature model, then, when an OpenAI-compatible API key is available through `OPENAI_API_KEY` or `QG_POLYMARKET_OPENAI_API_KEY`, it asks the reviewer to inspect market wording, event ambiguity, tail risk, history score, dry-run outcome, and next-test direction.

Control knobs:

```bat
set QG_POLYMARKET_AI_LLM_MODE=auto
set QG_POLYMARKET_AI_LLM_MAX_CANDIDATES=8
set QG_POLYMARKET_AI_LLM_MODEL=gpt-4o-mini
tools\score_polymarket_ai_v1.bat
```

`QG_POLYMARKET_AI_LLM_MODE=off` keeps the deterministic path. `required` fails fast if the semantic reviewer cannot run. The default batch file may read `D:\polymarket\.env`, but only for LLM-related keys; wallet/private-key values are ignored and never written to output.

Inputs:

- Gamma opportunity radar score, probability divergence, volume, and liquidity;
- single-market analysis recommendation, confidence, and risk;
- dry-run/outcome MFE, MAE, TP/SL/trailing evidence, and gate blockers;
- global executed/shadow/account quarantine evidence;
- optional LLM semantic assessment, risk factors, and next-test suggestion.

The output classifies markets as green/yellow/red for research priority only. Current decision remains `AI_SCORE_ONLY_NO_BETTING`: no private-key read, no wallet write, no CLOB order calls, no executor start, and no MT5 mutation. Green rows can only become higher-priority shadow/dry-run candidates until a separate execution gate, budget policy, stop-loss/take-profit manager, ledger audit, and kill switch are promoted.

## Cross-Market Linkage V1

Run:

```bat
tools\build_polymarket_cross_market_linkage.bat
```

The linkage builder consumes:

- `QuantGod_PolymarketMarketRadar.json`
- `QuantGod_PolymarketRadarWorkerV2.json`
- `QuantGod_PolymarketRadarTrendCache.json`
- `QuantGod_PolymarketRadarCandidateQueue.json`
- `QuantGod_PolymarketSingleMarketAnalysis.json`
- `QuantGod_PolymarketAiScoreV1.json`

It writes:

- `QuantGod_PolymarketCrossMarketLinkage.json`
- `QuantGod_PolymarketCrossMarketLinkage.csv`

Each linkage row maps Polymarket market text/category into awareness-only tags: `USD`, `JPY`, `XAU`, `RATES`, `WAR_GEOPOLITICS`, and `MACRO_RISK`. Rows include matched keywords, linked MT5 symbols such as `USDJPYc`, `EURUSDc`, and `XAUUSDc`, source types, confidence, macro risk state, and the safety fields `walletWriteAllowed=false`, `orderSendAllowed=false`, and `mt5ExecutionAllowed=false`.

This is not an execution bridge. It can only explain why a Polymarket event may be relevant to USD/JPY/XAU/rates/geopolitical awareness. It must not open MT5 trades, change EA live switches, place Polymarket bets, or promote a strategy by itself.

## Canary / Wallet Executor V2

Run:

```bat
tools\build_polymarket_canary_executor_contract.bat
tools\run_polymarket_canary_executor_v1.bat --plan-only
```

The canary contract builder consumes:

- `QuantGod_PolymarketExecutionGate.json`
- `QuantGod_PolymarketDryRunOrders.json`
- `QuantGod_PolymarketDryRunOutcomeWatcher.json`
- `QuantGod_PolymarketAiScoreV1.json`
- `QuantGod_PolymarketCrossMarketLinkage.json`
- `QuantGod_PolymarketMarketRadar.json`

It writes:

- `QuantGod_PolymarketCanaryExecutorContract.json`
- `QuantGod_PolymarketCanaryExecutorLedger.csv`
- `QuantGod_PolymarketCanaryExecutorRun.json`
- `QuantGod_PolymarketCanaryOrderAuditLedger.csv`
- `QuantGod_PolymarketCanaryPositionLedger.csv`
- `QuantGod_PolymarketCanaryExitLedger.csv`

V2 is a guarded real-money canary path, not an always-on betting bot. It can plan and audit a real-money order only when the evidence policy and runtime guard both pass.

Default evidence policy before automatic canary release:

- dry-run outcome samples >= 60;
- dry-run win rate >= 58%;
- dry-run profit factor >= 1.35;
- dry-run stop-loss rate <= 28%;
- max consecutive dry-run losses <= 3;
- average dry-run return >= 0.5%;
- AI score >= 82;
- composite score >= 85;
- no red cross-market risk, no global quarantine, and no execution-gate blocker.

Runtime guard before any wallet write:

- `QG_POLYMARKET_REAL_EXECUTION=true`;
- `QG_POLYMARKET_CANARY_ACK=REAL_MONEY_CANARY_OK`;
- `QG_POLYMARKET_CANARY_KILL_SWITCH=false`;
- `QG_POLYMARKET_WALLET_ADAPTER=isolated_clob`;
- lock file contains `REAL_MONEY_CANARY_OK`;
- isolated wallet/CLOB settings are configured.

The runner defaults to plan-only/audit behavior unless these guards pass. Current generated evidence is closed: `evidence_eligible=0`, `eligible_now=0`, `planned=0`, and `sent=0`. No Polymarket order was sent.

## Auto Promotion / Demotion Governance V2

Run:

```bat
tools\build_polymarket_auto_governance.bat
```

The auto-governance builder consumes:

- `QuantGod_PolymarketResearch.json`
- `QuantGod_PolymarketMarketRadar.json`
- `QuantGod_PolymarketRadarWorkerV2.json`
- `QuantGod_PolymarketRadarCandidateQueue.json`
- `QuantGod_PolymarketRetunePlanner.json`
- `QuantGod_PolymarketAiScoreV1.json`
- `QuantGod_PolymarketDryRunOutcomeWatcher.json`
- `QuantGod_PolymarketCrossMarketLinkage.json`
- `QuantGod_PolymarketCanaryExecutorContract.json`

It writes:

- `QuantGod_PolymarketAutoGovernance.json`
- `QuantGod_PolymarketAutoGovernanceLedger.csv`

V2 produces execution-aware promotion/demotion decisions by market. It can say a market is `AUTO_CANARY_EXECUTION_ELIGIBLE`, should remain in dry-run promotion review, should keep collecting shadow evidence, should retune, should demote to research-only, or should stay quarantined.

Governance can set `canPromoteToLiveExecution=true` only if the same real-money policy passes. It still cannot place orders by itself, cannot read private keys, cannot call CLOB, cannot mutate MT5, and cannot bypass the canary runner's runtime switches, lock file, kill switch, and isolated wallet adapter guard.

Current generated state remains conservative: `auto_canary=0` and `quarantine=28`.

## Retune Planner

Run:

```bat
tools\build_polymarket_retune_planner.bat
```

The planner consumes `QuantGod_PolymarketResearch.json` and emits shadow-only recommendations. It does not import Polymarket runtime modules, load wallet code, place orders, start executors, or mutate MT5.

Planner outputs include:

- global guardrails and blockers;
- per experiment-key severity, score, PF, win rate, realized PnL, and issue tags;
- shadow-only filter suggestions;
- next shadow test names and goals;
- explicit `liveExecutionAllowed=false` for every recommendation.

## Dashboard Surface

The QuantGod dashboard now starts from a workspace entry page. `MT5` and `Polymarket` are selected as separate workspaces, and the left navigation only shows the active workspace plus the entry link so the MT5 equity/open-position view is not mixed with Polymarket account cash. Inside the Polymarket workspace, the left navigation is further split into `治理总览`, `机会雷达`, `单市场分析`, `执行模拟`, and `重调账本` so research, dry-run execution review, and ledger/risk evidence are not stacked into one long page.

It displays:

- Safety boundary: DB is read-only, `.env` secret values are redacted in dashboard evidence, the canary executor is locked unless policy/runtime guards pass, and no Polymarket layer mutates MT5.
- Account snapshot: separate Polymarket cash and configured bankroll, never mixed with MT5 equity.
- Opportunity Radar: public Gamma scan with probability, liquidity, divergence, score, risk, and suggested shadow track.
- Single Market AI Analysis: URL/title/marketId focused analysis with market probability, AI/rule probability, divergence, confidence, risk factors, and shadow-track recommendation. The dashboard also reads `QuantGod_PolymarketSingleMarketAnalysisLedger.csv` to show a compact history list by time, recommendation, risk, divergence, confidence, probability, and shadow track, so the operator is not limited to the latest request JSON.
- Execution Gate: Chinese dashboard contract view for allowed-bet conditions, stake, TP/SL, max loss, market blocklist, cancel/exit, and audit requirements; currently blocks all candidates.
- Dry-Run Orders: Chinese dashboard view of simulated order size, entry price, TP/SL price, cancel time, exit time, and the execution-ledger schema. It does not connect to wallet/order APIs.
- Dry-Run Outcome Watcher: Chinese dashboard view of current simulated price, MFE/MAE, TP/SL/trailing/time exits, and whether an order would have exited. It remains observation-only.
- Historical Analysis DB: SQLite-backed research history with API-first search, row counts, recent opportunity rows, recent Worker V2 run/trend/queue rows, recent single-market analysis rows, recent simulated execution rows, recent canary executor run/audit rows, and the no-MT5 safety boundary. It falls back to the latest JSON snapshot only when the local dashboard API is unavailable.
- Cross-Market Linkage: awareness-only USD/JPY/XAU/rates/geopolitical/macroeconomic risk tags from Polymarket market wording, with linked MT5 symbols shown only as risk context and never as execution permission.
- Canary / Wallet Executor: isolated canary policy card plus executor preflight/audit panel with evidence eligibility, runtime guards, lock state, planned orders, sent count, and stop reasons. It remains plan-only/audit-only unless the evidence policy and runtime guards all pass.
- Auto Promotion / Demotion Governance: execution-aware governance panel showing auto-canary eligibility, dry-run review, keep-shadow, retune, demote, and quarantine decisions with blockers and next tests. It can only release a candidate to the guarded canary runner when all policy checks pass.
- Unified Evidence Search: `/api/polymarket/search` aggregates history, radar, cross-market linkage, canary contract, canary executor run/audit, auto-governance, single-market analysis, AI score, and Worker V2 run/trend/queue evidence into one read-only Dashboard query box, then folds duplicate rows by market into comprehensive evidence cards. Each card previews the strongest evidence, expands all compact raw evidence rows, filters the expanded audit rows by source, copies a compact audit summary, carries Worker candidate/run/queue/trend details, linkage risk tags/linked symbols, canary blockers/stake limits, executor preflight/audit state, and governance state/recommended action, and can jump to the single-market analysis/history workspace with the market query prefilled.
- Historical AI Score V1: history-aware green/yellow/red research scoring by market, using radar, single-market analysis, dry-run/outcome, global quarantine evidence, and optional LLM semantic review. The Dashboard shows history score vs semantic score, reviewer confidence, and reviewer next-test reasoning; it remains `AI_SCORE_ONLY_NO_BETTING`.
- Executed live evidence.
- No-money shadow evidence.
- Shadow-only Retune Planner.
- Experiment buckets by `experiment_key`.
- Latest PnL log.
- Risk-log event families.
- Recent journal rows.
- Governance decision and blockers.

## Current Evidence Snapshot

The first bridge run on 2026-04-28 produced:

- Executed: 24 closed, win rate 4.17%, PF 0.0145, realized PnL about -$9.98.
- Shadow: 383 closed, win rate 36.29%, PF 0.7055, realized PnL about -$159.33.
- All journal buckets: PF below 1, realized PnL negative.
- Account snapshot: read-only CLOB cash is displayed separately from MT5; the first verified snapshot showed cash below the configured Polymarket bankroll and no open orders.

The dashboard decision is therefore:

```text
PLAN_ONLY_NO_REAL_ORDER_AUTHORIZED
```

This means Polymarket evidence can help diagnose and design retunes. Live execution is not authorized by the current evidence. A real canary order can only appear after dry-run outcomes, AI score, governance, cross-market risk, lock file, kill switch, wallet adapter, and isolated CLOB settings all pass the V2 guard.

## Refactor Direction

Worth keeping from Polymarket:

- Executed vs shadow vs experiment separation.
- Risk-log blocker families.
- PnL and journal summary rollups.
- Sports/esports scope separation.
- Canary/rollback mindset.
- Dashboard-only evidence snapshots.

Not merged in this research slice:

- Production-scale wallet/executor/live betting modules. The current module is canary-only, isolated, locked by policy and runtime switches, and generated no real order on the current evidence.
- Auth/user/product modules.
- Long-running Flask/Socket.IO service.
- Database-backed strategy CRUD.
- Any execution path that bypasses Governance Advisor and the safety gate.

## Next Safe Work

Implemented as `tools\build_polymarket_retune_planner.py`: it consumes `QuantGod_PolymarketResearch.json` and emits candidate research ideas only, such as:

- which experiment keys are retired;
- which sample buckets need stricter filters;
- which sports/esports scopes should stay separated;
- which recovery rule should be replayed in shadow-only mode.

It should remain file-based and research-only until both executed and shadow evidence stop contradicting it.
