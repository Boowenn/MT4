# Apply and push QuantGod Phase 2 overlay

Run these commands from your local QuantGod repository after pulling the newest `main` branch.

```powershell
git checkout main
git pull origin main
git checkout -b phase2-integration
```

Unzip `quantgod_phase2_full_overlay.zip` into a temporary directory, then copy its contents over the repository root.

```powershell
Expand-Archive C:\path\to\quantgod_phase2_full_overlay.zip -DestinationPath C:\temp\qg_phase2 -Force
Copy-Item C:\temp\qg_phase2\quantgod_phase2_full_overlay\* . -Recurse -Force
```

Apply repository-specific patches.

```powershell
python tools\apply_phase2_full.py --repo-root .
```

Run backend and integration tests.

```powershell
python -m unittest discover tests -v
python -m pytest tests -q --cov=tools --cov-report=term-missing
node --check Dashboard\phase2_api_routes.js
npm test
```

Rebuild the Vue dashboard and commit the generated static files.

```powershell
cd frontend
npm install
npm run build
cd ..
```

Smoke test the new CLI/API helpers.

```powershell
python tools\run_notify.py config
python tools\run_notify.py test --message "QuantGod Phase 2 smoke" --dry-run
python tools\run_notify.py history --limit 10
```

Set Telegram secrets only in your local environment or `.env.local`, never in Git.

```powershell
$env:TELEGRAM_BOT_TOKEN="<bot-token>"
$env:TELEGRAM_CHAT_ID="<chat-id>"
```

Commit and push.

```powershell
git status
git add .
git commit -m "Implement Phase 2 API unification and Telegram notifications"
git push origin phase2-integration
```

After CI passes, open a pull request or merge according to your repository rules.
