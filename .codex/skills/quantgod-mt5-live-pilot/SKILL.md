---
name: quantgod-mt5-live-pilot
description: Operate, review, and modify the QuantGod HFM MT5 live-pilot system in this repository. Use when working on the MT5 live-pilot EA, HFM runtime exports, dashboard, local server, launchers, pilot telemetry, news filtering, or the repo-local operating guidance for the current MT5 production path. Trigger this skill for requests about HFM live-pilot monitoring, strategy evaluation, data-pipeline debugging, dashboard mismatches, MT5 execution tuning, or turning project knowledge into stable repo-local guidance.
---

# QuantGod MT5 Live Pilot

## Quick Start

- Read [references/current-state.md](references/current-state.md) before changing behavior or documenting system status.
- Treat the HFM Cent live-account runtime under `C:\Program Files\HFM Metatrader 5\MQL5\Files\` as the source of truth for current live counts, pilot telemetry, and recent outcomes.
- Treat `QuantGod_GovernanceAdvisor.json`, `QuantGod_StrategyVersionRegistry.json`, and `QuantGod_OptimizerV2Plan.json` as derived local advisory files from those runtime files. They help summarize route lifecycle state, strategy versions, and tester-only optimization proposals, but they are not execution paths.
- Treat the matching MT5 code and launcher files under `C:\Users\OWNER\QuantGod_MT4\` as the only writable source for current behavior changes.
- The generic `C:\Program Files\MetaTrader 5\MQL5\Files\` directory may still contain stale skeleton exports and should not be assumed to represent the live HFM account.
- MT4 is historical archive only. If you need old research evidence, use `tools/archive_mt4_runtime.ps1` and `archive/mt4-runtime-snapshots/`; do not treat MT4 as the live runtime.
- When docs and runtime disagree, trust code plus runtime exports first, then update the docs.

## Working Loop

1. Inspect the live runtime artifacts.
- For the HFM Cent live pilot, start under `C:\Program Files\HFM Metatrader 5\MQL5\Files\`.
- For HFM live-pilot journaling, also inspect `QuantGod_TradeJournal.csv`, `QuantGod_CloseHistory.csv`, `QuantGod_TradeOutcomeLabels.csv`, and `QuantGod_TradeEventLinks.csv`.
- For promotion/demotion or route-quality questions, also inspect or regenerate `QuantGod_StrategyVersionRegistry.json`, `QuantGod_OptimizerV2Plan.json`, and `QuantGod_GovernanceAdvisor.json` with `tools\build_strategy_version_registry.py`, `tools\build_optimizer_v2_plan.py`, and `tools\build_governance_advisor.py`.
- Decide whether the issue is in execution, aggregation, export, or frontend rendering.

2. Trace the matching code path.
- MT5 migration skeleton export logic lives in `MQL5/Experts/QuantGod_MultiStrategy.mq5`.
- MT5 startup automation for phase 1 lives in `MQL5/Config/QuantGod_MT5_Start.ini` and `Start_QuantGod_MT5.bat`.
- HFM shadow startup automation lives in `MQL5/Config/QuantGod_MT5_HFM_Shadow.ini` and `Start_QuantGod_MT5_HFM_Shadow.bat`.
- HFM live-pilot startup automation lives in `MQL5/Config/QuantGod_MT5_HFM_LivePilot.ini`, `MQL5/Presets/QuantGod_MT5_HFM_LivePilot.set`, and `Start_QuantGod_MT5_HFM_LivePilot.bat`.
- MT4 runtime archive automation lives in `tools/archive_mt4_runtime.ps1`.
- Dashboard rendering lives in `Dashboard/QuantGod_Dashboard.html`.

3. Protect research statistics before trusting conclusions.
- Validate how `researchLots`, `researchNet`, `TradeEventLinks`, and `TradeOutcomeLabels` are derived.
- Prefer ticket-linked metadata over parsing fragile text fields when both exist.
- Do not recommend strategy changes from dashboard summaries alone if the data pipeline is suspect.

4. Keep documentation stable and low-maintenance.
- Store durable architecture and workflow guidance here in the skill.
- Keep this skill as the canonical repo-local knowledge base for Codex-style maintenance work.
- Point volatile numbers back to runtime exports instead of hardcoding them into canonical docs.
- Treat HFM MT5 as the primary runtime and GitHub-facing operating path.
- After any Codex-made code, configuration, dashboard, documentation, or automation change, keep local and GitHub `main` consistent: run the appropriate self-tests/compile/syntax checks for the change, then commit and push automatically when those checks pass. Do not auto-push unverified changes.
- Treat MT4 only as archived research context unless the user explicitly asks to reopen old MT4 work.
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
- Remember that `EURUSD / MACD_Divergence` now also has a research-only downtrend guard: in virtual research mode it skips bullish divergence buys during `TREND_DOWN` and `TREND_EXP_DOWN`.
- Remember that `EURUSD / BB_Triple` now also has a research-only downtrend guard: in virtual research mode it skips buy setups during `TREND_EXP_DOWN`.
- Remember that the overview section now also contains a server-time `昨晚 vs 今天` research summary card, with windows split as `昨晚 20:00 -> 今天 08:00` and `今天 08:00 -> 现在`, using MT4 server timestamps instead of local desktop time.
- Remember that this summary card is no longer closed-trades-only; it now also surfaces window-scoped new opens and their current floating PnL, so "today has activity but no exits yet" does not look blank.
- Remember that MT5 is no longer shadow-only: the HFM client now has a constrained live pilot for `MA_Cross` at `0.01` lot using `M15` signal timing, `H1` trend filtering, a 5-bar fresh-crossover window, a 24-bar pullback-continuation entry window after recent crosses, and additional guards that block new range-regime entries, enforce a post-loss same-symbol cooldown, turn consecutive-loss pauses into a 180-minute timed auto-resume cooldown, move eligible profitable EA positions to breakeven and trailing-stop profit protection, and apply a conservative safety/trailing guard to manual positions across all symbols, including XAUUSDc, without counting them in strategy/regime research reports. Daily realized-loss and floating-loss kill switches remain hard pauses. Manual positions are separate from EA pilot positions and should not block same-symbol EA entries; the EA still keeps its own pilot-only position caps. The old MT4 `RSI_Reversal`, `BB_Triple`, `MACD_Divergence`, and `SR_Breakout` routes are now ported into MT5. The shipped HFM live preset enables only the old strong `USDJPY RSI_Reversal H1` among legacy routes; `BB_Triple`, `MACD_Divergence`, and `SR_Breakout` stay candidate/backtest-only until their iterated versions show stronger evidence. Any old live pilot position from a demoted route should be exited at breakeven/profit or at the small demoted-route loss threshold instead of waiting for its original TP/SL.
- Remember that the HFM live pilot now also applies a USD high-impact news filter through the MT5 economic calendar: it pre-blocks and post-blocks around tracked USD events, derives a short-lived USD directional bias from actual-versus-forecast results, and blocks `USDJPY` breakout buys near `160`.
- Remember that HFM MT5 exports broker-history journaling and regime labels for both manual/other activity and live-pilot trades; those files do not yet represent the full five-strategy QuantGod MT4 research engine.
- Remember that Backtest Lab V1 exists for the HFM MT5 path: it only covers `MA_Cross` on `EURUSDc` and `USDJPYc` at `0.01`, writes run artifacts under `archive/backtests/`, and publishes `QuantGod_BacktestSummary.json` for the dashboard `回测 vs 实盘` card.
- Remember that Backtest Lab V1 also has tester presets for the legacy MT4 route ports (`RSI_Reversal`, `BB_Triple`, `MACD_Divergence`, `SR_Breakout`) on `EURUSDc` and `USDJPYc` at `0.01`; the shipped HFM live preset keeps only `USDJPY RSI_Reversal H1` live-enabled among legacy routes while BB/MACD/SR iterate in candidate/backtest mode.
- Remember that route promotion/demotion is now automation-governed and evidence-driven: weak live routes should be demoted quickly to simulation/backtest and iterated there, while improved candidate routes can only be promoted after old-history context, Backtest Lab, candidate/outcome ledgers, and fresh `0.01` forward-style evidence agree and no guardrail is weakened.
- Remember that the QuantDinger-inspired Governance Advisor, Strategy Version Registry, Optimizer V2, and light dashboard shell are file-only and advisory: they combine Backtest Lab, live forward, Shadow/Outcome, Candidate/Outcome, Manual Alpha, local runtime-health evidence, strategy parameter hashes, parent/child version lineage, and tester-only next-generation proposals into `QuantGod_GovernanceAdvisor.json`, `QuantGod_StrategyVersionRegistry.json`, and `QuantGod_OptimizerV2Plan.json`, but must never store credentials, connect to HFM, send orders, mutate the HFM live preset, or bypass EA `OrderSend` gating.
- Remember that strategy loosening now needs a two-gate check: backtest support plus live `0.01` forward samples. Do not recommend widening risk or relaxing guards from only one side of that evidence.
- Remember that the dashboard trades section now also renders an HFM MT5 journal panel sourced from `QuantGod_TradeJournal.csv`, `QuantGod_CloseHistory.csv`, `QuantGod_TradeOutcomeLabels.csv`, and `QuantGod_TradeEventLinks.csv`; if those tables look blank or stale, debug the local CSV loading path before blaming the JSON export.
- Remember that the HFM Cent live runtime now runs against `C:\Program Files\HFM Metatrader 5\`; if dashboard data does not match the live account, check whether the operator accidentally opened the generic MT5 files folder instead of the HFM one.
- Remember that the HFM MT5 live pilot now also exports per-symbol `pilotTelemetry` counters into `QuantGod_Dashboard.json`, and the symbol overview cards surface those counters so operators can see whether the pilot is waiting for bars, missing crossovers, being blocked by news, or failing on spread/order-send.

- Remember that Shadow Signal Ledger now exists for the HFM MT5 path: it appends `QuantGod_ShadowSignalLedger.csv` rows for each new M15 `MA_Cross` pilot evaluation, including signals, no-cross observations, range/spread/session/news/cooldown blocks, and order-send outcomes. Shadow Outcome Ledger also exports `QuantGod_ShadowOutcomeLedger.csv` with completed 15/30/60 minute post-outcome labels for those shadow rows. Shadow Candidate Router V1 also exports `QuantGod_ShadowCandidateLedger.csv` and `QuantGod_ShadowCandidateOutcomeLedger.csv` for MA continuation/range-soft, RSI reversal, Bollinger reversal, MACD momentum turn, and support/resistance breakout candidates. These are learning surfaces only and must not trigger orders or loosen risk by themselves.
- Remember that Legacy Route Port V1 can write candidate rows for the newly ported old MT4 routes when route signals appear. Those rows are learning evidence unless a route-specific live switch is explicitly enabled after validation, and they must not loosen risk by themselves.
- Remember that Manual Alpha Ledger now exists for HFM MT5: it exports `QuantGod_ManualAlphaLedger.csv` for manual open/closed trades, including symbol, side, duration, regime transition, floating/realized profit, and a learn-only marker. Strong manual trades can become shadow-route candidates, but must not automatically expand live EA symbols, strategies, or lot size.

## Validation Rules

- Re-run any affected export path after changing research-stat logic.
- Re-run the MT5 JSON export and placeholder CSV export after changing the phase 1 MT5 skeleton.
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
- Check that MT5 phase 1 still exports `QuantGod_Dashboard.json`, `QuantGod_StrategyEvaluationReport.csv`, `QuantGod_RegimeEvaluationReport.csv`, and `QuantGod_OpportunityLabels.csv` into the active MT5 terminal data directory whenever you touch the migration skeleton or its launcher.
- For the HFM Cent live pilot launcher, verify those files under `C:\Program Files\HFM Metatrader 5\MQL5\Files\`.
- For HFM journaling changes, also verify `QuantGod_TradeJournal.csv`, `QuantGod_CloseHistory.csv`, `QuantGod_TradeOutcomeLabels.csv`, and `QuantGod_TradeEventLinks.csv` under the same directory.
- For HFM dashboard changes, also verify that the trades section renders the journal summary, event-link table, journal table, and close/outcome empty states or rows from those CSVs.
- For Backtest Lab changes, verify `tools/run_mt5_backtest_lab.ps1`, the `MQL5/Config/BacktestLab/` tester configs, the `MQL5/Presets/QuantGod_MT5_HFM_Backtest_*.set` files, `archive/backtests/latest/QuantGod_BacktestSummary.json`, and the dashboard `回测 vs 实盘` card.
- For Shadow Signal Ledger or Shadow Candidate Router changes, verify `QuantGod_ShadowSignalLedger.csv`, `QuantGod_ShadowOutcomeLedger.csv`, `QuantGod_ShadowCandidateLedger.csv`, and `QuantGod_ShadowCandidateOutcomeLedger.csv` under the HFM Files directory and the dashboard `Shadow Signal Ledger` card; the ledgers must add observations and post-outcome labels without changing `OrderSend` gating.
- For Manual Alpha Ledger changes, verify `QuantGod_ManualAlphaLedger.csv` under the HFM Files directory and the dashboard `Manual Alpha Ledger` card; manual alpha rows are evidence candidates only and must not alter live EA execution.
- For Governance Advisor, Strategy Version Registry, or Optimizer V2 changes, run `python tools\build_strategy_version_registry.py`, `python tools\build_optimizer_v2_plan.py`, and `python tools\build_governance_advisor.py`, verify the three JSON files under the HFM Files directory, and check the dashboard Strategy Workspace / Governance Advisor cards. These advisors must remain file-only and must not add a new broker/order path or mutate the live preset.
- For HFM news-filter changes, also verify the `news` object in `QuantGod_Dashboard.json` and the `news*` lines in `QuantGod_MT5_ShadowStatus.txt`, because the monitoring automation depends on those exports.
- For HFM live-pilot frequency debugging, also verify each symbol's `pilotTelemetry` object in `QuantGod_Dashboard.json` and the `Pilot 命中率` block in the symbol overview cards.
- If a change modifies design assumptions, update this skill in the same change.
- After every repair or behavior change, check whether the `QuantGod MT5监盘进化` automation instructions need to be updated too; if the operational rule changed, update the automation in the same pass so monitoring does not drift from the code.
- After every verified local change, commit and push to GitHub `main` so the local runtime, repo state, and remote default branch do not drift.

## References

- Read [references/current-state.md](references/current-state.md) for the stable system map, runtime source-of-truth rules, and current research constraints.
