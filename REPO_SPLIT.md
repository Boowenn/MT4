# Backend split status

This repository is the backend member of the QuantGod four-repo workspace.

## Kept here

- MT5/MQL5 engine and presets
- Node dashboard/API server
- Python tools and tests
- backend contract tests
- local launchers and guarded MT5 workflows

## Moved out

- `frontend/` → `Boowenn/QuantGodFrontend`
- `cloudflare/` → `Boowenn/QuantGodInfra`
- full `docs/` tree → `Boowenn/QuantGodDocs`

## Build linkage

Frontend source builds to `QuantGodFrontend/dist`. Infra sync copies it into `QuantGodBackend/Dashboard/vue-dist` for the backend server to serve at `/vue/`.
