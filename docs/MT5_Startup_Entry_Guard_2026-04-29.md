# MT5 startup entry guard - 2026-04-29

## Purpose

The HFM live terminal can reload the EA while a valid H1 signal is already present. Without a startup guard, the first `ExportDashboard()` pass after reload can immediately send a new pilot order.

This patch keeps all existing position management active, but blocks new entries after EA startup until both conditions clear:

- The terminal has moved to the next H1 bar after EA reload.
- At least `PilotStartupEntryMinWaitMinutes` has elapsed.

The live preset uses:

- `EnablePilotStartupEntryGuard=true`
- `PilotStartupEntryMinWaitMinutes=15`
- `PilotStartupEntryWaitNextH1Bar=true`

Backtest presets disable this guard so tester results are not shifted by startup timing:

- `EnablePilotStartupEntryGuard=false`
- `PilotStartupEntryMinWaitMinutes=0`
- `PilotStartupEntryWaitNextH1Bar=false`

## Runtime Evidence

Dashboard/status fields:

- `pilotStartupEntryGuard`
- `pilotStartupEntryGuardActive`
- `pilotStartupEntryGuardReason`
- `pilotStartupTime`
- `pilotStartupH1BarTime`

If a live signal appears during startup protection, the EA logs:

`QuantGod MT5 pilot order blocked: startup entry guard`

and route state becomes `STARTUP_GUARD`.
