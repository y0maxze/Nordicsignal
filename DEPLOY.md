# Deployment

NordicSignal uses two production services:

- **Cloudflare Workers + Static Assets** serves `frontend/` through `worker.js`.
- **Render** runs the FastAPI application under `backend/`.

## Cloudflare Workers

The source of truth is `wrangler.toml`:

- `main = "worker.js"`
- `assets.directory = "./frontend"`
- `assets.binding = "ASSETS"`
- `assets.run_worker_first = true`
- explicit application routes are handled by `worker.js`

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
uvicorn production:app --host 0.0.0.0 --port $PORT
```

`production:app` is intentional: it replaces the blocking development startup handler with the non-blocking production warmup, installs production indexes, and removes exact shadowed route duplicates.

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
