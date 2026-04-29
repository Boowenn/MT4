# MT5 Trading Control Contracts

This document describes the guarded MT5 trading surfaces added after the
read-only bridge. They are implemented, but locked by default. Live mutation
requires explicit operator configuration and is still separated from the EA
live preset.

## Default State

Default behavior is safe:

- `tradingEnabled=false`
- `dryRun=true`
- `killSwitch=true`
- `ownerMode=EA_ONLY`
- `orderSendAllowed=false`
- `closeAllowed=false`
- `cancelAllowed=false`
- `credentialStorageAllowed=false`
- `livePresetMutationAllowed=false`

The Dashboard can call the endpoints, but with the default config every trading
request becomes a dry-run or blocked audit event.

## Trading Bridge

Backed by `tools/mt5_trading_client.py`.

Supported endpoints:

- `GET /api/mt5/status`
- `GET /api/mt5/profiles`
- `POST /api/mt5/profile`
- `POST /api/mt5/login`
- `POST /api/mt5/order`
- `POST /api/mt5/close`
- `POST /api/mt5/cancel`
- `DELETE /api/mt5/order/<ticket>`

Aliases under `/api/mt5-trading/*` are also supported.

### Order Request

```json
{
  "route": "MA_Cross",
  "symbol": "EURUSDc",
  "side": "buy",
  "orderType": "buy_limit",
  "lots": 0.01,
  "price": 1.099,
  "sl": 1.094,
  "tp": 1.109,
  "expirationTimeIso": "2026-04-30T00:00:00Z",
  "dryRun": true
}
```

### Close Request

```json
{
  "ticket": 17749329175,
  "lots": 0.01,
  "dryRun": true
}
```

### Cancel Request

```json
{
  "ticket": 17749329175,
  "dryRun": true
}
```

### Profile Request

Profiles store account metadata only. Passwords are never persisted.

```json
{
  "profileId": "hfm-live",
  "accountLogin": 186054398,
  "server": "HFMarketsGlobal-Live12",
  "terminalPath": "C:\\Program Files\\HFM Metatrader 5\\terminal64.exe",
  "passwordEnvVar": "QG_MT5_HFM_PASSWORD"
}
```

## Live Mutation Gate

For `order`, `close`, `cancel`, or `login` to mutate MT5, all checks must pass:

- `QG_MT5_TRADING_ENABLED=true` unless config disables env gating.
- `QuantGod_MT5TradingConfig.json` has `tradingEnabled=true`.
- `dryRun=false`.
- `killSwitch=false`.
- `ownerMode` is one of `DASHBOARD_TICKET_OPS`, `PY_PENDING_ONLY`, or
  `EA_AND_PY_SPLIT`.
- The matching operation flag is enabled:
  `allowDashboardMarketOrders`, `allowDashboardPendingOrders`,
  `allowDashboardClose`, `allowDashboardCancel`, or `allowLogin`.
- The authorization lock exists, is not expired, matches account/server/action,
  matches route/symbol scope, and passes signature validation.
- Worker risk limits pass: max lots, per-symbol lots, portfolio lots, daily
  count, route-symbol daily count.
- An audit row is written before the broker call.

Any failed check forces `DRY_RUN_ACCEPTED` or `BLOCKED`.

## Authorization Lock

Default lock path:

`C:\ProgramData\QuantGod\mt5_trading_auth_lock.json`

Suggested fields:

```json
{
  "lockId": "operator-approved-window-001",
  "expiresAtIso": "2026-04-30T00:00:00Z",
  "accountLogin": 186054398,
  "server": "HFMarketsGlobal-Live12",
  "mode": "DASHBOARD_TICKET_OPS",
  "allowedActions": ["order", "close", "cancel"],
  "allowedRoutes": ["MA_Cross"],
  "allowedCanonicalSymbols": ["EURUSD"],
  "maxOrdersPerDay": 2,
  "maxLotsPerOrder": 0.01,
  "operator": "human-review",
  "reason": "approved limited dry-run-to-live window",
  "signature": "<sha256>"
}
```

When `signatureRequired=true`, the signature is:

`sha256(lockId|accountLogin|server|expiresAtIso|mode|$QG_MT5_AUTH_SECRET)`

## Audit Ledger

Trading bridge ledger:

`QuantGod_MT5TradingAuditLedger.csv`

Important columns:

- `LedgerId`
- `EventTimeIso`
- `Endpoint`
- `Action`
- `DryRun`
- `LiveAllowed`
- `Decision`
- `Reason`
- `AccountLogin`
- `Server`
- `Route`
- `CanonicalSymbol`
- `BrokerSymbol`
- `OrderType`
- `Side`
- `Lots`
- `Ticket`
- `AuthLockId`
- `KillSwitchSnapshotJson`
- `RequestJson`
- `BrokerRetCode`
- `BrokerOrderTicket`
- `BrokerComment`

## Pending-Order Worker

Backed by `tools/mt5_pending_order_worker.py`.

Endpoints:

- `GET /api/mt5-pending-worker/status`
- `POST /api/mt5-pending-worker/run`

Input artifact:

`QuantGod_MT5PendingOrderIntents.json`

Output artifacts:

- `QuantGod_MT5PendingOrderWorker.json`
- `QuantGod_MT5PendingOrderLedger.csv`

The worker only supports pending order types:

- `buy_limit`
- `sell_limit`
- `buy_stop`
- `sell_stop`
- `buy_stop_limit`
- `sell_stop_limit`

It derives a stable `IntentId`, skips duplicate accepted intents, calls the
guarded trading bridge, and mirrors decisions into the worker ledger.

## Platform Store

Backed by `tools/mt5_platform_store.py`.

Endpoints:

- `GET /api/mt5-platform/status`
- `POST /api/mt5-platform/operator`

Artifacts:

- `QuantGod_MT5Platform.db`
- `QuantGod_MT5PlatformState.json`

The local SQLite store tracks:

- `operators`
- `role_permissions`
- `product_features`
- `task_runs`
- `audit_events`

It synchronizes `QuantGod_MT5TradingAuditLedger.csv` and
`QuantGod_MT5PendingOrderLedger.csv` into queryable audit events. It never sends
orders or mutates MT5.

## Live-Trading Factory

Backed by `tools/live_trading_factory.py`.

The factory exposes a QuantDinger-style abstraction:

```python
from live_trading_factory import create_client

client = create_client("MT5", market_category="Forex")
client.place_limit_order({...})
client.close_position({...})
client.cancel_order({...})
```

The MT5 client is a wrapper around the guarded trading bridge. It does not
change any safety requirement: default calls are dry-run/audited, and live
mutation still requires config, env, authorization lock, limits, and audit.

## Adaptive-Control Executor

Backed by `tools/mt5_adaptive_control_executor.py`.

Endpoints:

- `GET /api/mt5-adaptive-control/status`
- `POST /api/mt5-adaptive-control/run`

Artifacts:

- `QuantGod_MT5AdaptiveControlActions.json`
- `QuantGod_MT5AdaptiveControlLedger.csv`
- `QuantGod_MT5AdaptiveControlStaging.set`

The executor turns Governance Advisor / Version Promotion Gate route decisions
into durable actions such as `STAGE_ENABLE_ROUTE`, `STAGE_DISABLE_ROUTE`, and
`STAGE_RETUNE_ROUTE`. By default it only writes an audited staging artifact.
Live preset mutation is blocked unless all of these are true:

- `dryRun=false`
- `killSwitch=false`
- `QG_MT5_ADAPTIVE_APPLY_ENABLED=true`
- `allowLivePresetMutation=true`
- authorization lock validates

It never sends broker orders.

## Tests

Contract tests cover:

- default trading requests are dry-run and audited
- fake MT5 `order_send` only runs after config + lock + limits pass
- profiles never persist passwords
- pending worker writes dry-run ledger and skips duplicates
- platform store syncs audit events into SQLite
- live-trading factory keeps MT5 actions behind the guarded bridge
- adaptive-control executor stages actions without live preset mutation by
  default

Run:

```powershell
python -m unittest discover -s tests -p "test_mt5_*.py" -v
```
