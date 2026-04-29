# MT5 Read-Only API Contracts

This document defines the stable local Dashboard API contracts for the MT5
read-only bridge and symbol registry. These APIs are observation surfaces only.
They must never send orders, close positions, cancel orders, select symbols,
store credentials, mutate presets, or change EA live-trading permissions.
Guarded trading operations, account profiles, the pending-order worker, and the
local platform store are separate and documented in
`docs/MT5_Trading_Control_Contracts.md`; they must not be added to the
`/api/mt5-readonly/*` namespace.

## Hard Safety Contract

Every successful or unavailable response must include a `safety` object with:

```json
{
  "readOnly": true,
  "orderSendAllowed": false,
  "closeAllowed": false,
  "cancelAllowed": false,
  "credentialStorageAllowed": false,
  "livePresetMutationAllowed": false,
  "mutatesMt5": false
}
```

`/api/mt5-symbol-registry` also includes:

```json
{
  "symbolSelectAllowed": false
}
```

Unsupported mutating endpoint names such as `/api/mt5-readonly/order`,
`/api/mt5-readonly/close`, `/api/mt5-readonly/cancel`,
`/api/mt5-symbol-registry/order`, and any equivalent mutation route must return
`404` with `ok=false`.

## `/api/mt5-readonly/*`

Backed by `tools/mt5_readonly_bridge.py`.

Supported endpoints:

- `GET /api/mt5-readonly`
- `GET /api/mt5-readonly/status`
- `GET /api/mt5-readonly/account`
- `GET /api/mt5-readonly/positions?symbol=EURUSDc`
- `GET /api/mt5-readonly/orders?symbol=EURUSDc`
- `GET /api/mt5-readonly/symbols?group=*&q=usd&limit=120`
- `GET /api/mt5-readonly/quote?symbol=EURUSDc`
- `GET /api/mt5-readonly/snapshot?symbol=EURUSDc&symbolsLimit=120`

Common response fields:

- `ok`: boolean
- `mode`: `MT5_READONLY_BRIDGE_V1`
- `endpoint`: requested endpoint
- `generatedAtIso`: UTC ISO timestamp
- `safety`: hard safety object
- `terminal`: terminal status and paths when MT5 initializes
- `account`: account identity and read-only balance/equity fields when available
- `lastError`: MT5 `last_error()` value when available
- `_api`: Node dashboard API metadata when served through `dashboard_server.js`

Endpoint-specific fields:

- `positions`: `{ count, symbol, items[] }`
- `orders`: `{ count, symbol, items[] }`
- `symbols`: `{ group, query, count, returned, truncated, items[] }`
- `quote`: `{ ok, symbol, bid, ask, last, volume, spreadPoints, timeIso }`

Position item fields:

- `ticket`
- `identifier`
- `symbol`
- `type`
- `volume`
- `priceOpen`
- `priceCurrent`
- `sl`
- `tp`
- `profit`
- `swap`
- `magic`
- `comment`
- `time`
- `timeIso`

Order item fields:

- `ticket`
- `symbol`
- `type`
- `volumeInitial`
- `volumeCurrent`
- `priceOpen`
- `priceCurrent`
- `sl`
- `tp`
- `magic`
- `comment`
- `timeSetup`
- `timeSetupIso`

Symbol item fields:

- `name`
- `description`
- `path`
- `visible`
- `selected`
- `currencyBase`
- `currencyProfit`
- `digits`
- `point`
- `spread`
- `tradeMode`
- `volumeMin`
- `volumeMax`
- `volumeStep`

## `/api/mt5-symbol-registry/*`

Backed by `tools/mt5_symbol_registry.py`.

Supported endpoints:

- `GET /api/mt5-symbol-registry?group=*&q=usd&limit=2000`
- `GET /api/mt5-symbol-registry/resolve?symbol=EURUSD`

Common response fields:

- `ok`: boolean
- `mode`: `MT5_SYMBOL_REGISTRY_V1`
- `endpoint`: `registry` or `resolve`
- `source`: `live_mt5` or `input_json`
- `group`
- `query`
- `generatedAtIso`
- `safety`
- `summary`
- `mappings`
- `terminal`, `account`, `status`, `lastError` when sourced from live MT5
- `_api` when served through `dashboard_server.js`

Summary fields:

- `totalSymbols`
- `mappedSymbols`
- `visibleSymbols`
- `selectedSymbols`
- `staticCatalogSymbols`
- `assetClassCounts`
- `brokerSuffixCounts`
- `canonicalConflicts`
- `canonicalConflictCount`

Mapping item fields:

- `canonicalSymbol`
- `brokerSymbol`
- `brokerSuffix`
- `assetClass`
- `marketCategory`
- `marketType`
- `baseCurrency`
- `quoteCurrency`
- `description`
- `path`
- `visible`
- `selected`
- `digits`
- `point`
- `spread`
- `tradeMode`
- `volumeMin`
- `volumeMax`
- `volumeStep`
- `lotSize`
- `standardLot`
- `minLot`
- `lotStep`
- `maxLot`
- `contractUnit`
- `mappingReason`
- `confidence`
- `aliases`

The registry also exposes a static QuantDinger-compatible MT5 symbol catalog
for common forex pairs, metals, indices, and crypto CFDs. Live HFM symbols are
preferred when present; static rows fill discovery gaps and carry normalized
lot-size metadata so Dashboard, research stats, and the platform store do not
split samples by broker suffix.

Resolve response additions:

- `querySymbol`
- `resolved`
- `matches`
- `matchCount`

## Contract Tests

The contract is enforced by:

- `tests/test_mt5_readonly_bridge.py`
- `tests/test_mt5_symbol_registry.py`

These tests use fake MT5 payloads and must remain fast and terminal-independent.
Live MT5 smoke tests can be run separately, but they are not a replacement for
the fake contract tests because live account state changes over time.
