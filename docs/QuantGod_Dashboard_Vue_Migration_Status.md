# QuantGod Dashboard Vue Migration Status

Updated: 2026-04-29

Status: VUE PARITY POLISH ACTIVE, LEGACY FALLBACK RETAINED AND NOT FROZEN

## Current Vue Coverage

The Vue workbench is now the primary operator surface at `http://localhost:8080/vue/`.

- Workspace shell: MT5, Polymarket, ParamLab, reports, and chart/trend workspaces are available through sidebar navigation without long-page scrolling.
- Deep evidence panels: MT5 positions/routes, Polymarket radar/search/AI/canary/cross-linkage, and ParamLab queue/result details have Vue equivalents.
- Chart/trend visuals: the old single-file dashboard chart layer has Vue coverage for MT5 Shadow blocker distribution, Shadow Outcome 15/30/60 minute posterior pips, Candidate route speed, MFE/MAE trend, ParamLab score/PF trend, Polymarket radar score/probability trend, AI score trend, Canary state, automatic governance actions, and cross-market risk tags.
- ParamLab parity: the Vue ParamLab page now mirrors the old page's batch workflow more closely with queue/result/watcher aggregation, status filters, route filters, priority/score/time sorting, Auto Scheduler, Report Watcher, Run Recovery, AUTO_TESTER_WINDOW, and MT5ResearchStats drilldowns.
- Evidence report parity: the Vue reports page now includes evidence freshness, Strategy Evaluation, Regime Evaluation, MT5 trading audit, Manual Alpha, and raw drawers for Governance, AutoTesterWindow, MT5ResearchStats, Polymarket AI, and Canary contract evidence.
- Data boundary: all Vue chart panels read existing JSON/CSV evidence only. They do not mutate MT5 execution, Polymarket wallet state, EA presets, or tester queues.

## Vue Parity Polish Before Freeze

The legacy page must not be fully frozen while the Vue workbench still feels materially weaker for daily operation.

## Review Cycle Evidence

2026-04-29 JST read-only review:

- Normal Vue monitoring cycle: PASS. `/vue/#home`, `/vue/#mt5`, `/vue/#polymarket`, `/vue/#paramlab`, `/vue/#charts`, and `/vue/#reports` loaded without dashboard fetch errors. The MT5 page showed the fresh HFM snapshot with account `186054398`, server `HFMarketsGlobal-Live12`, status `CONNECTED`, equity around `$10000.03`, and zero open positions at the time of review.
- ParamLab / Strategy Tester review: PARTIAL PASS. Vue showed the ParamLab batch filters, route filters, Report Watcher, Run Recovery, AUTO_TESTER_WINDOW, MT5ResearchStats, charts, and evidence report tables. The local evidence still has `runTerminal=false`, `parsedReportCount=0`, `pendingReportCount=35`, and `AUTO_TESTER_WINDOW.canRunTerminal=false`, so this was a read-only queue/report review rather than a real Strategy Tester execution window review.
- Freeze decision: DO NOT FREEZE YET. Vue is usable for the daily monitoring surface, but the final archive gate still requires one allowed Strategy Tester / ParamLab report-return cycle where a tester report is produced, watched, parsed, scored, and reviewed from Vue without opening the legacy HTML page.

Current parity priorities:

- Complete one allowed Strategy Tester / ParamLab report-return cycle and confirm Vue covers queue, watcher, parsed result, score, recovery, and chart/report review without opening the old HTML page.
- Keep watching for operator-only gaps in MT5 route cards, ParamLab filters, trend charts, and evidence report tables during live use.
- Any remaining missing old-page detail must be either migrated or explicitly marked obsolete here before final freeze.

## Legacy `QuantGod_Dashboard.html` Status

`Dashboard/QuantGod_Dashboard.html` remains an active fallback page.

It remains available as a fallback and is not frozen yet. Keep it until:

- The Vue workbench is used through at least one normal monitoring cycle and one Strategy Tester / ParamLab review cycle.
- The Strategy Tester / ParamLab review must include a real report-return path, not just a config-only or waiting-report queue inspection.
- Any missing operator-only detail from the legacy page is either migrated or explicitly marked obsolete.
- The local dashboard server, README, and automation notes point to `/vue/` as the default view while retaining the legacy page as fallback.

## Candidate Period Rules

- `Dashboard/start_dashboard.bat` opens `/vue/` by default.
- `Dashboard/QuantGod_Dashboard.html` displays a visible archive-candidate banner and links operators back to `/vue/`.
- New UI work belongs in `frontend/src/**` and is published through `Dashboard/vue-dist/**`.
- The legacy HTML may receive emergency display/fallback fixes while Vue parity is still being verified.
- The legacy HTML must not become the default launcher target again unless Vue is temporarily unavailable.

## Final Archive Gate

Freeze `QuantGod_Dashboard.html` as a fully read-only archive only after:

- One normal monitoring cycle confirms the Vue workbench has the needed MT5/Polymarket/ParamLab operator evidence.
- One Strategy Tester / ParamLab review confirms `/vue/#paramlab` and `/vue/#charts` cover the old workflow.
- Any missing detail is migrated or explicitly declared obsolete in this document.
- The fallback link remains available for recovery.

After the checks above pass:

- Do not add new features to the single-file page.
- Apply only emergency display fixes if the Vue bundle cannot load.
- Keep new frontend work in `frontend/src/**` and rebuild to `Dashboard/vue-dist/**`.

This keeps the old page useful for recovery while preventing the system from drifting back into two active frontends.
