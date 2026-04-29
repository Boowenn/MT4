# 2026-04-27 BB_Triple unauthorized live order

## Status

Closed for prevention. Root cause is classified as a live-preset exposure window, with additional hardening added after the incident.

## Incident

- Open time: `2026.04.27 13:24`
- Close time: `2026.04.27 15:20`
- Symbol: `EURUSDc`
- Direction: `SELL`
- Lots: `0.01`
- Strategy: `BB_Triple`
- Source: `EA`
- Comment: `QG_BB_Triple_MT5_SELL`
- Net result: `-1.35 USC`
- Entry regime: `TREND_UP`
- Exit regime: `RANGE`

This trade should be treated as incident-contaminated evidence for BB_Triple live-forward review. It remains in broker-derived CloseHistory and raw GovernanceAdvisor liveForward totals so the account history is not rewritten, but it should not be used as clean promotion evidence until an incident override/exclusion ledger is implemented.

## Evidence

- `136280c Enable all legacy MT5 live pilot routes` was committed on `2026-04-27 18:12:05 +0900` and changed the HFM live preset route switches so `EnablePilotBBH1Live=true`, `EnablePilotMacdH1Live=true`, and `EnablePilotSRM15Live=true`.
- The BB_Triple `EURUSDc` order opened during that exposure window.
- `b86f88f Constrain MT5 live routes` was committed on `2026-04-27 19:53:17 +0900` and returned BB/MACD/SR live switches to `false`.
- `5a77ccb feat: add MT5 non-RSI live auth lock` added the second authorization key and environment tag requirement for BB_Triple, MACD_Divergence, and SR_Breakout.
- `3ce4690 feat: add MT5 startup entry guard` added the v3.17 startup delay guard so EA restarts cannot immediately open a fresh position before the configured wait conditions clear.
- Local `archive/param-lab/runs` inspection found no ParamLab run directory with a `2026-04-27 12:00-21:00` local timestamp, so ParamLab live-profile bleed is not supported by the available repo evidence.

## Root Cause Classification

- A: preset exposure window: confirmed. The BB_Triple live switch was enabled during the incident window.
- B: hard authorization did not exist yet: confirmed as a prevention gap. The later non-RSI authorization lock was added after the incident and now blocks this class even if a single route switch is accidentally enabled.
- C: ParamLab tester attached to live profile: not supported by current local archive evidence.

## Remediation

- Keep `EnablePilotBBH1Live=false`, `EnablePilotMacdH1Live=false`, and `EnablePilotSRM15Live=false` in the HFM live preset.
- Keep `EnableNonRsiLegacyLiveAuthorization=false` and `NonRsiLegacyLiveAuthorizationTag=` in the HFM live preset.
- Require both the per-route live switch and `ALLOW_NON_RSI_LEGACY_LIVE` before any future real BB/MACD/SR live test.
- Keep RSI documented separately: `RSI_Reversal` is intentionally governed by `EnablePilotRsiH1Live` and does not use the non-RSI legacy authorization lock.
- Preserve startup guard defaults: `EnablePilotStartupEntryGuard=true`, `PilotStartupEntryMinWaitMinutes=15`, and `PilotStartupEntryWaitNextH1Bar=true`.

## Follow-Up

- Add an incident override/exclusion ledger for research statistics and GovernanceAdvisor so this trade can be annotated or excluded from clean promotion evidence without altering broker history.
- If any future live-preset route switch change enables BB/MACD/SR, require a linked incident/test plan and explicit human approval before deployment.
