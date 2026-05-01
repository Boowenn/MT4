# QuantGod Phase 1 Implementation

This overlay implements Phase 1 from `QuantGod_Phase1_Design_v2.docx` on top of the current `main` branch.

## Delivered modules

### Module A: AI multi-agent analysis V1

Files:

- `tools/ai_analysis/config.py`
- `tools/ai_analysis/llm_client.py`
- `tools/ai_analysis/market_data_collector.py`
- `tools/ai_analysis/analysis_service.py`
- `tools/ai_analysis/agents/*.py`
- `tools/ai_analysis/prompts/*.md`
- `tools/run_ai_analysis.py`
- `Dashboard/phase1_api_routes.js`
- `frontend/src/components/phase1/AiAnalysisWorkspace.vue`

The pipeline is advisory only:

1. collect a read-only `MarketSnapshot`
2. run `TechnicalAgent` and `RiskAgent` in parallel
3. run `DecisionAgent` after both reports are available
4. save `latest.json` and `history/*.json`
5. write `QuantGod_AIAnalysisEvidence.json` for Governance Advisor consumption

The evidence file explicitly sets:

- `advisoryOnly=true`
- `canExecuteTrade=false`
- `canOverrideKillSwitch=false`
- `canMutateLivePreset=false`
- `canPromoteOrDemoteRoute=false`

### Module B: professional K-line chart integration

Files:

- `tools/mt5_chart_readonly.py`
- `frontend/src/components/phase1/kline/KlineWorkspace.vue`
- `frontend/src/components/phase1/kline/KlineToolbar.vue`
- `frontend/src/components/phase1/kline/KlineChart.vue`
- `frontend/src/components/phase1/kline/SignalOverlay.vue`

The chart endpoints are read-only:

- `GET /api/mt5-readonly/kline?symbol=EURUSDc&tf=H1&bars=200`
- `GET /api/mt5-readonly/trades?symbol=EURUSDc&days=30`
- `GET /api/shadow-signals?symbol=EURUSDc&days=7`

`tools/mt5_chart_readonly.py` uses `copy_rates_from_pos` only for K-line data and reads runtime CSV ledgers for trade/shadow overlays. It never sends orders, closes positions, cancels orders, selects symbols, stores credentials, or mutates presets.

### Module C: CI/testing foundation

Files:

- `tests/test_ai_analysis.py`
- `tests/test_mt5_chart_readonly.py`
- `tests/test_phase1_installers.py`
- `requirements-dev.txt`
- `pyproject.toml`

The repo's current CI already runs `python -m unittest discover tests` and `frontend npm run build`; after applying the overlay and running the frontend build, commit the regenerated `Dashboard/vue-dist` files as required by the current CI.

## Installation

From a freshly pulled repo root:

```bash
git pull origin main
# Copy this overlay into the repo root first, then:
python tools/apply_phase1_full.py --repo-root .
python -m unittest discover tests -v
cd frontend
npm install
npm run build
cd ..
git status
```

Then commit and push:

```bash
git add Dashboard/phase1_api_routes.js Dashboard/dashboard_server.js frontend package.json package-lock.json tools tests docs requirements-dev.txt pyproject.toml Dashboard/vue-dist
git commit -m "Implement QuantGod Phase 1 AI analysis and K-line workspace"
git push origin main
```

## Runtime configuration

```bash
export OPENROUTER_API_KEY="..."
export AI_MODEL_TECHNICAL="anthropic/claude-sonnet-4-20250514"
export AI_MODEL_RISK="anthropic/claude-sonnet-4-20250514"
export AI_MODEL_DECISION="anthropic/claude-sonnet-4-20250514"
export AI_ANALYSIS_HISTORY_DIR="MQL5/Files/ai_analysis"
export QG_RUNTIME_DIR="MQL5/Files"
```

Without an OpenRouter key, the pipeline uses deterministic local fallback output so dashboard wiring and CI remain testable.

## Smoke tests

```bash
python tools/run_ai_analysis.py config
python tools/run_ai_analysis.py run --symbol EURUSDc --timeframes M15,H1,H4,D1
python tools/run_ai_analysis.py latest
python tools/run_ai_analysis.py history --symbol EURUSDc --limit 20
python tools/mt5_chart_readonly.py kline --symbol EURUSDc --tf H1 --bars 200
python tools/mt5_chart_readonly.py trades --symbol EURUSDc --days 30
python tools/mt5_chart_readonly.py shadow-signals --symbol EURUSDc --days 7
```
