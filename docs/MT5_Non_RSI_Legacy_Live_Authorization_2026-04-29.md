# MT5 non-RSI legacy live authorization lock - 2026-04-29

## Purpose

The April 27 BB_Triple live order showed that a preset-level live switch can be enough to open a non-RSI legacy route if the preset is accidentally promoted.

This patch adds a second authorization key for BB_Triple, MACD_Divergence, and SR_Breakout. A non-RSI legacy route now needs both:

- Its route live switch, for example `EnablePilotBBH1Live=true`.
- `EnableNonRsiLegacyLiveAuthorization=true` with the correct environment tag.

`RSI_Reversal` is intentionally outside this non-RSI lock. It is still gated by the global pilot-live checks, its own `EnablePilotRsiH1Live` switch, and the RSI-specific risk guards, but disabling `EnableNonRsiLegacyLiveAuthorization` does not pause RSI.

## Tags

- MT5 Strategy Tester only: `ALLOW_NON_RSI_LEGACY_TESTER`
- Real live terminal only: `ALLOW_NON_RSI_LEGACY_LIVE`

The tester tag does not authorize a real HFM live terminal. The live tag is not present in the HFM live preset.

## Live Preset State

`QuantGod_MT5_HFM_LivePilot.set` remains USDJPY RSI focused:

- `Watchlist=USDJPY`
- `EnablePilotMA=false`
- `EnablePilotRsiH1Live=true`
- `EnablePilotBBH1Live=false`
- `EnablePilotMacdH1Live=false`
- `EnablePilotSRM15Live=false`
- `EnableNonRsiLegacyLiveAuthorization=false`
- `NonRsiLegacyLiveAuthorizationTag=`

## Evidence To Watch

After deployment, these fields should appear in the dashboard/status files:

- `build=QuantGod-v3.17-mt5-startup-entry-guard` or newer
- `nonRsiLegacyLiveAuthorization=false`
- `nonRsiLegacyLiveAuthorizationState=DISABLED`

If a BB/MACD/SR order path is reached without the second key, the Journal should log:

`QuantGod MT5 pilot order blocked: non-RSI legacy live authorization lock disabled`
