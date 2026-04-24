# QuantGod HFM MT5 Backtest Archive

This folder keeps local HFM MT5 Strategy Tester outputs for the constrained live-pilot research loop.

V1 scope:

- Strategy: `MA_Cross`
- Symbols: `EURUSDc`, `USDJPYc`
- Execution lot: `0.01`
- Signal/trend frame: `M15` trigger with `H1` trend filter
- No `0.10`, no extra symbols, no extra strategies

Use:

```powershell
powershell -ExecutionPolicy Bypass -File .\tools\run_mt5_backtest_lab.ps1
```

By default the script prepares tester configs and writes a dashboard summary without interrupting the live HFM terminal. Add `-RunTerminal` only when you intentionally want to run MT5 Strategy Tester from the HFM client.

Generated run folders and latest summary files are local runtime artifacts and are ignored by Git.
