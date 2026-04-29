# MT5 RSI Exit Review - 2026-04-28

This is a same-day read-only review of HFM MT5 live and research evidence before changing the RSI exit rules.

## Live Snapshot

- Runtime: HFM live pilot, connected, execution enabled, kill switch off.
- Current open trade: `USDJPYc` `RSI_Reversal` SELL, `0.01` lot, opened `2026.04.28 16:29`, entry regime `RANGE`.
- Current open trade state during review: roughly `-1.0` to `-1.3 USC` floating loss, hard SL/TP present.
- Today closed live RSI sample: 7 closed trades, 5 wins, 2 losses, `+2.07 USC` net, 71.4% win rate, PF 1.659.

## RSI Exit Problem

The RSI route is profitable in short bursts but gives back too much when the reversal move fades. One clear closed example:

- `2026.04.27 17:00` RSI SELL reached about `+16.7 pips` MFE, then closed `-1.53 USC`.

Root cause in the previous live preset:

- Base pilot breakeven protection required `PilotBreakevenMinAgeMinutes=60`.
- Base trailing required `PilotTrailingStartPips=10` and `PilotTrailingDistancePips=5`.
- RSI H1 reversals often make their useful move before 60 minutes, then mean-reversion momentum decays.

## Implemented Branch Change

Only `QG_RSI_Rev` positions use the faster protection path:

- `EnablePilotRsiFastExitProtect=true`
- `PilotRsiProtectMinAgeMinutes=10`
- `PilotRsiBreakevenTriggerPips=5.0`
- `PilotRsiBreakevenLockPips=1.0`
- `PilotRsiTrailingStartPips=8.0`
- `PilotRsiTrailingDistancePips=3.5`
- `PilotRsiTrailingStepPips=0.5`

The MA live route keeps the original base protection:

- `PilotBreakevenMinAgeMinutes=60`
- `PilotBreakevenTriggerPips=6.0`
- `PilotTrailingStartPips=10.0`
- `PilotTrailingDistancePips=5.0`

## Follow-Up Failfast Guard

The fast-exit change protects profits, but it does not help when an RSI reversal never gets into profit. The follow-up `v3.14` guard adds an RSI-only failfast layer for `QG_RSI_Rev` positions:

- `EnablePilotRsiFailFastProtect=true`
- `PilotRsiFailFastMinAgeMinutes=120`
- `PilotRsiFailFastMinLossPips=8.0`
- `PilotRsiFailFastMaxLossUSC=1.20`
- `PilotRsiFailFastStopBufferPips=2.5`
- `PilotRsiFailFastStepPips=0.5`
- `PilotRsiFailFastCloseOnMaxLoss=false`

This first tightens the existing SL near the current price and logs `routeProtect=RSI_FAILFAST`. It does not enable a Python trading path, does not increase lot size, and does not change the MA route. Direct failfast close remains a disabled preset switch for separate review.

## Promotion / Demotion / Iteration

No strategy should be newly promoted to live today.

Keep live watch:

- `RSI_Reversal`: keep at `0.01` only with the new fast exit protection; do not increase size. The live sample is net positive, but `RANGE` and `TREND_EXP_UP` slices are weak.
- `MA_Cross`: keep constrained watch only. Backend pre-screen is still caution with negative pips and PF below target.

Stay simulation / iterate:

- `BB_Triple`: live evidence is negative and backend/sample state is caution.
- `SR_Breakout`: candidate evidence is not reliable enough; shadow sample is too small and backend is caution.
- `MACD_Divergence`: retune in simulation; backend and candidate outcomes remain weak.

Shadow-only candidates worth watching:

- `USDJPY_PULLBACK_BOUNCE`: best 60-minute candidate average in today's shadow summary, but only 5 rows. Keep shadow-only until sample grows materially.

Demotion watch:

- If RSI fast protection does not stop RANGE SELL giveback over the next few live samples, demote RSI live back to candidate-only.
- If MA_Cross adds another weak live forward loss without better shadow/backend confirmation, move it to demotion review rather than adding exposure.
