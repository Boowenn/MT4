# QuantGod Polymarket Sequential Migration Plan

Branch: `feature/polymarket-sequential-plan`

Rule: finish, verify, and commit one item before starting the next. MT5 branches and MT5 live-pilot work are out of scope for this branch.

## 1. True AI Scoring

Status: completed in this branch.

- Upgraded `score_polymarket_ai_v1.py` from rule-only history scoring to optional LLM semantic review plus deterministic fallback.
- Keeps existing `QuantGod_PolymarketAiScoreV1.json/csv` compatibility and adds `QuantGod_PolymarketAiSemanticReview.json`.
- LLM keys are optional and limited to `OPENAI_API_KEY` / `QG_POLYMARKET_OPENAI_API_KEY`; wallet/private-key values are ignored.
- Safety remains research-only: no wallet writes, no CLOB order calls, no executor start, no MT5 mutation.
- Verified with `--llm-mode off`, `auto` without key, syntax checks, and an internal mocked semantic-review blend test.

Next item after this commit: `Batch Opportunity Radar V2 / Worker`.

## 2. Batch Opportunity Radar V2 / Worker

Status: completed in this branch.

- Added `tools/run_polymarket_radar_worker_v2.py` and `.bat`.
- Worker V2 wraps Gamma Radar V1 with bounded cycles, default one-shot mode, trend cache, deduplication, and a shadow-only analysis queue.
- Writes `QuantGod_PolymarketRadarWorkerV2.json/csv`, `QuantGod_PolymarketRadarTrendCache.json`, and `QuantGod_PolymarketRadarCandidateQueue.json/csv`.
- Refreshes compatible V1 radar output with trend annotations so the existing dashboard radar keeps working.
- Dashboard now has a read-only Worker V2 panel and `/api/polymarket/radar-worker`.
- Safety remains research-only: no env/secret load, no wallet write, no order execution, no executor start, no MT5 mutation.
- Verified with offline seed radar, live Gamma small batch, trend-cache recurrence pass, Python syntax check, Node syntax check, dashboard inline script syntax check, and `/api/polymarket/radar-worker` smoke test.

Next item after this commit: `Historical Analysis Library` polish for Worker V2 trend/queue persistence.

## 3. Historical Analysis Library

Status: completed in this branch.

- Upgraded the SQLite history builder to `POLYMARKET_HISTORY_DB_V2_WORKER_EVIDENCE`.
- Persisted Worker V2 evidence into `qd_polymarket_radar_worker_runs`, `qd_polymarket_radar_trends`, and `qd_polymarket_radar_queue`.
- Added run/trend/queue row counts and recent rows to `QuantGod_PolymarketHistoryDb.json/csv`.
- Extended the read-only history helper, dashboard server, and Dashboard filter UI with `worker-runs`, `worker-trends`, and `worker-queue`.
- Safety remains research-only: no private-key read, no wallet write, no CLOB order call, no executor start, no MT5 mutation.

Next item after this commit: `Search / History API` facade polish over the now-persisted worker fields.

## 4. Search / History API

Status: completed in this branch.

- Extended `/api/polymarket/search` to treat persisted Worker V2 evidence as first-class grouped evidence.
- Split Worker V2 rows into a dedicated `worker` section and summary count while keeping ordinary history rows separate.
- Worker run/trend/queue rows now contribute source labels, risk/recommendation, score, probability, probability delta, trend direction, candidate id, queue state, next action, and run id to the comprehensive evidence card.
- The Dashboard raw evidence drawer and copyable audit summary now expose Worker V2 queue/trend fields, so folded search cards stay auditable without opening the SQLite view manually.
- Safety remains research-only: no private-key read, no wallet write, no CLOB order call, no executor start, no MT5 mutation.

Next item after this commit: `Cross-Market Linkage`.

## 5. Cross-Market Linkage

Status: completed in this branch.

- Added `tools/build_polymarket_cross_market_linkage.py` and `.bat`.
- The builder reads the current radar, Worker V2 queue/trend cache, single-market analysis, and AI score snapshots, then maps market text into `USD`, `JPY`, `XAU`, `RATES`, `WAR_GEOPOLITICS`, and `MACRO_RISK`.
- It writes `QuantGod_PolymarketCrossMarketLinkage.json/csv` with matched keywords, linked MT5 symbols, confidence, macro risk state, source types, and explicit execution blockers.
- Upgraded the SQLite history builder/API to `POLYMARKET_HISTORY_DB_V3_CROSS_MARKET_LINKAGE`, adding `qd_polymarket_cross_market_linkage`, `/api/polymarket/cross-linkage`, and `table=cross-linkage` history search.
- `/api/polymarket/search` now folds cross-market linkage into the same comprehensive evidence cards, with raw evidence details showing risk tags, linked MT5 symbols, and `mt5ExecutionAllowed=false`.
- Dashboard now shows a dedicated `跨市场联动` panel and includes linkage counts in the history library.
- Safety remains research-only: no private-key read, no wallet write, no CLOB order call, no executor start, no MT5 mutation, and no MT5 permission change.

Next item after this commit: `Canary / Wallet Executor`, but only as a separately promoted design/execution item after explicit user request.

## 6. Canary / Wallet Executor

Status: completed in this branch as contract-only V1.

- Added `tools/build_polymarket_canary_executor_contract.py` and `.bat`.
- The builder reads Execution Gate, dry-run orders, dry-run outcomes, AI score, cross-market linkage, and radar snapshots.
- It writes `QuantGod_PolymarketCanaryExecutorContract.json` and `QuantGod_PolymarketCanaryExecutorLedger.csv`.
- V1 defines the isolated canary root, future env switch names, max single canary bet, max daily loss, max open canary positions, TP/SL, trailing, cancel, max-hold, exit-before-resolution, kill switch, and future audit ledgers.
- Every candidate remains `canaryEligibleNow=false`, `walletWriteAllowed=false`, `orderSendAllowed=false`, and `startsExecutor=false`.
- Upgraded the SQLite history builder/API to `POLYMARKET_HISTORY_DB_V4_CANARY_CONTRACT`, adding `qd_polymarket_canary_contracts`, `table=canary-contracts`, and `/api/polymarket/canary-executor-contract`.
- `/api/polymarket/search` now folds Canary contract evidence into the same comprehensive evidence cards.
- Dashboard now shows a dedicated Canary contract panel under Polymarket execution simulation and includes Canary contract counts in the history library.
- Safety remains contract-only: no private-key read, no env secret read, no wallet write, no CLOB order call, no canary/executor start, no MT5 mutation.

## 7. Polymarket Auto Promotion / Demotion Governance

Status: pending.

Target: use history library, semantic AI score, dry-run outcomes, risk budgets, and worker trend evidence to promote/demote shadow tracks automatically. This must not enable wallet execution by itself.
