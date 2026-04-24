# QuantGod MT5 Live Pilot: Current Stable Map

## Purpose

Use this reference when working on the QuantGod repository so you do not need to rediscover where execution, statistics, presentation, and migration scaffolding live.

Keep this file stable. Put durable architecture and workflow facts here. Do not turn it into a hand-maintained snapshot of changing row counts.

## Source of Truth Order

When project knowledge conflicts:

1. Runtime exports under `C:\Program Files\HFM Metatrader 5\MQL5\Files\`
2. Current MT5 live-pilot behavior in `MQL5/Experts/QuantGod_MultiStrategy.mq5`
3. Dashboard and local server rendering in `Dashboard/QuantGod_Dashboard.html` and `Dashboard/dashboard_server.js`
4. MT5 launch/config files such as `MQL5/Config/QuantGod_MT5_HFM_LivePilot.ini` and `MQL5/Presets/QuantGod_MT5_HFM_LivePilot.set`
5. Human-facing notes such as `README.md`

Use HFM MT5 runtime files for live counts, recent trades, pilot telemetry, and latest execution states.
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

Responsibilities:

- Export an MT5 `QuantGod_Dashboard.json` with a dashboard-compatible shape
- Export MT5 broker-history journaling files such as `QuantGod_TradeJournal.csv`, `QuantGod_CloseHistory.csv`, `QuantGod_TradeOutcomeLabels.csv`, and `QuantGod_TradeEventLinks.csv`
- Export MT5 evaluation files such as `QuantGod_StrategyEvaluationReport.csv`, `QuantGod_RegimeEvaluationReport.csv`, and `QuantGod_OpportunityLabels.csv`
- Reuse the existing dashboard assets against the active MT5 terminal files directory
- Reuse the existing dashboard assets against `C:\Program Files\HFM Metatrader 5\MQL5\Files\` for the HFM Cent live-account runtime path
- Use the official MT5 startup config mechanism to auto-open `EURUSD M1` and auto-load the phase 1 skeleton at terminal launch
- Run a constrained HFM Cent live pilot for `MA_Cross` only, with `0.01` lot, `M15` trigger + `H1` trend filter, a 3-bar fresh-crossover lookback window plus an extended pullback-continuation entry after recent crosses, one-position caps, hard `SL/TP`, kill switches, a same-symbol post-loss cooldown, a range-regime entry block, breakeven/small-profit SL protection for eligible profitable EA positions, conservative SL/max-loss safety protection for manual positions, and a USD high-impact news filter driven by the MT5 economic calendar

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
- In the monitor section, each HFM symbol card now also renders a `Pilot 命中率` block from `symbols[].pilotTelemetry`, so operators can inspect daily evaluations, signal hits, WAIT_BAR frequency, no-crossover misses, news blocks, and order-send outcomes without opening raw JSON
- Reuse the same recommendation layer inside the strategy evaluation table so the live row for each current slice shows its current research action
- Reuse the same recommendation layer inside the symbol overview strategy chips so operators can see each live `strategy x symbol` slice's current action without leaving the monitoring section
- Let operators expand each symbol overview strategy chip to inspect the matched `strategy x symbol x regime` slice, sample metrics, and whether the displayed action came from an exact match or a fallback rule
- Let operators jump from that provenance panel directly into the research suggestion panel or the regime heatmap, with symbol filter sync and visual focus on the matching slice when available
- Let operators jump back from research suggestion cards and regime heatmap cells into the monitor section, where the corresponding symbol card and strategy chip are visually focused for fast cross-checking
- Explain that monitor-section focus with a breadcrumb, so the operator can tell whether the current highlight came from a research suggestion card or from a heatmap cell

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

HFM Cent live runtime uses the same phase 1 export set, but writes it under:

- `C:\Program Files\HFM Metatrader 5\MQL5\Files\`

## Stable Design Facts

### Research Mode

- Research mode uses a virtual starting balance and risk model while executing real demo fills with a fixed micro lot.
- Demo account PnL is not the primary research metric.
- Research conclusions must follow the virtual-account pipeline, not raw broker profit alone.
- MT5 live pilot does not implement the old MT4 virtual research-account model; its dashboard export is broker-account runtime only.
- The HFM live pilot currently automates `MA_Cross` only at `0.01` lot with `M15` trigger + `H1` trend filter + 3-bar fresh-crossover lookback plus an extended pullback-continuation entry, and it now also blocks new entries in `RANGE` / `RANGE_TIGHT`, enforces a same-symbol cooldown after a losing exit, moves eligible profitable EA positions to breakeven/small-profit SL protection, and applies a conservative safety guard to manual positions without counting them in strategy/regime research reports; the other four strategies remain dashboard placeholders on MT5.
- The HFM live pilot now also exports a `news` state object and matching `news*` status lines so automation can react to USD event pre-blocks, post-release cooldowns, and short-lived directional bias windows.

### Adaptive Control

- Adaptive control is protective, not self-optimizing.
- It adjusts risk and activation state.
- It does not automatically mutate strategy parameters.
- The current implementation evaluates adaptive state independently for each `strategy x symbol` pair.
- `EURUSD / RSI_Reversal` also has an additional research-only execution guard: it requires an exact RSI threshold crossback, uses a tighter Bollinger touch, and skips new entries during `TREND_EXP*` regimes.
- `EURUSD / MACD_Divergence` now also has a research-only execution guard: it skips bullish divergence buys during `TREND_DOWN` and `TREND_EXP_DOWN`.
- `EURUSD / BB_Triple` now also has a research-only execution guard: it skips buy setups during `TREND_EXP_DOWN`.
- Dashboard root `strategies` is scoped to the current dashboard focus symbol.
- Cross-symbol comparison should come from `QuantGod_StrategyEvaluationReport.csv` or `symbols[].strategies` in `QuantGod_Dashboard.json`.
- MT5 phase 1 exports placeholder strategy and diagnostic objects only; they are there to keep the dashboard rendering stable during migration.
- In HFM live-pilot mode, `MA_Cross` becomes a real executable slice on MT5; the remaining MT5 strategies are still placeholders.

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
- If dashboard heatmap and raw CSV disagree, treat the CSV as the source of truth first and debug the frontend aggregation/filtering path.
- If research suggestions and heatmap disagree, debug the recommendation-threshold layer separately from the raw regime aggregation layer.
- Do not mix one symbol's adaptive state into another symbol's evaluation.

### When Updating Documentation

- Keep reusable operator guidance here in the skill.
- Keep lightweight human-facing notes in `README.md` when needed.
- Put volatile numbers in runtime exports, not canonical docs.
- Keep MT5 migration notes explicit about phase boundaries so the skeleton is not mistaken for a fully ported execution engine.
