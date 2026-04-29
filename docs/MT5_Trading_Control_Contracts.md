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

DB-backed mode is also available:

```powershell
python tools\mt5_pending_order_worker.py --runtime-dir <runtime> --db-worker --dry-run
```

This processes the local platform `pending_orders` queue through
`/api/mt5-platform/worker-run`, writes `task_runs`, mirrors broker/dry-run
fields back onto the queue, and still forces `dryRun=true`.

## Platform Store

Backed by `tools/mt5_platform_store.py`.

Endpoints:

- `GET /api/mt5-platform/status`
- `POST /api/mt5-platform/operator`
- `GET /api/mt5-platform/credentials`
- `POST /api/mt5-platform/credential`
- `POST /api/mt5-platform/connect`
- `POST /api/mt5-platform/disconnect`
- `GET /api/mt5-platform/strategies`
- `POST /api/mt5-platform/strategy`
- `GET /api/mt5-platform/queue`
- `POST /api/mt5-platform/enqueue`
- `POST /api/mt5-platform/quick-trade`
- `POST /api/mt5-platform/dispatch`
- `POST /api/mt5-platform/worker-run`
- `POST /api/mt5-platform/queue-retry`
- `POST /api/mt5-platform/queue-cancel`
- `POST /api/mt5-platform/queue-archive`
- `GET /api/mt5-platform/ledger`
- `GET /api/mt5-platform/quick-trades`
- `GET /api/mt5-platform/task-runs`
- `GET /api/mt5-platform/positions`
- `GET /api/mt5-platform/trades`
- `POST /api/mt5-platform/reconcile`
- `POST /api/mt5-platform/symbols`

Artifacts:

- `QuantGod_MT5Platform.db`
- `QuantGod_MT5PlatformState.json`

The local SQLite store tracks:

- `operators`
- `role_permissions`
- `product_features`
- `task_runs`
- `audit_events`
- `qd_exchange_credentials`
- `qd_strategies_trading`
- `pending_orders`
- `qd_quick_trades`
- `qd_strategy_positions`
- `qd_strategy_trades`
- `qd_market_symbols`
- `mt5_connection_sessions`

It synchronizes `QuantGod_MT5TradingAuditLedger.csv` and
`QuantGod_MT5PendingOrderLedger.csv` into queryable audit events. It also
mirrors dry-run/order ledger events into `qd_strategy_trades`, accepts
read-only snapshot reconcile into `qd_strategy_positions`, and materializes
symbol-registry mappings into `qd_market_symbols`.

The current store mode is `MT5_PLATFORM_STORE_V3`. It extends the QuantDinger
style local platform layer with:

- static MT5 symbol catalog seeding, including normalized market type and
  lot-size metadata
- DB pending-order worker task runs
- exchange-order mirror fields on `pending_orders`:
  `dispatch_note`, `exchange_order_id`, `exchange_response_json`, `filled`,
  `avg_price`, `executed_at`, and `owner_mode`
- lifecycle fields on `qd_strategy_positions`:
  `highest_price`, `lowest_price`, `pnl_percent`, and `equity`
- richer `qd_strategy_trades` commission fields
- `qd_quick_trades` for Dashboard quick-ticket intents

Safety contract:

- raw MT5 passwords are rejected/redacted and never persisted
- live execution modes posted through the platform store are downgraded to
  `dry_run`
- `pending_orders.dry_run_required=1` for queued Dashboard/quick-ticket intents
- `/api/mt5-platform/dispatch` calls the guarded trading bridge with
  `dryRun=true` and records the result; it does not send broker orders
- `/api/mt5-platform/worker-run` processes the SQLite queue in the same
  dry-run-only way and records a `task_runs` row
- queue retry/cancel/archive changes local SQLite state only
- connect/disconnect records a local control-plane session event; it does not
  bypass `/api/mt5/login` authorization
- `orderSendAllowed=false`, `dispatchLiveAllowed=false`,
  `rawPasswordStorageAllowed=false`, and `mutatesMt5=false` must remain true in
  every platform-store response

## Live-Trading Factory

Backed by `tools/live_trading_factory.py`.

The factory exposes a QuantDinger-style abstraction:

```python
from live_trading_factory import create_client

client = create_client("MT5", market_category="Forex")
client = create_client({"exchange_id": "mt5", "market_category": "Forex"})
client.place_limit_order({...})
client.enqueue_order({...})
client.quick_trade({...})
client.close_position({...})
client.cancel_order({...})
client.get_account_info()
client.get_positions()
client.get_orders()
client.get_symbols()
client.get_quote("EURUSDc")
```

The MT5 client is a wrapper around the guarded trading bridge. It does not
change any safety requirement: default calls are dry-run/audited, and live
mutation still requires config, env, authorization lock, limits, and audit.
`enqueue_order` and `quick_trade` write to the local platform
`pending_orders` queue with `dry_run_required=1`; they do not call
`order_send`.
The read methods proxy the read-only bridge, giving QuantDinger-style client
shape without moving credentials or live authority into Python by default.

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
- DB pending worker drains the SQLite `pending_orders` queue in dry-run mode
  and records task runs
- platform store syncs audit events into SQLite
- platform store credential/strategy/queue contracts keep raw passwords out and
  force dry-run dispatch
- platform reconcile and symbol catalog contracts pool broker suffixes under
  canonical symbols
- static MT5 symbol catalog rows carry market/lot metadata
- live-trading factory accepts QuantDinger-style MT5 exchange config dicts and
  exposes read-only account/position/order/symbol/quote methods
- live-trading factory keeps MT5 actions behind the guarded bridge
- adaptive-control executor stages actions without live preset mutation by
  default

Run:

```powershell
python -m unittest discover -s tests -p "test_mt5_*.py" -v
```
