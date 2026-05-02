# QuantGod Phase 2 Implementation Notes

Phase 2 finishes the Phase 1 integration layer rather than replacing the existing dashboard architecture.
It keeps the local-only, read-only safety boundary intact while adding a unified API facade, Telegram push notifications, Ant Design Vue workspace scaffolding, and CI integration tests.

## Module D: Vue migration close-out + Ant Design Vue

Implemented in this overlay:

- `frontend/src/components/phase2/Phase2OperationsWorkspace.vue`
- `frontend/src/services/phase2Api.js`
- Installer patch for `frontend/package.json` to add `ant-design-vue`.
- Installer patch for `frontend/src/main.js` to register Ant Design Vue globally.
- Installer patch for `frontend/src/App.vue` to add a `Phase 2` workspace entry and mount the new workspace.

The new Phase 2 workspace uses Ant Design Vue components for layout, tables, cards, descriptions, tabs, buttons, alerts, and notifications. The existing 202 KB `App.vue` is patched conservatively because rewriting every hand-made card/table in one commit would be high-risk. The Phase 2 workspace becomes the migration target for unified API and notification operations.

## Module E: unified backend API facade

Implemented in:

- `Dashboard/phase2_api_routes.js`

The module is a self-contained CommonJS route handler that can be registered in the existing `dashboard_server.js`. It exposes local read-only endpoints under `/api/*` and reads JSON/CSV files from the runtime directory. Supported environment variables include:

- `QG_RUNTIME_DIR`
- `QG_MT5_FILES_DIR`
- `QG_HFM_FILES`
- `QG_HFM_FILES_DIR`

Key endpoint groups:

- `/api/governance/*`
- `/api/paramlab/*`
- `/api/trades/*`
- `/api/research/*`
- `/api/shadow/*`
- `/api/dashboard/*`
- `/api/polymarket/*`
- `/api/notify/*`

Every endpoint returns an envelope with:

```json
{
  "ok": true,
  "endpoint": "/api/...",
  "data": {},
  "source": {},
  "safety": {
    "readOnlyDataPlane": true,
    "notificationPushOnly": true,
    "orderSendAllowed": false,
    "closeAllowed": false,
    "cancelAllowed": false,
    "credentialStorageAllowed": false,
    "livePresetMutationAllowed": false,
    "telegramCommandExecutionAllowed": false
  }
}
```

CSV endpoints support these query parameters:

- `symbol=EURUSDc`
- `route=MA_Cross`
- `days=7`
- `limit=500`

## Module F: Telegram push notification system

Implemented in:

```text
tools/notify/
├── __init__.py
├── config.py
├── event_formatter.py
├── telegram_bot.py
└── notify_service.py

tools/run_notify.py
```

Supported event types:

- `TRADE_OPEN`
- `TRADE_CLOSE`
- `KILL_SWITCH`
- `NEWS_BLOCK`
- `AI_ANALYSIS`
- `CONSECUTIVE_LOSS`
- `DAILY_DIGEST`
- `GOVERNANCE`
- `TEST`

API endpoints:

- `GET /api/notify/config`
- `GET /api/notify/history?limit=50`
- `POST /api/notify/test`

The Telegram module is push-only. It does not accept commands, does not expose trade execution, and does not store secrets in Git. Bot token and chat ID must come from environment variables.

CLI smoke tests:

```powershell
python tools\run_notify.py config
python tools\run_notify.py test --message "QuantGod Phase 2 smoke" --dry-run
python tools\run_notify.py history --limit 10
python tools\run_notify.py daily-digest --dry-run
python tools\run_notify.py scan-once --dry-run
```

## Module G: CI/CD enhancement

Implemented in:

- `.github/workflows/ci.yml`
- `tests/node/test_phase2_api_routes.mjs`
- `tests/test_notify_formatter.py`
- `tests/test_notify_service.py`
- `tests/test_phase2_installer.py`
- `requirements-dev.txt` with `pytest-cov`
- root `package.json` with `npm test`

The CI workflow now includes:

- Vue build and committed `Dashboard/vue-dist` verification.
- Python unittest suite.
- Python coverage summary for `tools/`.
- Existing static/regression guards.
- Node API integration tests for the Phase 2 dashboard API facade.

## Local safety smoke checklist

```powershell
python -m unittest discover tests -v
python -m pytest tests -q --cov=tools --cov-report=term-missing
node --check Dashboard\phase2_api_routes.js
npm test
cd frontend
npm install
npm run build
cd ..
```

Then commit the generated `Dashboard/vue-dist` after the frontend build.
