# QuantGod Polymarket Research Integration

This document records how the local `D:\polymarket` project is integrated into QuantGod without conflicting with MT5/HFM execution.

## Boundary

The integration is research-only.

- Reads `D:\polymarket\copybot.db` through SQLite `mode=ro` and `PRAGMA query_only=ON`.
- Does not import Polymarket application modules.
- Reads `D:\polymarket\.env` only for the optional account-cash snapshot, redacts secret values, and never writes them to dashboard output.
- Does not start Polymarket `main.py`, `web.py`, executor loops, canary loops, or order-send code.
- Does not mutate MT5 EA source, live presets, account/server settings, lot size, SL/TP, kill switches, or order paths.

The generated file is only a dashboard evidence supplement:

- `QuantGod_PolymarketResearch.json`
- `QuantGod_PolymarketResearchLedger.csv`
- `QuantGod_PolymarketRetunePlanner.json`
- `QuantGod_PolymarketRetunePlanner.csv`

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
- `Dashboard\`, for the local `http://localhost:8080/QuantGod_Dashboard.html` static dashboard server.

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

The QuantGod dashboard now starts from a workspace entry page. `MT5` and `Polymarket` are selected as separate workspaces, and the left navigation only shows the active workspace plus the entry link so the MT5 equity/open-position view is not mixed with Polymarket account cash.

It displays:

- Safety boundary: DB is read-only, `.env` secret values are redacted, no executor, no MT5 mutation.
- Account snapshot: separate Polymarket cash and configured bankroll, never mixed with MT5 equity.
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
RESEARCH_ONLY_DO_NOT_ENABLE_LIVE
```

This means Polymarket evidence can help diagnose and design retunes, but it should not resume live execution or merge order-execution code into QuantGod.

## Refactor Direction

Worth keeping from Polymarket:

- Executed vs shadow vs experiment separation.
- Risk-log blocker families.
- PnL and journal summary rollups.
- Sports/esports scope separation.
- Canary/rollback mindset.
- Dashboard-only evidence snapshots.

Not worth merging into QuantGod now:

- Wallet/executor/live canary modules.
- Auth/user/product modules.
- Long-running Flask/Socket.IO service.
- Database-backed strategy CRUD.
- Any non-EA execution path.

## Next Safe Work

Implemented as `tools\build_polymarket_retune_planner.py`: it consumes `QuantGod_PolymarketResearch.json` and emits candidate research ideas only, such as:

- which experiment keys are retired;
- which sample buckets need stricter filters;
- which sports/esports scopes should stay separated;
- which recovery rule should be replayed in shadow-only mode.

It should remain file-based and research-only until both executed and shadow evidence stop contradicting it.
