# QuantGod Cloudflare Layer

This folder deploys the existing dashboard plus a lightweight ingest API.

## What It Does

- Serves `../Dashboard/QuantGod_Dashboard.html` on Cloudflare
- Accepts MT4 snapshot pushes at `/api/ingest`
- Stores the latest snapshot in Cloudflare KV
- Exposes the latest snapshot at `/api/latest`

## Deploy Steps

1. Open a terminal in this folder:

```powershell
cd C:\Users\OWNER\QuantGod_MT4\cloudflare
```

2. Create a KV namespace:

```powershell
npx wrangler kv namespace create QG_STATE
npx wrangler kv namespace create QG_STATE --preview
```

3. Paste the returned `id` and `preview_id` into `wrangler.jsonc`.

4. Set the ingest token:

```powershell
npx wrangler secret put QG_INGEST_TOKEN
```

5. Deploy:

```powershell
npx wrangler deploy
```

After deploy, the dashboard will be available on your Worker domain and the API paths will be:

- `/api/health`
- `/api/latest`
- `/api/ingest`

## MT4 Settings

In EA inputs:

- `EnableCloudSync = true`
- `CloudSyncEndpoint = https://<your-worker-domain>/api/ingest`
- `CloudSyncToken = <same token as QG_INGEST_TOKEN>`

In MT4 terminal settings, add the same domain to:

- `Tools -> Options -> Expert Advisors -> Allow WebRequest for listed URL`

Example:

```text
https://your-worker-domain.workers.dev
```

## Dashboard Source Selection

- Local mode still reads `QuantGod_Dashboard.json`
- Cloud mode defaults to `/api/latest`
- You can force a custom API by appending `?api=https://your-domain/api/latest`
