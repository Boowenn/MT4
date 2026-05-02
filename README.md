# QuantGodBackend

Backend repository for QuantGod.

This repo contains the local-first trading/research backend only:

- `MQL5/` — MT5 EA source, presets, tester configs, and live/shadow guarded runtime assets.
- `Dashboard/` — local Node API server and backend-served static frontend target (`Dashboard/vue-dist/`, populated from the frontend repo by infra sync).
- `tools/` — Python research, Governance, ParamLab, AI analysis, Vibe Coding, Telegram notification, MT5 bridge, and CI guard tools.
- `tests/` — Python and Node backend/API contract tests.
- `archive/` — local backtest/ParamLab/research archives; generated run data is ignored unless intentionally promoted.

Frontend source, Cloudflare/infra automation, and full documentation have been split out:

- Frontend: <https://github.com/Boowenn/QuantGodFrontend>
- Infra: <https://github.com/Boowenn/QuantGodInfra>
- Docs: <https://github.com/Boowenn/QuantGodDocs>

## Local development

```powershell
python -m unittest discover tests -v
python -m pytest tests -q --cov=tools --cov-report=term-missing
node --test tests/node/*.mjs
Dashboard\start_dashboard.bat
```

Open the Vue workbench after the frontend dist has been synced:

```text
http://localhost:8080/vue/
```

During frontend development, run `QuantGodFrontend` separately on Vite and use its dev proxy to call this backend at `http://127.0.0.1:8080`.

## Frontend dist sync

The backend does not own Vue source anymore. Build frontend in `QuantGodFrontend`, then sync the compiled dist into this repo's served folder:

```powershell
cd ..\QuantGodFrontend
npm install
npm run build
cd ..\QuantGodInfra
python scripts\qg-workspace.py --workspace workspace\quantgod.workspace.json sync-frontend-dist
```

## Safety boundaries

Automation cannot bypass Kill Switch, authorization locks, dry-run guards, live preset mutation guards, Telegram push-only boundaries, or Vibe Coding research-only boundaries. Any live-route change must still pass backtest evidence, ParamLab, Governance, Version Gate, and manual authorization.
