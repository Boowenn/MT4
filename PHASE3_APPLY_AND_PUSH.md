# Apply QuantGod Phase 3 Overlay

```powershell
cd C:\path\to\QuantGod
git checkout main
git pull origin main
git checkout -b phase3-vibe-ai-v2
```

Copy the overlay files into the repo, then run:

```powershell
python tools\apply_phase3_full.py --repo-root .
python -m unittest discover tests -v
node --check Dashboard\phase3_api_routes.js
npm test
cd frontend
npm install
npm run build
cd ..
```

Smoke tests:

```powershell
python tools\run_vibe_coding.py config
python tools\run_vibe_coding.py generate --description "Buy RSI oversold rebound with H1 trend filter" --symbol EURUSDc --tf H1
python tools\run_ai_analysis_v2.py config
python tools\run_ai_analysis_v2.py run --symbol EURUSDc --timeframes M15,H1,H4,D1
python tools\kline_phase3_overlays.py realtime-config
```

Commit:

```powershell
git status
git add .
git commit -m "Implement Phase 3 Vibe Coding and AI Analysis V2"
git push origin phase3-vibe-ai-v2
```
