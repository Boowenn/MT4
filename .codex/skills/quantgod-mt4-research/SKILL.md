---
name: quantgod-mt4-research
description: Operate, review, and modify the QuantGod MT4 research system in this repository. Use when working on the MT4 EA, dashboard, runtime data exports, virtual research-account statistics, adaptive controls, or QuantGod design documentation. Trigger this skill for requests about strategy evaluation, data-pipeline debugging, dashboard mismatches, performance reviews, or turning project knowledge into stable repo-local guidance.
---

# QuantGod MT4 Research

## Quick Start

- Read [references/current-state.md](references/current-state.md) before changing behavior or documenting system status.
- Treat local MT4 runtime exports under `C:\Program Files (x86)\MetaTrader 4\MQL4\Files\` as the source of truth for live counts and recent outcomes.
- When docs and runtime disagree, trust code plus runtime exports first, then update the docs.

## Working Loop

1. Inspect the live runtime artifacts.
- Start with `QuantGod_Dashboard.json`, `QuantGod_StrategyEvaluationReport.csv`, `QuantGod_TradeOutcomeLabels.csv`, and `QuantGod_TradeEventLinks.csv`.
- Decide whether the issue is in execution, aggregation, export, or frontend rendering.

2. Trace the matching code path.
- EA and export logic live in `MQL4/Experts/QuantGod_MultiStrategy.mq4`.
- Shared trading helpers live in `MQL4/Include/QuantEngine.mqh`.
- Dashboard rendering lives in `Dashboard/QuantGod_Dashboard.html`.

3. Protect research statistics before trusting conclusions.
- Validate how `researchLots`, `researchNet`, `TradeEventLinks`, and `TradeOutcomeLabels` are derived.
- Prefer ticket-linked metadata over parsing fragile text fields when both exist.
- Do not recommend strategy changes from dashboard summaries alone if the data pipeline is suspect.

4. Keep documentation stable and low-maintenance.
- Store durable architecture and workflow guidance here in the skill.
- Keep this skill as the canonical repo-local knowledge base for Codex-style maintenance work.
- Point volatile numbers back to runtime exports instead of hardcoding them into canonical docs.

## Validation Rules

- Re-run any affected export path after changing research-stat logic.
- Check at least `QuantGod_Dashboard.json`, `QuantGod_TradeOutcomeLabels.csv`, `QuantGod_TradeJournal.csv`, and `QuantGod_BalanceHistory.csv` when a fix touches profit scaling or trade labeling.
- If a change modifies design assumptions, update this skill in the same change.

## References

- Read [references/current-state.md](references/current-state.md) for the stable system map, runtime source-of-truth rules, and current research constraints.
