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
- Start with `QuantGod_Dashboard.json`, `QuantGod_StrategyEvaluationReport.csv`, `QuantGod_RegimeEvaluationReport.csv`, `QuantGod_TradeOutcomeLabels.csv`, and `QuantGod_TradeEventLinks.csv`.
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
- Remember that dashboard root `strategies` now reflects the current dashboard focus symbol, while full cross-symbol adaptive truth lives in `QuantGod_StrategyEvaluationReport.csv` and `symbols[].strategies`.
- Remember that the dashboard now also renders a `strategy x regime` heatmap from `QuantGod_RegimeEvaluationReport.csv`; dashboard bugs may be in CSV parsing or in the frontend aggregation layer, not only in EA exports.
- Remember that the dashboard is now sectioned with a left-side navigation rail; when moving panels around, preserve the section anchors and sidebar navigation flow instead of reverting to an undifferentiated long page.
- Remember that the dashboard now derives explicit research recommendations from `strategy x symbol x regime` slices; these suggestions are advisory only and must not silently change live execution behavior.
- Remember that the strategy evaluation table now also shows the current research action for each live `strategy x symbol x timeframe x current-regime` slice, using the same recommendation layer as the heatmap and suggestion cards.
- Remember that the symbol overview strategy chips now also surface the current research action and fallback note for each live `strategy x symbol` slice; changes to recommendation matching must be checked there too.
- Remember that the symbol overview strategy chips now also expose a collapsible provenance panel that shows which `strategy x symbol x regime` slice was matched, whether it was exact or fallback, and the supporting sample metrics.
- Remember that the provenance panel now also contains jump links into the research section; those links are expected to sync the symbol filter and visually focus the matching suggestion card or heatmap cell when a match exists.
- Remember that research suggestion cards and heatmap cells now also support reverse jumps back into the monitor section; those jumps are expected to highlight the relevant symbol card and strategy chip, even when a heatmap cell represents multiple symbols.
- Remember that monitor focus now carries a breadcrumb explaining whether the current highlight came from a research suggestion card or a heatmap cell; stale monitor focus should be cleared when the operator jumps back into the research section.
- Remember that `EURUSD / RSI_Reversal` now has an additional research-only guard: when virtual research mode is on, that slice requires an exact RSI crossback, a tighter Bollinger touch, and it skips mean-reversion entries during `TREND_EXP*` regimes.
- Remember that the overview section now also contains a server-time `昨晚 vs 今天` research summary card, with windows split as `昨天 20:00 -> 今天 08:00` and `今天 08:00 -> 现在`, using MT4 server timestamps instead of local desktop time.
- Remember that this summary card is no longer closed-trades-only; it now also surfaces window-scoped new opens and their current floating PnL, so "today has activity but no exits yet" does not look blank.

## Validation Rules

- Re-run any affected export path after changing research-stat logic.
- Check at least `QuantGod_Dashboard.json`, `QuantGod_TradeOutcomeLabels.csv`, `QuantGod_TradeJournal.csv`, and `QuantGod_BalanceHistory.csv` when a fix touches profit scaling or trade labeling.
- Check `QuantGod_RegimeEvaluationReport.csv` whenever you change event linkage, regime attribution, or outcome labeling.
- Check the heatmap panel in `Dashboard/QuantGod_Dashboard.html` whenever you change regime-report columns, aggregation meaning, or symbol filtering behavior.
- Check the research suggestion panel whenever you change regime scoring thresholds, confidence handling, or the recommendation wording/priority logic.
- Check the strategy evaluation table whenever you change research recommendation matching, especially the fallback behavior when the current regime has no closed sample yet.
- Check the symbol overview strategy chips whenever you change research recommendation matching, because they now expose the same current-slice action without requiring the operator to scroll to the evaluation section.
- Check the symbol overview chip details whenever you change recommendation matching or fallback behavior, because operators now use that expanded panel to audit why a card is saying `KEEP / REDUCE / PAUSE`.
- Check the research jump links whenever you change recommendation matching, filter state, or research-section layout, because operators now rely on one-click jumps from monitoring cards into the aligned suggestion/heatmap slice.
- Check the reverse jumps from suggestion cards and heatmap cells whenever you change monitor-card markup or research aggregation, because operators now use those clicks to return to the right monitor card and strategy chip.
- Check the monitor breadcrumb whenever you change reverse-jump state handling, because operators now rely on that label to understand why a symbol card or strategy chip is highlighted.
- Check the `昨晚 vs 今天` summary card whenever you change trade timestamp parsing, server-time handling, the closed-trade aggregation path, or the open-trade/floating summary path.
- If a change modifies design assumptions, update this skill in the same change.

## References

- Read [references/current-state.md](references/current-state.md) for the stable system map, runtime source-of-truth rules, and current research constraints.
