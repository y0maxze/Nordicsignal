# Deployment

NordicSignal uses two production services:

- **Cloudflare Workers + Static Assets** serves `frontend/` through `scheduler_worker.js` / `worker.js`.
- **Render** runs the FastAPI application under `backend/`.

## Cloudflare Workers

The source of truth is `wrangler.toml`:

- `main = "scheduler_worker.js"`
- `assets.directory = "./frontend"`
- `assets.binding = "ASSETS"`
- `assets.run_worker_first = true`
- explicit application routes are handled by `worker.js`
- Opportunity autoscan runs every 10 minutes
- authenticated provider-wide market refresh runs hourly at minute 17

Production deploy command:

```bash
npx wrangler deploy
```

Do not use `wrangler versions upload` as the production deploy command. A version upload alone does not guarantee that the new version receives production traffic.

### Routes to verify after deploy

- `/app`
- `/stock?ticker=LSG`
- `/stock?ticker=LSG&tab=news`
- `/stock?ticker=LSG&tab=insider`
- `/stock?ticker=LSG&tab=paper`
- `/stock?ticker=LSG&tab=backtest`
- `/stock?ticker=LSG&tab=pressure`
- `/paper`
- `/history`
- `/news`
- `/theme.css`

Confirm the NordicSignal logo returns to `/app` and that dashboard summary cards open their filtered stock lists.

## Render API

Render is configured by `render.yaml` with `rootDir: backend`, a health check at `/api/health`, and automatic deploys from commits.

Build:

```bash
pip install -r requirements.txt
```

Start:

```bash
uvicorn api_entrypoint:app --host 0.0.0.0 --port $PORT
```

`api_entrypoint:app` is intentional. It imports the hardened production route/runtime configuration but replaces deploy-time provider warmup with database/schema/index initialization only. Provider-wide market work is owned by the authenticated Cloudflare cron, while manual/scheduled `/api/refresh` still uses the bounded production refresh implementation and its cooldown guard.

Backend dependencies are pinned in `backend/requirements.txt` so CI and Render use the same tested versions.

### PostgreSQL storage

Set `DATABASE_URL` to the Render PostgreSQL internal connection string. PostgreSQL is the recommended production store. SQLite remains a local-development fallback when `DATABASE_URL` is absent.

Keep the current API at one instance until paper-account writes and refresh jobs are explicitly designed for multi-instance concurrency.

After every backend deployment verify at least:

- `/api/health`
- `/api/stocks`
- `/api/verification`
- `/api/news/LSG`
- `/api/insider/LSG`
- `/api/short/LSG`
- `/api/market-pressure/LSG`
- `/api/paper/portfolio`
- `/api/paper/dashboard`
- `/api/opportunity-performance`

## CI gate

`.github/workflows/ci.yml` validates:

- Python compilation
- backend unit tests
- inline frontend JavaScript syntax
- standalone frontend JavaScript syntax
- Cloudflare Worker syntax
- required frontend assets
- production route declarations
- key navigation/deep-link invariants

A production deploy should not be treated as ready until the latest `main` workflow is green.

## Paper trading integrity

Starting capital cannot be changed after the first paper trade. Reset the paper account first if a new starting balance is required. This avoids revaluing historical performance against a different initial-capital assumption.

## Data and security notes

Do not put API keys or secrets in frontend files or Git. Market-data redistribution rights and provider terms must be validated before public/commercial launch. Inferred market-pressure signals must remain labelled as proxies and must not be presented as Level 2 order-book data.
