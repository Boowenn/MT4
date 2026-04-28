# MT5 Backend Backtest Loop

This document defines the QuantDinger-style backend backtest loop that was ported into QuantGod for MT5 research automation.

## Purpose

`tools/run_mt5_backend_backtest_loop.py` gives QuantGod a scalable Python-side pre-screen before expensive MT5 Strategy Tester runs. It reads tester-only candidate tasks, loads historical MT5 bars or an offline bars fixture, simulates route logic in Python, and writes reusable artifacts for Dashboard and Governance Advisor.

This loop is research-only. It does not replace the EA, Strategy Tester, or live broker execution path.

## Safety Boundary

The backend loop must stay inside these boundaries:

- no `order_send`
- no close-position calls
- no cancel-order calls
- no `symbol_select`
- no credential storage
- no live preset mutation
- no `-RunTerminal`
- no Python live trading worker

The JSON contract includes:

```json
{
  "safety": {
    "readOnly": true,
    "pythonBacktestOnly": true,
    "usesMt5StrategyTester": false,
    "orderSendAllowed": false,
    "closeAllowed": false,
    "cancelAllowed": false,
    "symbolSelectAllowed": false,
    "credentialStorageAllowed": false,
    "livePresetMutationAllowed": false,
    "mutatesMt5": false
  }
}
```

The existing MT5 EA remains the only live order owner. Its automatic entry, close, SL, TP, kill switches, and live preset rules are not changed by this backend loop.

## Inputs

Task priority:

1. `QuantGod_ParamLabAutoScheduler.json`
2. `QuantGod_OptimizerV2Plan.json`
3. built-in route defaults

Each task is normalized to:

- `candidateId`
- `routeKey`
- `strategy`
- `symbol`
- `canonicalSymbol`
- `timeframe`
- `presetOverrides`
- `testerOnly`
- `livePresetMutation`

Tasks are blocked when they are not tester-only or declare live preset mutation.

Bars source:

- MT5 read-only rates through `MetaTrader5.copy_rates_range`
- optional offline JSON/CSV fixture through `--input-bars`

The MT5 read path only reads rates. It does not select symbols or touch trade permissions.

## Outputs

Default runtime outputs:

- `QuantGod_MT5BackendBacktest.json`
- `QuantGod_MT5BackendBacktestLedger.csv`
- `QuantGod_MT5BackendBacktestTrades.csv`

Dashboard API:

- `GET /api/mt5-backtest-loop`
- `GET /api/mt5-backtest-loop/run?maxTasks=20&days=180`

Governance Advisor reads the JSON artifact and exposes:

- `mt5BackendBacktestTasks`
- `mt5BackendBacktestReady`
- `mt5BackendBacktestCaution`
- `mt5BackendBacktestTopCandidate`
- `mt5BackendBacktest`

## Strategy Coverage In V1

The Python simulator covers the five MT5 route keys:

- `MA_Cross`
- `RSI_Reversal`
- `BB_Triple`
- `MACD_Divergence`
- `SR_Breakout`

V1 is an approximation layer for high-throughput screening. MT5 Strategy Tester remains the higher-fidelity validator before promotion decisions.

## Recommended Daily Flow

1. Run the read-only watch for account, positions, orders, symbols, quote, research stats, and backend backtest artifact freshness.
2. Run the backend backtest loop on the latest tester-only queue.
3. Build MT5 research stats.
4. Build Governance Advisor.
5. Review candidates marked `BACKEND_READY`.
6. Send only qualified candidates to guarded Strategy Tester windows.

Promotion stays dry-run until the existing evidence, authorization, and live-preset review process approves it.

## Example Commands

```powershell
python tools\run_mt5_backend_backtest_loop.py `
  --runtime-dir "C:\Program Files\HFM Metatrader 5\MQL5\Files" `
  --max-tasks 20 `
  --days 180

python tools\build_governance_advisor.py `
  --runtime-dir "C:\Program Files\HFM Metatrader 5\MQL5\Files"
```

Offline fixture smoke:

```powershell
python tools\run_mt5_backend_backtest_loop.py `
  --runtime-dir .\runtime\fixture `
  --input-bars .\runtime\fixture\bars.json `
  --route SR_Breakout `
  --max-tasks 1
```
