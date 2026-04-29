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

- `136280c Enable all legacy MT5 live pilot routes` was authored by `Boowenn` on `2026-04-27T18:12:05+09:00` and changed the HFM live preset route switches so `EnablePilotBBH1Live=true`, `EnablePilotMacdH1Live=true`, and `EnablePilotSRM15Live=true`.
- The BB_Triple `EURUSDc` order opened during that exposure window.
- `b86f88f Constrain MT5 live routes` was authored by `Boowenn` on `2026-04-27T19:53:17+09:00` and returned BB/MACD/SR live switches to `false`. The exposure window was about 101 minutes.
- `5a77ccb feat: add MT5 non-RSI live auth lock` was authored on `2026-04-29T19:38:29+09:00` and added the second authorization key plus environment tag requirement for BB_Triple, MACD_Divergence, and SR_Breakout.
- `3ce4690 feat: add MT5 startup entry guard` was authored on `2026-04-29T19:59:55+09:00` and added the v3.17 startup delay guard so EA restarts cannot immediately open a fresh position before the configured wait conditions clear.

## Investigation Commands

The push/review investigation used these commands from the repo root:

```powershell
git show 136280c -- MQL5\Presets\QuantGod_MT5_HFM_LivePilot.set |
  Select-String -Pattern 'EnablePilotBBH1Live|EnablePilotMacdH1Live|EnablePilotSRM15Live' -Context 1,1

git show b86f88f -- MQL5\Presets\QuantGod_MT5_HFM_LivePilot.set |
  Select-String -Pattern 'EnablePilotBBH1Live|EnablePilotMacdH1Live|EnablePilotSRM15Live' -Context 1,1

git show -s --format='commit=%H%nauthor=%an%nauthorDate=%aI%nsubject=%s' 136280c b86f88f 5a77ccb 3ce4690

if (Test-Path 'archive\param-lab\runs') {
  Get-ChildItem 'archive\param-lab\runs' -Directory |
    Where-Object { $_.LastWriteTime -ge [datetime]'2026-04-27T12:00:00' -and $_.LastWriteTime -le [datetime]'2026-04-27T21:00:00' }
} else {
  'archive\param-lab\runs missing'
}
```

The local repo currently has no `archive\param-lab\runs` directory. That means there is no local run-archive evidence supporting ParamLab live-profile bleed, but it does not prove such a run was impossible if external or deleted artifacts existed.

## Root Cause Classification

- What: `136280c` changed the HFM live preset from BB/MACD/SR candidate-only to BB/MACD/SR live-enabled.
- Why, inferred from commit message and surrounding work: the intent appears to have been collecting `0.01` live-forward samples for the legacy MT5 ports. There was not yet a separate signed authorization lock for non-RSI legacy routes.
- Process gap: a single preset route switch was sufficient to authorize a non-RSI route. There was no second key, exact tag, incident/test-plan requirement, or runtime lock beyond the route switch.
- Outcome: BB_Triple opened a `0.01` `EURUSDc` SELL during the exposure window and closed at `-1.35 USC`.
- Detection: the trade was identified during later CloseHistory / GovernanceAdvisor review.
- A: preset exposure window: confirmed. The BB_Triple live switch was enabled during the incident window.
- B: hard authorization did not exist yet: confirmed as a prevention gap. The later non-RSI authorization lock was added after the incident and now blocks this class even if a single route switch is accidentally enabled.
- C: ParamLab tester attached to live profile: not supported by current local archive evidence. Confidence is medium, because the local archive path is missing rather than append-only complete.

## Remediation

- Keep `EnablePilotBBH1Live=false`, `EnablePilotMacdH1Live=false`, and `EnablePilotSRM15Live=false` in the HFM live preset.
- Keep `EnableNonRsiLegacyLiveAuthorization=false` and `NonRsiLegacyLiveAuthorizationTag=` in the HFM live preset.
- Require both the per-route live switch and `ALLOW_NON_RSI_LEGACY_LIVE` before any future real BB/MACD/SR live test.
- Keep RSI documented separately: `RSI_Reversal` is intentionally governed by `EnablePilotRsiH1Live` and does not use the non-RSI legacy authorization lock.
- Preserve startup guard defaults: `EnablePilotStartupEntryGuard=true`, `PilotStartupEntryMinWaitMinutes=15`, and `PilotStartupEntryWaitNextH1Bar=true`.

## Follow-Up

- Add an incident override/exclusion ledger for research statistics and GovernanceAdvisor so this trade can be annotated or excluded from clean promotion evidence without altering broker history.
- If any future live-preset route switch change enables BB/MACD/SR, require a linked incident/test plan and explicit human approval before deployment.
- Run a deliberate MT5 Strategy Tester unauthorized-route probe: set `EnablePilotBBH1Live=true`, `EnableNonRsiLegacyLiveAuthorization=false`, and a known BB-triggering EURUSDc window; expected result is the Journal marker `pilot order blocked: non-RSI legacy live authorization lock disabled` and zero BB_Triple tester orders.
- Treat Python unit tests as static contract coverage for the `.mq5` guard shape. They do not replace the MT5 Strategy Tester runtime probe above.
