# QuantGod Dashboard Vue Migration Status

Updated: 2026-04-29

Status: VUE ACTIVE, LEGACY SINGLE-FILE HTML RETIRED

## Current Vue Coverage

The Vue workbench is now the primary operator surface at `http://localhost:8080/vue/`.

- Workspace shell: MT5, Polymarket, ParamLab, reports, and chart/trend workspaces are available through sidebar navigation without long-page scrolling.
- Deep evidence panels: MT5 positions/routes, Polymarket radar/search/AI/canary/cross-linkage, and ParamLab queue/result details have Vue equivalents.
- Chart/trend visuals: the old single-file dashboard chart layer has Vue coverage for MT5 Shadow blocker distribution, Shadow Outcome 15/30/60 minute posterior pips, Candidate route speed, MFE/MAE trend, ParamLab score/PF trend, Polymarket radar score/probability trend, AI score trend, Canary state, automatic governance actions, and cross-market risk tags.
- ParamLab parity: the Vue ParamLab page now mirrors the old page's batch workflow more closely with queue/result/watcher aggregation, status filters, route filters, priority/score/time sorting, Auto Scheduler, Report Watcher, Run Recovery, AUTO_TESTER_WINDOW, and MT5ResearchStats drilldowns.
- Evidence report parity: the Vue reports page now includes evidence freshness, Strategy Evaluation, Regime Evaluation, MT5 trading audit, Manual Alpha, and raw drawers for Governance, AutoTesterWindow, MT5ResearchStats, Polymarket AI, and Canary contract evidence.
- Data boundary: all Vue chart panels read existing JSON/CSV evidence only. They do not mutate MT5 execution, Polymarket wallet state, EA presets, or tester queues.

## Vue Parity Polish After Retirement

The Vue page is the active frontend. Any remaining UI polish or operator workflow gaps should be fixed in `frontend/src/**` and rebuilt into `Dashboard/vue-dist/**`; do not add new features to the retired single-file page.

## Review Cycle Evidence

2026-04-29 JST read-only review:

- Normal Vue monitoring cycle: PASS. `/vue/#home`, `/vue/#mt5`, `/vue/#polymarket`, `/vue/#paramlab`, `/vue/#charts`, and `/vue/#reports` loaded without dashboard fetch errors. The MT5 page showed the fresh HFM snapshot with account `186054398`, server `HFMarketsGlobal-Live12`, status `CONNECTED`, equity around `$10000.03`, and zero open positions at the time of review.
- ParamLab / Strategy Tester review: PARTIAL PASS. Vue showed the ParamLab batch filters, route filters, Report Watcher, Run Recovery, AUTO_TESTER_WINDOW, MT5ResearchStats, charts, and evidence report tables. The local evidence still has `runTerminal=false`, `parsedReportCount=0`, `pendingReportCount=35`, and `AUTO_TESTER_WINDOW.canRunTerminal=false`, so this was a read-only queue/report review rather than a real Strategy Tester execution window review.
- Retirement decision: PASS. Vue is now the active operator surface. The legacy `QuantGod_Dashboard.html` file has been removed from the repo, and the old route redirects to `/vue/`.

Current Vue priorities:

- Complete one allowed Strategy Tester / ParamLab report-return cycle and confirm Vue covers queue, watcher, parsed result, score, recovery, and chart/report review without opening the old HTML page.
- Keep watching for operator-only gaps in MT5 route cards, ParamLab filters, trend charts, and evidence report tables during live use.
- Any future missing operator detail should be migrated into Vue or explicitly marked obsolete here.

## Legacy `QuantGod_Dashboard.html` Status

`Dashboard/QuantGod_Dashboard.html` has been retired and removed from the repository.

The local dashboard server redirects `/` and `/QuantGod_Dashboard.html` to `/vue/`. Launcher scripts copy `Dashboard/vue-dist/**` plus `dashboard_server.js` into MT5 Files instead of copying the old HTML.

## Active Frontend Rules

- `Dashboard/start_dashboard.bat` opens `/vue/` by default.
- New UI work belongs in `frontend/src/**` and is published through `Dashboard/vue-dist/**`.
- Do not restore `QuantGod_Dashboard.html` unless Vue cannot load and the restoration is explicitly approved.
- If a copied old HTML remains in an MT5 Files directory from an earlier deployment, the current server still redirects the route to Vue.
