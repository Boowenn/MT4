# QuantGod Dashboard Vue Migration Status

Updated: 2026-04-29

## Current Vue Coverage

The Vue workbench is now the primary operator surface at `http://localhost:8080/vue/`.

- Workspace shell: MT5, Polymarket, ParamLab, reports, and chart/trend workspaces are available through sidebar navigation without long-page scrolling.
- Deep evidence panels: MT5 positions/routes, Polymarket radar/search/AI/canary/cross-linkage, and ParamLab queue/result details have Vue equivalents.
- Chart/trend visuals: the old single-file dashboard chart layer has Vue coverage for MT5 Shadow blocker distribution, Shadow Outcome 15/30/60 minute posterior pips, Candidate route speed, MFE/MAE trend, ParamLab score/PF trend, Polymarket radar score/probability trend, AI score trend, Canary state, automatic governance actions, and cross-market risk tags.
- Data boundary: all Vue chart panels read existing JSON/CSV evidence only. They do not mutate MT5 execution, Polymarket wallet state, EA presets, or tester queues.

## Legacy `QuantGod_Dashboard.html` Status

`Dashboard/QuantGod_Dashboard.html` should remain available as a read-only fallback for now.

It is ready to be treated as an archive candidate, but not deleted yet. Keep it until:

- The Vue workbench is used through at least one normal monitoring cycle and one Strategy Tester / ParamLab review cycle.
- Any missing operator-only detail from the legacy page is either migrated or explicitly marked obsolete.
- The local dashboard server, README, and automation notes point to `/vue/` as the default view while retaining the legacy page as fallback.

## Proposed Archive Rule

After the checks above pass, freeze `QuantGod_Dashboard.html` as read-only:

- Do not add new features to the single-file page.
- Apply only emergency display fixes if the Vue bundle cannot load.
- Keep new frontend work in `frontend/src/**` and rebuild to `Dashboard/vue-dist/**`.

This keeps the old page useful for recovery while preventing the system from drifting back into two active frontends.
