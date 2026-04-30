#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$REPO_ROOT"

load_env_file() {
  local env_file="$1"
  local line
  while IFS= read -r line || [[ -n "$line" ]]; do
    line="${line#$'\xef\xbb\xbf'}"
    line="${line#export }"
    [[ -z "$line" || "$line" == \#* || "$line" != *=* ]] && continue
    local key="${line%%=*}"
    [[ -n "${!key+x}" ]] && continue
    export "$line"
  done < "$env_file"
}

if [[ -f .env.local ]]; then
  load_env_file .env.local
fi

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

if [[ "$(uname -s)" == "Darwin" && -d "$MAC_MT5_FILES" ]]; then
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

export QG_POLYMARKET_REAL_EXECUTION=false
export QG_POLYMARKET_CANARY_KILL_SWITCH=true

echo "QuantGod Polymarket Mac read-only cycle"
echo "Runtime: $RUNTIME_DIR"
echo "Dashboard: $DASHBOARD_DIR"
echo "History DB: $HISTORY_DB"

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

echo "Completed read-only Polymarket cycle. No real executor was started."
