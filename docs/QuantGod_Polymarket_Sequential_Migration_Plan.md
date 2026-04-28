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

Status: pending.

Target: turn one-shot Gamma Radar V1 into a controlled worker that can refresh active markets on a cadence, cache trend deltas, deduplicate markets, and enqueue analysis candidates without wallet execution.

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
