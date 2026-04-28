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
- `QuantGod_PolymarketMarketRadar.json`
- `QuantGod_PolymarketMarketRadar.csv`
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

The V1 tables are:

- `qd_polymarket_runs`
- `qd_polymarket_asset_opportunities`
- `qd_polymarket_market_analysis`
- `qd_polymarket_execution_simulations`
- `qd_polymarket_research_snapshots`

This closes the first persistence gap from the QuantDinger-style workflow: opportunity radar rows, single-market analysis rows, dry-run/outcome rows, and high-level research snapshots are no longer only latest JSON/CSV snapshots. They can be searched, counted, reviewed later, and used as the stable input for future AI scoring.

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
GET /api/polymarket/analyze/history?limit=80&q=keyword
GET /api/polymarket/ai-score
GET /api/polymarket/search?q=keyword&limit=36
```

These endpoints are API-first replacements for direct dashboard reads of:

- `QuantGod_PolymarketMarketRadar.json`
- `QuantGod_PolymarketSingleMarketAnalysis.json`
- `QuantGod_PolymarketSingleMarketAnalysisLedger.csv`
- `QuantGod_PolymarketAiScoreV1.json`

`/api/polymarket/analyze/history` combines the latest single-market analysis snapshot with historical rows from the read-only SQLite history helper. The Dashboard now prefers these endpoints and only falls back to local JSON/CSV files if the service is unavailable.

`/api/polymarket/search` is a unified search facade over the history DB, current opportunity radar, latest single-market analysis/history, and AI score snapshot. It now returns `groupedResults`/`results` as market-level evidence groups, with duplicate radar/history/analysis/AI-score rows folded into one comprehensive card per market. It also keeps `rawResults` and per-source counts so the Dashboard can drill back into source evidence without rendering the same market repeatedly.

This layer is intentionally a facade, not an executor: it does not read private keys, does not write wallets, does not call CLOB order APIs, does not start betting workers, and does not mutate MT5.

## History-Aware AI Score V1

Run:

```bat
tools\score_polymarket_ai_v1.bat
```

The scorer consumes `archive\polymarket\history\QuantGod_PolymarketHistory.sqlite` and writes:

- `QuantGod_PolymarketAiScoreV1.json`
- `QuantGod_PolymarketAiScoreV1.csv`

V1 is a transparent, history-aware scoring layer over:

- Gamma opportunity radar score, probability divergence, volume, and liquidity;
- single-market analysis recommendation, confidence, and risk;
- dry-run/outcome MFE, MAE, TP/SL/trailing evidence, and gate blockers;
- global executed/shadow/account quarantine evidence.

The output classifies markets as green/yellow/red for research priority only. Current decision remains `AI_SCORE_ONLY_NO_BETTING`: no private-key read, no wallet write, no CLOB order calls, no executor start, and no MT5 mutation. Green rows can only become higher-priority shadow/dry-run candidates until a separate execution gate, budget policy, stop-loss/take-profit manager, ledger audit, and kill switch are promoted.

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

- Safety boundary: DB is read-only, `.env` secret values are redacted, no executor, no MT5 mutation.
- Account snapshot: separate Polymarket cash and configured bankroll, never mixed with MT5 equity.
- Opportunity Radar: public Gamma scan with probability, liquidity, divergence, score, risk, and suggested shadow track.
- Single Market AI Analysis: URL/title/marketId focused analysis with market probability, AI/rule probability, divergence, confidence, risk factors, and shadow-track recommendation. The dashboard also reads `QuantGod_PolymarketSingleMarketAnalysisLedger.csv` to show a compact history list by time, recommendation, risk, divergence, confidence, probability, and shadow track, so the operator is not limited to the latest request JSON.
- Execution Gate: Chinese dashboard contract view for allowed-bet conditions, stake, TP/SL, max loss, market blocklist, cancel/exit, and audit requirements; currently blocks all candidates.
- Dry-Run Orders: Chinese dashboard view of simulated order size, entry price, TP/SL price, cancel time, exit time, and the execution-ledger schema. It does not connect to wallet/order APIs.
- Dry-Run Outcome Watcher: Chinese dashboard view of current simulated price, MFE/MAE, TP/SL/trailing/time exits, and whether an order would have exited. It remains observation-only.
- Historical Analysis DB: SQLite-backed research history with API-first search, row counts, recent opportunity rows, recent single-market analysis rows, recent simulated execution rows, and the no-wallet/no-MT5 safety boundary. It falls back to the latest JSON snapshot only when the local dashboard API is unavailable.
- Unified Evidence Search: `/api/polymarket/search` aggregates history, radar, single-market analysis, and AI score evidence into one read-only Dashboard query box, then folds duplicate rows by market into comprehensive evidence cards.
- Historical AI Score V1: history-aware green/yellow/red research scoring by market, using radar, single-market analysis, dry-run/outcome, and global quarantine evidence; it remains `AI_SCORE_ONLY_NO_BETTING`.
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

This means Polymarket evidence can help diagnose and design retunes. Live execution is not restored by the research bridge, radar, or retune planner; if it is reintroduced later, it must be explicitly promoted through a separate wallet/execution guard with TP/SL and loss controls.

## Refactor Direction

Worth keeping from Polymarket:

- Executed vs shadow vs experiment separation.
- Risk-log blocker families.
- PnL and journal summary rollups.
- Sports/esports scope separation.
- Canary/rollback mindset.
- Dashboard-only evidence snapshots.

Not merged in this research slice:

- Wallet/executor/live canary modules. They are allowed only as a later, separately gated execution module with bankroll isolation, TP/SL, max-loss, audit ledger, and kill-switch wiring. `Execution Gate V1` plus the dry-run execution ledger are prerequisites, not the executor.
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
