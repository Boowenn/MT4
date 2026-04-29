# QuantGod Mac Setup

This guide is for running the QuantGod Vue dashboard and Polymarket research layer on macOS.

The MT5 live pilot and Strategy Tester remain Windows-hosted unless the Mac has a working MT5 runtime through Windows, Wine, a VM, or remote path access. Keep MT5 trading disabled on Mac by default.

## 1. Clone and Install

```bash
git clone https://github.com/Boowenn/QuantGod.git
cd QuantGod
cd frontend
npm ci
npm run build
cd ..
```

## 2. Import Environment

Use the committed template for a clean setup:

```bash
cp .env.example .env.local
```

If you copied the local migration bundle from Windows, use:

```bash
cp runtime/mac_migration_env/quantgod.mac.env .env.local
```

Load the env before starting tools:

```bash
set -a
source .env.local
set +a
```

Important defaults for Mac:

```bash
QG_RUNTIME_DIR=./Dashboard
QG_MT5_FILES_DIR=./Dashboard
QG_MT5_TRADING_ENABLED=false
QG_MT5_ADAPTIVE_APPLY_ENABLED=false
QG_POLYMARKET_REAL_EXECUTION=false
QG_POLYMARKET_CANARY_KILL_SWITCH=true
```

These settings keep the Mac session read-only for MT5 and no-money for Polymarket execution.

## 3. Import Runtime Snapshots

The repo intentionally does not commit generated runtime ledgers, Polymarket history snapshots, or local SQLite state.

If you copied the Windows bundle, restore it from the repo root:

```bash
rsync -a runtime/mac_migration_env/Dashboard_runtime_snapshot/ Dashboard/
mkdir -p archive/polymarket/history
rsync -a runtime/mac_migration_env/polymarket_history/ archive/polymarket/history/
```

This restores files such as:

- `Dashboard/QuantGod_PolymarketAiScoreV1.json`
- `Dashboard/QuantGod_PolymarketMarketRadar.json`
- `Dashboard/QuantGod_PolymarketAutoGovernance.json`
- `Dashboard/QuantGod_PolymarketRealTradeLedger.json`
- `archive/polymarket/history/QuantGod_PolymarketHistory.sqlite`

## 4. Start the Dashboard

```bash
node Dashboard/dashboard_server.js
```

Open:

```text
http://localhost:8080/vue/
```

The old `QuantGod_Dashboard.html` route is retired and redirects to `/vue/`.

## 5. Optional Polymarket AI Scoring

Create a private secrets file if you want LLM-backed scoring:

```bash
cp runtime/mac_migration_env/quantgod.secrets.env.example runtime/mac_migration_env/quantgod.secrets.env
```

Fill one of:

```bash
QG_POLYMARKET_OPENAI_API_KEY=...
OPENAI_API_KEY=...
```

Then run:

```bash
set -a
source .env.local
source runtime/mac_migration_env/quantgod.secrets.env
set +a
python tools/score_polymarket_ai_v1.py --llm-mode auto
```

Do not put wallet/private-key values in this file unless you are intentionally preparing a real canary executor session.

## 6. What Not To Migrate Blindly

Do not copy these Codex profile/runtime secrets from Windows to Mac:

- `auth.json`
- `.sandbox-secrets/`
- `cap_sid`
- `installation_id`

Re-authenticate Codex on the Mac instead.

Do not enable these without a separate review:

```bash
QG_MT5_TRADING_ENABLED=true
QG_MT5_ADAPTIVE_APPLY_ENABLED=true
QG_POLYMARKET_REAL_EXECUTION=true
QG_POLYMARKET_CANARY_KILL_SWITCH=false
```

## 7. Quick Health Check

```bash
npm --prefix frontend run build
node --check Dashboard/dashboard_server.js
python tools/query_polymarket_history_api.py --table all --limit 5
```

Expected behavior:

- Vue build succeeds.
- Server syntax check succeeds.
- History API returns data if the SQLite snapshot was copied; otherwise it returns `MISSING_DB` safely.
