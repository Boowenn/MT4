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
- Do not mix one symbol's adaptive state into another symbol's evaluation.

### When Updating Documentation

- Keep reusable operator guidance here in the skill.
- Keep lightweight human-facing notes in `README.md` when needed.
- Put volatile numbers in runtime exports, not canonical docs.
