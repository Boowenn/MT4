#!/bin/sh
set -eu

: "${QG_RUNTIME_DIR:=/app/runtime}"
: "${QG_STATE_DB:=/app/runtime/quantgod_state.sqlite}"

mkdir -p "$QG_RUNTIME_DIR"
python3 tools/run_state_store.py --db "$QG_STATE_DB" init

exec "$@"
