#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$REPO_ROOT"

load_env_file() {
  local env_file="$1"
  local line key value
  while IFS= read -r line || [[ -n "$line" ]]; do
    line="${line#$'\xef\xbb\xbf'}"
    line="${line#export }"
    [[ -z "$line" || "$line" == \#* || "$line" != *=* ]] && continue
    key="${line%%=*}"
    [[ -n "${!key+x}" ]] && continue
    value="${line#*=}"
    value="${value%$'\r'}"
    if [[ "$value" == \"*\" && "$value" == *\" ]]; then
      value="${value:1:${#value}-2}"
    elif [[ "$value" == \'*\' && "$value" == *\' ]]; then
      value="${value:1:${#value}-2}"
    fi
    export "$key=$value"
  done < "$env_file"
}

force_load_env_file() {
  local env_file="$1"
  local line key value
  [[ -f "$env_file" ]] || return 0
  while IFS= read -r line || [[ -n "$line" ]]; do
    line="${line#$'\xef\xbb\xbf'}"
    line="${line#export }"
    [[ -z "$line" || "$line" == \#* || "$line" != *=* ]] && continue
    key="${line%%=*}"
    value="${line#*=}"
    value="${value%$'\r'}"
    if [[ "$value" == \"*\" && "$value" == *\" ]]; then
      value="${value:1:${#value}-2}"
    elif [[ "$value" == \'*\' && "$value" == *\' ]]; then
      value="${value:1:${#value}-2}"
    fi
    export "$key=$value"
  done < "$env_file"
}

if [[ -f .env.local ]]; then
  load_env_file .env.local
fi
if [[ -f "${QG_LAUNCHD_ENV_FILE:-$HOME/.quantgod/launchd.env}" ]]; then
  load_env_file "${QG_LAUNCHD_ENV_FILE:-$HOME/.quantgod/launchd.env}"
fi

export PYTHONPATH="$REPO_ROOT${PYTHONPATH:+:$PYTHONPATH}"

is_import_snapshot_dir() {
  local candidate="$1"
  [[ "$candidate" == *"runtime/mac_import/mt5_files_snapshot"* ]]
}

is_import_dashboard_dir() {
  local candidate="$1"
  [[ "$candidate" == *"runtime/mac_import/dashboard_runtime_snapshot"* ]]
}

mac_mt5_files_dir() {
  printf '%s\n' "$HOME/Library/Application Support/net.metaquotes.wine.metatrader5/drive_c/Program Files/MetaTrader 5/MQL5/Files"
}

PYTHON_BIN="${QG_PYTHON_BIN:-python3}"
RUNTIME_DIR="${QG_RUNTIME_DIR:-${QG_MT5_FILES_DIR:-./Dashboard}}"
DASHBOARD_DIR="${QG_DASHBOARD_FILES_DIR:-./Dashboard}"
HISTORY_DIR="${QG_POLYMARKET_HISTORY_DIR:-./archive/polymarket/history}"
HISTORY_DB="${QG_POLYMARKET_HISTORY_DB:-$HISTORY_DIR/QuantGod_PolymarketHistory.sqlite}"
RUNTIME_SOURCE="${QG_MAC_RUNTIME_SOURCE:-auto}"
MAC_MT5_FILES="$(mac_mt5_files_dir)"
COPY_ONLY="${QG_POLYMARKET_COPY_ONLY:-true}"

if [[ "$(uname -s)" == "Darwin" && -d "$MAC_MT5_FILES" ]]; then
  if [[ -z "${QG_RUNTIME_DIR+x}" && -z "${QG_MT5_FILES_DIR+x}" ]]; then
    RUNTIME_DIR="$MAC_MT5_FILES"
  fi
  RUNTIME_IS_IMPORT=0
  if is_import_snapshot_dir "$RUNTIME_DIR"; then
    RUNTIME_IS_IMPORT=1
  fi
  if [[ "$RUNTIME_SOURCE" == "mt5" || ( "$RUNTIME_SOURCE" == "auto" && "$RUNTIME_IS_IMPORT" == "1" ) ]]; then
    RUNTIME_DIR="$MAC_MT5_FILES"
  fi
fi

if is_import_dashboard_dir "$DASHBOARD_DIR"; then
  DASHBOARD_DIR="./Dashboard"
fi

mkdir -p "$RUNTIME_DIR" "$DASHBOARD_DIR" "$HISTORY_DIR"

export QG_POLYMARKET_REAL_EXECUTION="${QG_POLYMARKET_REAL_EXECUTION:-false}"
export QG_POLYMARKET_CANARY_KILL_SWITCH="${QG_POLYMARKET_CANARY_KILL_SWITCH:-true}"
export QG_POLYMARKET_CLOB_HOST="${QG_POLYMARKET_CLOB_HOST:-https://clob.polymarket.com}"

echo "QuantGod Polymarket Mac read-only cycle"
echo "Runtime: $RUNTIME_DIR"
echo "Dashboard: $DASHBOARD_DIR"
echo "History DB: $HISTORY_DB"
echo "Copy-only mode: $COPY_ONLY"

prepare_isolated_clob_runtime() {
  "$PYTHON_BIN" tools/setup_polymarket_isolated_clob_runtime.py \
    --runtime-dir "$RUNTIME_DIR" \
    --dashboard-dir "$DASHBOARD_DIR" \
    --isolated-root "${QG_POLYMARKET_ISOLATED_CLOB_ROOT:-$REPO_ROOT/runtime/Polymarket_Canary_Isolated}" \
    --adapter "${QG_POLYMARKET_WALLET_ADAPTER:-isolated_clob}" \
    --clob-host "$QG_POLYMARKET_CLOB_HOST" \
    --chain-id "${QG_POLYMARKET_CHAIN_ID:-137}" \
    --max-position-usdc "${QG_POLYMARKET_REAL_WALLET_MAX_POSITION_USDC:-1}" \
    --max-daily-loss-usdc "${QG_POLYMARKET_REAL_WALLET_MAX_DAILY_LOSS_USDC:-2}" \
    --max-open-positions "${QG_POLYMARKET_REAL_WALLET_MAX_OPEN_POSITIONS:-3}"
}

prepare_isolated_clob_runtime

run_copy_discovery() {
  "$PYTHON_BIN" tools/build_polymarket_copy_trader_discovery.py \
  --runtime-dir "$RUNTIME_DIR" \
  --dashboard-dir "$DASHBOARD_DIR" \
  --leaderboard-categories "${QG_POLYMARKET_COPY_CATEGORIES:-OVERALL,POLITICS,SPORTS,CRYPTO,ECONOMICS,TECH,FINANCE}" \
  --leaderboard-periods "${QG_POLYMARKET_COPY_PERIODS:-MONTH,ALL,WEEK}" \
  --leaderboard-limit "${QG_POLYMARKET_COPY_LEADERBOARD_LIMIT:-20}" \
  --max-traders "${QG_POLYMARKET_COPY_MAX_TRADERS:-30}" \
  --positions-limit "${QG_POLYMARKET_COPY_POSITIONS_LIMIT:-30}" \
  --closed-limit "${QG_POLYMARKET_COPY_CLOSED_LIMIT:-50}" \
  --activity-limit "${QG_POLYMARKET_COPY_ACTIVITY_LIMIT:-40}" \
  --min-closed-positions "${QG_POLYMARKET_COPY_MIN_CLOSED:-8}" \
  --min-current-value "${QG_POLYMARKET_COPY_MIN_CURRENT_VALUE:-50}" \
  --min-shadow-score "${QG_POLYMARKET_COPY_MIN_SHADOW_SCORE:-60}" \
  --telegram-export "${QG_POLYMARKET_TELEGRAM_EXPORT:-}" \
  --telegram-bot-env "${QG_POLYMARKET_TELEGRAM_BOT_ENV:-$REPO_ROOT/.env.telegram.local}" \
  --telegram-bot-updates-limit "${QG_POLYMARKET_TELEGRAM_BOT_UPDATES_LIMIT:-100}" \
  --telegram-telethon-env "${QG_POLYMARKET_TELETHON_ENV:-$REPO_ROOT/.env.telegram.local}" \
  --telegram-telethon-session "${QG_POLYMARKET_TELETHON_SESSION:-}" \
  --telegram-telethon-limit "${QG_POLYMARKET_TELETHON_LIMIT:-300}" \
  --telegram-signal-limit "${QG_POLYMARKET_TELEGRAM_SIGNAL_LIMIT:-300}" \
  --telegram-channel-name "${QG_POLYMARKET_TELEGRAM_CHANNEL_NAME:-预测市场内幕钱包监控}" \
  --real-wallet-enabled "${QG_POLYMARKET_REAL_WALLET_ENABLED:-true}" \
  --real-wallet-auto-unlock "${QG_POLYMARKET_REAL_WALLET_AUTO_UNLOCK:-true}" \
  --real-wallet-require-telegram "${QG_POLYMARKET_REAL_WALLET_REQUIRE_TELEGRAM:-true}" \
  --shadow-replay-path "${QG_POLYMARKET_COPY_SHADOW_REPLAY_PATH:-}" \
  --walk-forward-path "${QG_POLYMARKET_COPY_WALK_FORWARD_PATH:-}" \
  --min-shadow-replay-trades "${QG_POLYMARKET_COPY_MIN_SHADOW_REPLAY_TRADES:-30}" \
  --min-shadow-profit-factor "${QG_POLYMARKET_COPY_MIN_SHADOW_PROFIT_FACTOR:-1.10}" \
  --min-shadow-net-pnl-usdc "${QG_POLYMARKET_COPY_MIN_SHADOW_NET_PNL_USDC:-0.01}" \
  --min-walk-forward-batches "${QG_POLYMARKET_COPY_MIN_WALK_FORWARD_BATCHES:-3}" \
  --min-walk-forward-pass-rate-pct "${QG_POLYMARKET_COPY_MIN_WALK_FORWARD_PASS_RATE_PCT:-60}" \
  --max-validation-age-hours "${QG_POLYMARKET_COPY_MAX_VALIDATION_AGE_HOURS:-168}" \
  --real-wallet-take-profit-pct "${QG_POLYMARKET_REAL_WALLET_TAKE_PROFIT_PCT:-35}" \
  --real-wallet-stop-loss-pct "${QG_POLYMARKET_REAL_WALLET_STOP_LOSS_PCT:-18}" \
  --real-wallet-trailing-stop-pct "${QG_POLYMARKET_REAL_WALLET_TRAILING_STOP_PCT:-12}" \
  --real-wallet-max-position-usdc "${QG_POLYMARKET_REAL_WALLET_MAX_POSITION_USDC:-1}" \
  --real-wallet-max-daily-loss-usdc "${QG_POLYMARKET_REAL_WALLET_MAX_DAILY_LOSS_USDC:-2}" \
  --real-wallet-max-open-positions "${QG_POLYMARKET_REAL_WALLET_MAX_OPEN_POSITIONS:-3}" \
  --real-wallet-min-entry-price "${QG_POLYMARKET_REAL_WALLET_MIN_ENTRY_PRICE:-0.04}" \
  --real-wallet-max-entry-price "${QG_POLYMARKET_REAL_WALLET_MAX_ENTRY_PRICE:-0.90}"
}

run_copy_discovery

"$PYTHON_BIN" tools/build_polymarket_copy_trader_shadow_replay.py \
  --runtime-dir "$RUNTIME_DIR" \
  --dashboard-dir "$DASHBOARD_DIR" \
  --discovery-path "$DASHBOARD_DIR/QuantGod_PolymarketCopyTraderDiscovery.json" \
  --gamma-limit "${QG_POLYMARKET_COPY_REPLAY_GAMMA_LIMIT:-500}" \
  --timeout "${QG_POLYMARKET_COPY_REPLAY_TIMEOUT:-15}" \
  --max-signals "${QG_POLYMARKET_COPY_REPLAY_MAX_SIGNALS:-300}" \
  --max-ledger-signals "${QG_POLYMARKET_COPY_REPLAY_MAX_LEDGER_SIGNALS:-600}" \
  --stake-usdc "${QG_POLYMARKET_COPY_REPLAY_STAKE_USDC:-1}" \
  --follow-slippage-cents "${QG_POLYMARKET_COPY_REPLAY_FOLLOW_SLIPPAGE_CENTS:-1}" \
  --take-profit-pct "${QG_POLYMARKET_REAL_WALLET_TAKE_PROFIT_PCT:-35}" \
  --stop-loss-pct "${QG_POLYMARKET_REAL_WALLET_STOP_LOSS_PCT:-18}" \
  --min-entry-price "${QG_POLYMARKET_REAL_WALLET_MIN_ENTRY_PRICE:-0.04}" \
  --max-entry-price "${QG_POLYMARKET_REAL_WALLET_MAX_ENTRY_PRICE:-0.90}" \
  --min-shadow-replay-trades "${QG_POLYMARKET_COPY_MIN_SHADOW_REPLAY_TRADES:-30}" \
  --min-shadow-profit-factor "${QG_POLYMARKET_COPY_MIN_SHADOW_PROFIT_FACTOR:-1.10}" \
  --min-shadow-net-pnl-usdc "${QG_POLYMARKET_COPY_MIN_SHADOW_NET_PNL_USDC:-0.01}" \
  --walk-forward-batches "${QG_POLYMARKET_COPY_MIN_WALK_FORWARD_BATCHES:-3}" \
  --min-walk-forward-pass-rate-pct "${QG_POLYMARKET_COPY_MIN_WALK_FORWARD_PASS_RATE_PCT:-60}" \
  --min-trader-bucket-samples "${QG_POLYMARKET_COPY_MIN_TRADER_BUCKET_SAMPLES:-8}" \
  --min-source-bucket-samples "${QG_POLYMARKET_COPY_MIN_SOURCE_BUCKET_SAMPLES:-30}" \
  --min-source-trader-bucket-samples "${QG_POLYMARKET_COPY_MIN_SOURCE_TRADER_BUCKET_SAMPLES:-8}"

# Rebuild discovery so the wallet policy ingests the newly generated validation ledgers.
run_copy_discovery

"$PYTHON_BIN" tools/sync_polymarket_micro_live_unlock.py \
  --runtime-dir "$RUNTIME_DIR" \
  --dashboard-dir "$DASHBOARD_DIR" \
  --repo-env "$REPO_ROOT/.env.local" \
  --launchd-env "${QG_LAUNCHD_ENV_FILE:-$HOME/.quantgod/launchd.env}" \
  --lock-file "${QG_POLYMARKET_REAL_MONEY_LOCK_FILE:-$REPO_ROOT/runtime/Polymarket_Canary_Isolated/REAL_MONEY_CANARY.lock}" \
  --min-shadow-samples "${QG_POLYMARKET_COPY_MIN_SHADOW_REPLAY_TRADES:-30}" \
  --min-walk-batches "${QG_POLYMARKET_COPY_MIN_WALK_FORWARD_BATCHES:-3}"

force_load_env_file "$REPO_ROOT/.env.local"
force_load_env_file "${QG_LAUNCHD_ENV_FILE:-$HOME/.quantgod/launchd.env}"
prepare_isolated_clob_runtime
run_copy_discovery

if [[ "$COPY_ONLY" != "true" && "$COPY_ONLY" != "1" && "$COPY_ONLY" != "yes" ]]; then
  "$PYTHON_BIN" tools/run_polymarket_radar_worker_v2.py \
    --runtime-dir "$RUNTIME_DIR" \
    --dashboard-dir "$DASHBOARD_DIR" \
    --cycles "${QG_POLYMARKET_RADAR_WORKER_CYCLES:-1}" \
    --interval-seconds 0 \
    --queue-min-score "${QG_POLYMARKET_RADAR_QUEUE_MIN_SCORE:-45}"

  "$PYTHON_BIN" tools/analyze_polymarket_single_market.py \
    --runtime-dir "$RUNTIME_DIR" \
    --dashboard-dir "$DASHBOARD_DIR"

  "$PYTHON_BIN" tools/build_polymarket_history_db.py \
    --runtime-dir "$RUNTIME_DIR" \
    --dashboard-dir "$DASHBOARD_DIR" \
    --history-dir "$HISTORY_DIR" \
    --db-path "$HISTORY_DB"
else
  echo "Skipping legacy market-radar/AI/dry-run chain; Polymarket is copy-trader discovery only."
fi

"$PYTHON_BIN" tools/build_polymarket_research_bridge.py \
  --runtime-dir "$RUNTIME_DIR" \
  --dashboard-dir "$DASHBOARD_DIR" \
  --polymarket-root "$HISTORY_DIR" \
  --db-path "$HISTORY_DB" \
  --skip-account-snapshot

"$PYTHON_BIN" tools/build_polymarket_retune_planner.py \
  --runtime-dir "$RUNTIME_DIR" \
  --dashboard-dir "$DASHBOARD_DIR" \
  --copy-discovery-path "$DASHBOARD_DIR/QuantGod_PolymarketCopyTraderDiscovery.json"

if [[ "$COPY_ONLY" != "true" && "$COPY_ONLY" != "1" && "$COPY_ONLY" != "yes" ]]; then
  "$PYTHON_BIN" tools/score_polymarket_ai_v1.py \
    --runtime-dir "$RUNTIME_DIR" \
    --dashboard-dir "$DASHBOARD_DIR" \
    --history-dir "$HISTORY_DIR" \
    --db-path "$HISTORY_DB" \
    --llm-mode "${QG_POLYMARKET_LLM_MODE:-off}"

  "$PYTHON_BIN" tools/build_polymarket_cross_market_linkage.py \
    --runtime-dir "$RUNTIME_DIR" \
    --dashboard-dir "$DASHBOARD_DIR"

  "$PYTHON_BIN" tools/build_polymarket_execution_gate.py \
    --runtime-dir "$RUNTIME_DIR" \
    --dashboard-dir "$DASHBOARD_DIR"

  "$PYTHON_BIN" tools/build_polymarket_dry_run_orders.py \
    --runtime-dir "$RUNTIME_DIR" \
    --dashboard-dir "$DASHBOARD_DIR"

  "$PYTHON_BIN" tools/watch_polymarket_dry_run_outcomes.py \
    --runtime-dir "$RUNTIME_DIR" \
    --dashboard-dir "$DASHBOARD_DIR"

  "$PYTHON_BIN" tools/build_polymarket_canary_executor_contract.py \
    --runtime-dir "$RUNTIME_DIR" \
    --dashboard-dir "$DASHBOARD_DIR"

  "$PYTHON_BIN" tools/build_polymarket_auto_governance.py \
    --runtime-dir "$RUNTIME_DIR" \
    --dashboard-dir "$DASHBOARD_DIR"
fi

echo "Completed read-only Polymarket copy-trader cycle. No real executor was started."
