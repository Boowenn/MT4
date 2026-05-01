# Apply and push QuantGod Phase 1

1. Pull the newest remote branch.

```bash
cd /path/to/QuantGod
git pull origin main
```

2. Copy all files from this overlay into the repo root.

3. Install the server/frontend hooks.

```bash
python tools/apply_phase1_full.py --repo-root .
```

4. Run tests and rebuild the committed dashboard bundle.

```bash
python -m unittest discover tests -v
cd frontend
npm install
npm run build
cd ..
```

5. Commit and push.

```bash
git status
git add .
git commit -m "Implement QuantGod Phase 1 AI analysis and K-line workspace"
git push origin main
```

Important: if a GitHub token was pasted into a chat, revoke/rotate it in GitHub developer settings before relying on it again.
