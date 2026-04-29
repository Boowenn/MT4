# QuantGod Polymarket Sequential Migration Plan

Branch: `feature/polymarket-real-executor-governance`

Rule: finish, verify, and commit one item before starting the next. MT5 branches and MT5 live-pilot work are out of scope for this branch.

## 1. True AI Scoring

Status: completed.

- `tools/score_polymarket_ai_v1.py` supports history-aware scoring plus optional LLM semantic review.
- Output remains compatible with `QuantGod_PolymarketAiScoreV1.json/csv` and adds `QuantGod_PolymarketAiSemanticReview.json`.
- Safety: no wallet writes, no CLOB order calls, no executor start, no MT5 mutation.

## 2. Batch Opportunity Radar V2 / Worker

Status: completed.

- `tools/run_polymarket_radar_worker_v2.py` wraps Gamma Radar V1 with bounded cycles, trend cache, market deduplication, and a shadow-only queue.
- Writes `QuantGod_PolymarketRadarWorkerV2.json/csv`, `QuantGod_PolymarketRadarTrendCache.json`, and `QuantGod_PolymarketRadarCandidateQueue.json/csv`.
- Safety: no env secret read, no wallet write, no order execution, no MT5 mutation.

## 3. Historical Analysis Library

Status: completed.

- SQLite history persists radar, market catalog, related assets, Worker V2 trend/queue/run evidence, cross-market linkage, canary contracts, auto governance, dry-run/outcome rows, and research snapshots.
- Current DB schema is `POLYMARKET_HISTORY_DB_V7_REAL_CANARY_GOVERNANCE`.
- Safety: local research memory only; no wallet write, no CLOB call, no executor start, no MT5 mutation.

## 4. Search / History API

Status: completed.

- `/api/polymarket/history` and `/api/polymarket/search` expose the local SQLite/history evidence through read-only APIs.
- Unified search folds radar, history, single-market analysis, AI score, Worker V2, cross-market linkage, canary contract, canary executor run/audit, and auto-governance rows into comprehensive evidence cards.
- Safety: facade only; no wallet write, no CLOB call, no executor start, no MT5 mutation.

## 5. Cross-Market Linkage

Status: completed.

- `tools/build_polymarket_cross_market_linkage.py` maps Polymarket wording into awareness tags: `USD`, `JPY`, `XAU`, `RATES`, `WAR_GEOPOLITICS`, and `MACRO_RISK`.
- Rows include matched keywords, linked MT5 symbols, confidence, macro risk state, and execution blockers.
- Safety: risk context only; it cannot open MT5 trades, change EA switches, place Polymarket bets, or promote a strategy by itself.

## 6. Canary / Wallet Executor

Status: completed as guarded real-money canary V2.

- `tools/polymarket_governance_utils.py` centralizes readiness scoring.
- `tools/build_polymarket_canary_executor_contract.py` now writes `POLYMARKET_CANARY_EXECUTOR_CONTRACT_V2`.
- `tools/run_polymarket_canary_executor_v1.py` and `.bat` implement the guarded canary runner.
- The contract evaluates dry-run outcome samples, win rate, profit factor, average return, stop-loss rate, consecutive losses, AI score, composite score, cross-market risk, and gate state before a candidate can become real-money eligible.
- The default auto-open threshold is intentionally conservative: at least 60 dry-run outcome samples, win rate >= 58%, PF >= 1.35, stop-loss rate <= 28%, max consecutive losses <= 3, average return >= 0.5%, AI score >= 82, composite score >= 85, and no red cross-market/global-quarantine blocker.
- Real-money execution remains closed unless all runtime guards pass: `QG_POLYMARKET_REAL_EXECUTION=true`, `QG_POLYMARKET_CANARY_ACK=REAL_MONEY_CANARY_OK`, `QG_POLYMARKET_CANARY_KILL_SWITCH=false`, `QG_POLYMARKET_WALLET_ADAPTER=isolated_clob`, a matching lock file exists, and isolated wallet/CLOB settings are configured.
- The runner writes `QuantGod_PolymarketCanaryExecutorRun.json`, `QuantGod_PolymarketCanaryOrderAuditLedger.csv`, `QuantGod_PolymarketCanaryPositionLedger.csv`, and `QuantGod_PolymarketCanaryExitLedger.csv`.
- Current generated evidence has `evidence_eligible=0`, `eligible_now=0`, `planned=0`, and `sent=0`; no wallet order was sent.
- Safety: the executor can build and audit a real-money plan, but it does not consume retries or send orders for red, quarantined, or under-sampled candidates, and it never mutates MT5.

## 7. Polymarket Auto Promotion / Demotion Governance

Status: completed as execution-aware governance V2.

- `tools/build_polymarket_auto_governance.py` now writes `POLYMARKET_AUTO_GOVERNANCE_V2`.
- Governance reads Research, Gamma Radar, Worker V2 queue/trend evidence, Retune Planner, AI Score, dry-run outcomes, Cross-Market Linkage, and Canary contract snapshots.
- V2 emits `AUTO_CANARY_EXECUTION_ELIGIBLE`, `PROMOTION_REVIEW_DRY_RUN`, `KEEP_SHADOW_COLLECT_EVIDENCE`, `RETUNE_REQUIRED`, `DEMOTE_TO_RESEARCH_ONLY`, and `QUARANTINE_NO_PROMOTION`.
- Governance can mark `canPromoteToLiveExecution=true` only when the full real-money policy passes. It still cannot bypass the canary runner's runtime switches, lock file, kill switch, or wallet adapter guard.
- Current generated state is conservative: `auto_canary=0` and `quarantine=28`.
- Safety: no private-key read, no wallet write, no CLOB order call, no MT5 mutation.

## 8. QuantDinger Market Catalog / Related Asset Browser

Status: completed.

- `tools/build_polymarket_quantdinger_parity.py` writes `QuantGod_PolymarketMarketCatalog.json/csv` and `QuantGod_PolymarketAssetOpportunities.json/csv`.
- Dashboard server exposes `/api/polymarket/markets`, `/api/polymarket/market`, and `/api/polymarket/asset-opportunities`.
- Dashboard has a Polymarket market browser with search, category/risk/sort filters, selected-market details, and related-asset opportunity cards.
- Safety: related MT5 symbols are risk-context tags only.

## Current Status

All planned Polymarket migration and QuantDinger parity items are implemented on this branch, including a guarded real-money canary executor path. The current evidence does not authorize any real Polymarket order, so the executor run remains plan-only/audit-only until dry-run outcome, AI score, governance, lock, kill switch, and isolated wallet guards all pass.
