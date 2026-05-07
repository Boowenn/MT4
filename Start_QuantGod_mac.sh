#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORKSPACE_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
BACKEND_LAUNCHER="$WORKSPACE_ROOT/QuantGodBackend/Start_QuantGod_mac.sh"

if [[ ! -x "$BACKEND_LAUNCHER" ]]; then
  echo "QuantGodBackend launcher not found or not executable: $BACKEND_LAUNCHER" >&2
  exit 1
fi

echo "Delegating old QuantGod launcher to split-repo QuantGodBackend v2.5 launcher..."
exec "$BACKEND_LAUNCHER" "$@"
