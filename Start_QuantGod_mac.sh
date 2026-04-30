#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

load_env_file() {
  local env_file="$1"
  local line
  while IFS= read -r line || [[ -n "$line" ]]; do
    line="${line#$'\xef\xbb\xbf'}"
    line="${line#export }"
    [[ -z "$line" || "$line" == \#* || "$line" != *=* ]] && continue
    export "$line"
  done < "$env_file"
}

is_import_snapshot_dir() {
  local candidate="$1"
  [[ "$candidate" == *"runtime/mac_import/mt5_files_snapshot"* ]]
}

patch_ini_key() {
  local file="$1"
  local key="$2"
  local value="$3"
  if grep -q "^${key}=" "$file"; then
    perl -0pi -e "s/^\\Q${key}\\E=.*/${key}=${value}/mg" "$file"
  else
    printf '%s=%s\n' "$key" "$value" >> "$file"
  fi
}

if [[ -f .env.local ]]; then
  load_env_file .env.local
fi

RUNTIME_CONFIGURED=0
if [[ -n "${QG_RUNTIME_DIR:-}" || -n "${QG_MT5_FILES_DIR:-}" ]]; then
  RUNTIME_CONFIGURED=1
fi

export QG_DASHBOARD_HOST="${QG_DASHBOARD_HOST:-127.0.0.1}"
export QG_DASHBOARD_PORT="${QG_DASHBOARD_PORT:-8080}"
export QG_PYTHON_BIN="${QG_PYTHON_BIN:-python3}"
export QG_RUNTIME_DIR="${QG_RUNTIME_DIR:-./Dashboard}"
export QG_MT5_FILES_DIR="${QG_MT5_FILES_DIR:-./Dashboard}"

MT5_APP_PATH="${QG_MT5_APP_PATH:-$HOME/Applications/MetaTrader 5.app}"
MT5_PREFIX="${QG_MT5_WINE_PREFIX:-$HOME/Library/Application Support/net.metaquotes.wine.metatrader5}"
MT5_ROOT="${QG_MT5_ROOT:-$MT5_PREFIX/drive_c/Program Files/MetaTrader 5}"
MT5_MQL5="$MT5_ROOT/MQL5"
MT5_FILES="$MT5_MQL5/Files"
MT5_EXPERTS="$MT5_MQL5/Experts"
MT5_PRESETS="$MT5_MQL5/Presets"
WINE64="$MT5_APP_PATH/Contents/SharedSupport/wine/bin/wine64"
MT5_SHADOW_CONFIG="$MT5_PREFIX/drive_c/qg/QuantGod_MT5_HFM_Shadow_mac.ini"
MT5_LIVE_CONFIG="$MT5_PREFIX/drive_c/qg/QuantGod_MT5_HFM_LivePilot_mac.ini"
export QG_PARAMLAB_HFM_ROOT="${QG_PARAMLAB_HFM_ROOT:-$SCRIPT_DIR/runtime/ParamLab_Tester_Sandbox/live_hfm_placeholder}"
export QG_PARAMLAB_TESTER_ROOT="${QG_PARAMLAB_TESTER_ROOT:-$SCRIPT_DIR/runtime/HFM_MT5_Tester_Isolated}"
export QG_MT5_TESTER_ROOT="${QG_MT5_TESTER_ROOT:-$QG_PARAMLAB_TESTER_ROOT}"
MT5_SHADOW_SCREEN="${QG_MT5_SHADOW_SCREEN:-quantgod-mt5-shadow}"
RUNTIME_SOURCE="${QG_MAC_RUNTIME_SOURCE:-auto}"
MT5_START_MODE="${QG_MT5_START_MODE:-shadow}"
MT5_START_SYMBOL="${QG_MT5_START_SYMBOL:-USDJPYc}"
RUNTIME_IS_IMPORT_SNAPSHOT=0
if is_import_snapshot_dir "$QG_RUNTIME_DIR"; then
  RUNTIME_IS_IMPORT_SNAPSHOT=1
fi

if [[ -d "$MT5_ROOT" && ( "$RUNTIME_SOURCE" == "mt5" || ( "$RUNTIME_SOURCE" == "auto" && ( "$RUNTIME_CONFIGURED" == "0" || "$RUNTIME_IS_IMPORT_SNAPSHOT" == "1" ) ) ) ]]; then
  export QG_RUNTIME_DIR="$MT5_FILES"
  export QG_MT5_FILES_DIR="$MT5_FILES"
fi

echo "QuantGod Mac launcher"
echo "Repo: $SCRIPT_DIR"
echo "Runtime: $QG_RUNTIME_DIR"
echo "MT5 start mode: $MT5_START_MODE"
echo "MT5 start symbol: $MT5_START_SYMBOL"
echo "Dashboard: http://$QG_DASHBOARD_HOST:$QG_DASHBOARD_PORT/vue/"

if [[ -d "$MT5_ROOT" ]]; then
  echo "Syncing QuantGod files into MT5..."
  mkdir -p "$MT5_FILES" "$MT5_EXPERTS" "$MT5_PRESETS" "$MT5_PREFIX/drive_c/qg"
  rsync -a Dashboard/vue-dist/ "$MT5_FILES/vue-dist/"
  cp Dashboard/dashboard_server.js "$MT5_FILES/dashboard_server.js"
  rsync -a --include='QuantGod_*' --include='*/' --exclude='*' Dashboard/ "$MT5_FILES/"
  if [[ -d "$QG_MT5_FILES_DIR" ]]; then
    SRC_MT5_FILES="$(cd "$QG_MT5_FILES_DIR" && pwd -P)"
    DST_MT5_FILES="$(cd "$MT5_FILES" && pwd -P)"
    if [[ "$SRC_MT5_FILES" != "$DST_MT5_FILES" ]]; then
      rsync -a --include='QuantGod_*' --include='*/' --exclude='*' "$QG_MT5_FILES_DIR/" "$MT5_FILES/"
    fi
  fi
  cp MQL5/Experts/QuantGod_MultiStrategy.mq5 "$MT5_EXPERTS/QuantGod_MultiStrategy.mq5"
  rsync -a MQL5/Presets/ "$MT5_PRESETS/"
  cp MQL5/Config/QuantGod_MT5_HFM_Shadow.ini "$MT5_SHADOW_CONFIG"
  patch_ini_key "$MT5_SHADOW_CONFIG" "Symbol" "$MT5_START_SYMBOL"
  perl -0pi -e 's/AllowLiveTrading=1/AllowLiveTrading=0/g' "$MT5_SHADOW_CONFIG"

  if [[ -x "$WINE64" ]]; then
    echo "Compiling QuantGod_MultiStrategy.mq5 with MetaEditor..."
    cp MQL5/Experts/QuantGod_MultiStrategy.mq5 "$MT5_PREFIX/drive_c/qg/QuantGod_MultiStrategy.mq5"
    set +e
    WINEPREFIX="$MT5_PREFIX" "$WINE64" \
      'C:\Program Files\MetaTrader 5\metaeditor64.exe' \
      '/compile:C:\qg\QuantGod_MultiStrategy.mq5' \
      '/log:C:\qg\compile.log'
    COMPILE_CODE=$?
    set -e
    if [[ -f "$MT5_PREFIX/drive_c/qg/QuantGod_MultiStrategy.ex5" ]]; then
      cp "$MT5_PREFIX/drive_c/qg/QuantGod_MultiStrategy.ex5" "$MT5_EXPERTS/QuantGod_MultiStrategy.ex5"
      cp "$MT5_PREFIX/drive_c/qg/QuantGod_MultiStrategy.ex5" MQL5/Experts/QuantGod_MultiStrategy.ex5
      echo "EA compiled and synced to MT5 Experts."
    else
      echo "MetaEditor did not produce QuantGod_MultiStrategy.ex5. Exit code: $COMPILE_CODE"
      echo "Check: $MT5_PREFIX/drive_c/qg/compile.log"
    fi

    if [[ "${QG_PREPARE_ISOLATED_TESTER:-1}" != "0" ]]; then
      echo "Preparing isolated Strategy Tester root..."
      "$QG_PYTHON_BIN" tools/prepare_isolated_mt5_tester.py \
        --source-root "$MT5_ROOT" \
        --tester-root "$QG_PARAMLAB_TESTER_ROOT" \
        --status "$SCRIPT_DIR/runtime/QuantGod_IsolatedTesterStatus.json" \
        --refresh || echo "Isolated tester preparation failed; AUTO_TESTER_WINDOW will stay locked."
    fi

    if [[ "$MT5_START_MODE" == "off" ]]; then
      echo "MT5 launch skipped because QG_MT5_START_MODE=off."
    elif [[ "$MT5_START_MODE" == "live" ]]; then
      cp MQL5/Config/QuantGod_MT5_HFM_LivePilot.ini "$MT5_LIVE_CONFIG"
      patch_ini_key "$MT5_LIVE_CONFIG" "Symbol" "$MT5_START_SYMBOL"
      echo "Live MT5 config prepared at $MT5_LIVE_CONFIG."
      echo "Not launching live MT5 from the Mac launcher. Start it manually after checking live risk controls."
    else
      echo "Starting MT5 with the read-only HFM shadow config..."
      MT5_SHADOW_LOG="$SCRIPT_DIR/runtime/mt5_hfm_shadow_screen.log"
      mkdir -p "$SCRIPT_DIR/runtime"
      : > "$MT5_SHADOW_LOG"
      if command -v screen >/dev/null 2>&1; then
        screen -S "$MT5_SHADOW_SCREEN" -X quit >/dev/null 2>&1 || true
        screen -dmS "$MT5_SHADOW_SCREEN" /bin/zsh -lc \
          "cd '$MT5_ROOT' && exec env WINEPREFIX='$MT5_PREFIX' '$WINE64' terminal64.exe /portable '/config:C:\\qg\\QuantGod_MT5_HFM_Shadow_mac.ini' >> '$MT5_SHADOW_LOG' 2>&1"
        echo "MT5 read-only shadow started in screen session: $MT5_SHADOW_SCREEN"
      else
        (
          cd "$MT5_ROOT"
          WINEPREFIX="$MT5_PREFIX" "$WINE64" terminal64.exe /portable \
            '/config:C:\qg\QuantGod_MT5_HFM_Shadow_mac.ini' >> "$MT5_SHADOW_LOG" 2>&1 &
        )
        echo "MT5 read-only shadow started in background. Log: $MT5_SHADOW_LOG"
      fi
    fi
  fi
else
  echo "MT5 data folder not found yet: $MT5_ROOT"
  echo "Install/open MetaTrader 5 once, then run this script again."
fi

if [[ -d "$MT5_APP_PATH" && ! -x "$WINE64" ]]; then
  open "$MT5_APP_PATH" || true
fi

open "http://$QG_DASHBOARD_HOST:$QG_DASHBOARD_PORT/vue/" || true
exec node Dashboard/dashboard_server.js
