# QuantGod Dashboard Vue Migration Status

Updated: 2026-04-29

Status: READ-ONLY ARCHIVE CANDIDATE ACTIVE

## Current Vue Coverage

The Vue workbench is now the primary operator surface at `http://localhost:8080/vue/`.

- Workspace shell: MT5, Polymarket, ParamLab, reports, and chart/trend workspaces are available through sidebar navigation without long-page scrolling.
- Deep evidence panels: MT5 positions/routes, Polymarket radar/search/AI/canary/cross-linkage, and ParamLab queue/result details have Vue equivalents.
- Chart/trend visuals: the old single-file dashboard chart layer has Vue coverage for MT5 Shadow blocker distribution, Shadow Outcome 15/30/60 minute posterior pips, Candidate route speed, MFE/MAE trend, ParamLab score/PF trend, Polymarket radar score/probability trend, AI score trend, Canary state, automatic governance actions, and cross-market risk tags.
- Data boundary: all Vue chart panels read existing JSON/CSV evidence only. They do not mutate MT5 execution, Polymarket wallet state, EA presets, or tester queues.

## Legacy `QuantGod_Dashboard.html` Status

`Dashboard/QuantGod_Dashboard.html` is now an active read-only archive candidate.

It remains available as a fallback, but it should not receive new product features. Keep it until:

- The Vue workbench is used through at least one normal monitoring cycle and one Strategy Tester / ParamLab review cycle.
- Any missing operator-only detail from the legacy page is either migrated or explicitly marked obsolete.
- The local dashboard server, README, and automation notes point to `/vue/` as the default view while retaining the legacy page as fallback.

## Candidate Period Rules

- `Dashboard/start_dashboard.bat` opens `/vue/` by default.
- `Dashboard/QuantGod_Dashboard.html` displays a visible archive-candidate banner and links operators back to `/vue/`.
- New UI work belongs in `frontend/src/**` and is published through `Dashboard/vue-dist/**`.
- The legacy HTML may receive only emergency display or fallback fixes.
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
