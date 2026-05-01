# QuantGod AI Analysis Phase 1 Integration Notes

This change adds the Phase 1 backend seed for the design document:

- `tools/ai_analysis/` implements config, OpenRouter client, three agents, data collection, orchestration, storage, and Governance evidence writing.
- `tools/run_ai_analysis.py` exposes a CLI that the local Node dashboard server can call.
- `tools/mt5_chart_readonly.py` exposes read-only kline/trades/shadow-signal payload builders for Module B API wiring.
- `tests/test_ai_analysis.py` and `tests/test_mt5_chart_readonly.py` keep the new code terminal-independent and safe in CI.

## Safety boundary

All new outputs carry read-only/advisory metadata:

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

The AI report is written for review only. It must not place orders, close orders, cancel orders, change `.set` files, promote/demote routes, or override kill switches/news filters/dry-run guards.

## CLI smoke tests

```powershell
python tools\run_ai_analysis.py config
python tools\run_ai_analysis.py run --symbol EURUSDc --timeframes M15,H1,H4,D1
python tools\run_ai_analysis.py latest
python tools\run_ai_analysis.py history --symbol EURUSDc --limit 20

python tools\mt5_chart_readonly.py kline --symbol EURUSDc --tf H1 --bars 200
python tools\mt5_chart_readonly.py trades --symbol EURUSDc --days 30
python tools\mt5_chart_readonly.py shadow-signals --symbol EURUSDc --days 7
```

When `OPENROUTER_API_KEY` is missing or the LLM response is invalid, the agents return deterministic fallback reports from local OHLC/runtime evidence. Set `AI_ANALYSIS_MOCK_MODE=true` for offline development.

## Node dashboard server wiring

The existing `Dashboard/dashboard_server.js` already has helpers for spawning JSON Python scripts. Wire these paths as the next incremental patch:

- `POST /api/ai-analysis/run` -> `python tools/run_ai_analysis.py run --symbol <symbol> --timeframes <csv>`
- `GET /api/ai-analysis/latest` -> `python tools/run_ai_analysis.py latest --allow-empty`
- `GET /api/ai-analysis/history?symbol=&limit=20` -> `python tools/run_ai_analysis.py history --symbol <symbol> --limit <n>`
- `GET /api/ai-analysis/history/:id` -> `python tools/run_ai_analysis.py history-item --id <id>`
- `GET /api/ai-analysis/config` -> `python tools/run_ai_analysis.py config`
- `GET /api/mt5-readonly/kline?symbol=EURUSDc&tf=H1&bars=200` -> `python tools/mt5_chart_readonly.py kline --symbol EURUSDc --tf H1 --bars 200`
- `GET /api/mt5-readonly/trades?symbol=EURUSDc&days=30` -> `python tools/mt5_chart_readonly.py trades --symbol EURUSDc --days 30`
- `GET /api/shadow-signals?symbol=EURUSDc&days=7` -> `python tools/mt5_chart_readonly.py shadow-signals --symbol EURUSDc --days 7`

Keep these routes localhost-only and read-only. Do not add them to the guarded trading namespace.

## Governance evidence

A successful run writes:

- `<AI_ANALYSIS_HISTORY_DIR>/latest.json`
- `<AI_ANALYSIS_HISTORY_DIR>/history/<timestamp>_<symbol>.json`
- `<QG_RUNTIME_DIR>/QuantGod_AIAnalysisEvidence.json`

`QuantGod_AIAnalysisEvidence.json` is the only artifact Governance should read. It is explicitly marked `advisoryOnly=true` and `canPromoteOrDemoteRoute=false`.
