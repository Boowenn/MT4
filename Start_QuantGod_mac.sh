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
RUNTIME_SOURCE="${QG_MAC_RUNTIME_SOURCE:-auto}"

if [[ -d "$MT5_ROOT" && ( "$RUNTIME_SOURCE" == "mt5" || ( "$RUNTIME_SOURCE" == "auto" && "$RUNTIME_CONFIGURED" == "0" ) ) ]]; then
  export QG_RUNTIME_DIR="$MT5_FILES"
  export QG_MT5_FILES_DIR="$MT5_FILES"
fi

echo "QuantGod Mac launcher"
echo "Repo: $SCRIPT_DIR"
echo "Runtime: $QG_RUNTIME_DIR"
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

    echo "Starting MT5 with the read-only HFM shadow config..."
    WINEPREFIX="$MT5_PREFIX" "$WINE64" \
      'C:\Program Files\MetaTrader 5\terminal64.exe' \
      '/config:C:\qg\QuantGod_MT5_HFM_Shadow_mac.ini' >/dev/null 2>&1 &
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
