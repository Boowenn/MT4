# QuantGod MT4 Research: Current Stable Map

## Purpose

Use this reference when working on the QuantGod MT4 repository so you do not need to rediscover where execution, statistics, and presentation live.

Keep this file stable. Put durable architecture and workflow facts here. Do not turn it into a hand-maintained snapshot of changing row counts.

## Source of Truth Order

When project knowledge conflicts:

1. Runtime exports under `C:\Program Files (x86)\MetaTrader 4\MQL4\Files\`
2. Current EA behavior in `MQL4/Experts/QuantGod_MultiStrategy.mq4`
3. Dashboard rendering in `Dashboard/QuantGod_Dashboard.html`
4. Human-facing notes such as `README.md`

Use runtime files for live counts, recent trades, and latest adaptive states.

## Core Runtime Layers

### Execution Layer

- `MQL4/Experts/QuantGod_MultiStrategy.mq4`
- `MQL4/Include/QuantEngine.mqh`

Responsibilities:

- Manage the configured symbol watchlist
- Run the five built-in strategies
- Export dashboard JSON and CSV research artifacts
- Maintain virtual research-account statistics
- Apply protective adaptive control

### Presentation Layer

- `Dashboard/QuantGod_Dashboard.html`
- `Dashboard/dashboard_server.js`

Responsibilities:

- Read `QuantGod_Dashboard.json`
- Read evaluation and labeling CSVs
- Render per-symbol and per-strategy status
- Render the regime research heatmap from `QuantGod_RegimeEvaluationReport.csv`
- Render advisory research recommendations derived from `strategy x symbol x regime` slices
- Expose a left-navigation section layout so operators can jump between overview, monitor, trades, research, and reports
- Reuse the same recommendation layer inside the strategy evaluation table so the live row for each current slice shows its current research action
- Reuse the same recommendation layer inside the symbol overview strategy chips so operators can see each live `strategy x symbol` slice's current action without leaving the monitoring section
- Let operators expand each symbol overview strategy chip to inspect the matched `strategy x symbol x regime` slice, sample metrics, and whether the displayed action came from an exact match or a fallback rule
- Let operators jump from that provenance panel directly into the research suggestion panel or the regime heatmap, with symbol filter sync and visual focus on the matching slice when available

### Data Layer

Primary runtime files:

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

## Stable Design Facts

### Research Mode

- Research mode uses a virtual starting balance and risk model while executing real demo fills with a fixed micro lot.
- Demo account PnL is not the primary research metric.
- Research conclusions must follow the virtual-account pipeline, not raw broker profit alone.

### Adaptive Control

- Adaptive control is protective, not self-optimizing.
- It adjusts risk and activation state.
- It does not automatically mutate strategy parameters.
- The current implementation evaluates adaptive state independently for each `strategy x symbol` pair.
- Dashboard root `strategies` is scoped to the current dashboard focus symbol.
- Cross-symbol comparison should come from `QuantGod_StrategyEvaluationReport.csv` or `symbols[].strategies` in `QuantGod_Dashboard.json`.

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
