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

Status: mostly done, pending polish after worker.

Target: keep SQLite as the durable source, add any tables required by worker trend cache and semantic-review audit history.

## 4. Search / History API

Status: mostly done, pending worker/semantic fields.

Target: keep `history/radar/analyze/history/ai-score/search` read-only and extend facades only after new worker/history fields exist.

## 5. Cross-Market Linkage

Status: pending.

Target: map Polymarket event categories and keywords to USD, JPY, XAU, rates, war/geopolitical, and macro risk tags for MT5-side awareness without changing MT5 execution.

## 6. Canary / Wallet Executor

Status: pending.

Target: design a separated canary executor with read/write isolation, stake budget, TP/SL, cancel/exit, kill switch, and ledger audit. No real wallet wiring until Gate and dry-run outcome evidence support it.

## 7. Polymarket Auto Promotion / Demotion Governance

Status: pending.

Target: use history library, semantic AI score, dry-run outcomes, risk budgets, and worker trend evidence to promote/demote shadow tracks automatically. This must not enable wallet execution by itself.
