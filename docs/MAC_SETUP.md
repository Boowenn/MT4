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
cp runtime/mac_import/env/quantgod.mac.env .env.local
```

Load the env before starting tools:

```bash
set -a
source .env.local
set +a
```

Important defaults for Mac:

```bash
QG_PYTHON_BIN=python3
QG_RUNTIME_DIR=./runtime/mac_import/mt5_files_snapshot
QG_MT5_FILES_DIR=./runtime/mac_import/mt5_files_snapshot
QG_POLYMARKET_HISTORY_DB=./runtime/mac_import/polymarket_history/QuantGod_PolymarketHistory.sqlite
QG_MT5_TRADING_ENABLED=false
QG_MT5_ADAPTIVE_APPLY_ENABLED=false
QG_POLYMARKET_REAL_EXECUTION=false
QG_POLYMARKET_CANARY_KILL_SWITCH=true
```

These settings keep the Mac session read-only for MT5 and no-money for Polymarket execution.

## 3. Import Runtime Snapshots

The repo intentionally does not commit generated runtime ledgers, Polymarket history snapshots, or local SQLite state.

On Windows, generate a fresh bundle before moving to Mac:

```powershell
powershell -ExecutionPolicy Bypass -File tools/export_mac_runtime_bundle.ps1
```

This creates an ignored folder such as:

```text
runtime/mac_export_YYYYMMDD-HHMMSS/
runtime/quantgod_mac_export_YYYYMMDD-HHMMSS.zip
```

The bundle includes:

- `mt5_files_snapshot/`: current copied HFM `QuantGod*` files, including `QuantGod_Dashboard.json`, `QuantGod_TradeJournal.csv`, and `QuantGod_CloseHistory.csv` when they exist.
- `dashboard_runtime_snapshot/`: Dashboard-side Polymarket and research snapshots.
- `polymarket_history/`: SQLite history files.
- `env/`: Mac env templates, with no filled secrets.

On Mac, unzip or copy the generated folder to:

```text
runtime/mac_import/
```

If you want to restore snapshots into their normal repo locations instead of reading from `runtime/mac_import`, run:

```bash
rsync -a runtime/mac_import/dashboard_runtime_snapshot/ Dashboard/
mkdir -p archive/polymarket/history
rsync -a runtime/mac_import/polymarket_history/ archive/polymarket/history/
```

This restores files such as:

- `Dashboard/QuantGod_PolymarketAiScoreV1.json`
- `Dashboard/QuantGod_PolymarketMarketRadar.json`
- `Dashboard/QuantGod_PolymarketAutoGovernance.json`
- `Dashboard/QuantGod_PolymarketRealTradeLedger.json`
- `archive/polymarket/history/QuantGod_PolymarketHistory.sqlite`

If `runtime/mac_import/manifest.json` reports missing MT5 realtime files, the Mac dashboard should treat MT5 account balance, current positions, and close history as unavailable rather than current HFM evidence. A static Mac import is a snapshot; it will not stay live unless you sync the Windows HFM Files directory continuously.

## 4. Start the Dashboard

Recommended local launcher:

```bash
./Start_QuantGod_mac.sh
```

This syncs the Vue build, local runtime snapshots, MT5 EA source/presets, and a compiled `QuantGod_MultiStrategy.ex5` into the macOS MetaTrader 5 Wine prefix when it exists. If `.env.local` points at `runtime/mac_import`, the dashboard keeps using that imported snapshot; set `QG_MAC_RUNTIME_SOURCE=mt5` only when you intentionally want to read the Wine MT5 `MQL5/Files` folder directly.

If account balance or history is missing, log in inside MetaTrader 5 and attach `QuantGod_MultiStrategy` with `QuantGod_MT5_HFM_Shadow.set`. The dashboard only shows live MT5 account/history after the EA exports `QuantGod_Dashboard.json`, `QuantGod_TradeJournal.csv`, and `QuantGod_CloseHistory.csv` into `MQL5/Files`.

Manual dashboard-only start:

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
cp runtime/mac_import/env/quantgod.secrets.env.example .env.local.secrets
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
source .env.local.secrets
set +a
python3 tools/score_polymarket_ai_v1.py --llm-mode auto
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
python3 tools/query_polymarket_history_api.py --table all --limit 5
```

Expected behavior:

- Vue build succeeds.
- Server syntax check succeeds.
- History API returns data if the SQLite snapshot was copied; otherwise it returns `MISSING_DB` safely.
