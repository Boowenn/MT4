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

PYTHON_BIN="${QG_PYTHON_BIN:-python3}"
MODE="--once"
if [[ "${1:-}" == "--loop" ]]; then
  MODE="--loop"
  shift
elif [[ "${1:-}" == "--once" ]]; then
  MODE="--once"
  shift
fi

EXTRA_ARGS=()
if [[ "${QG_DAILY_AUTOPILOT_ALLOW_TESTER_RUN:-0}" == "1" ]]; then
  EXTRA_ARGS+=("--allow-tester-run")
fi

if [[ ${#EXTRA_ARGS[@]} -gt 0 ]]; then
  exec "$PYTHON_BIN" tools/run_daily_autopilot.py "$MODE" "${EXTRA_ARGS[@]}" "$@"
else
  exec "$PYTHON_BIN" tools/run_daily_autopilot.py "$MODE" "$@"
fi
