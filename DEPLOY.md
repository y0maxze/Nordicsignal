# Deployment

NordicSignal uses two production services:

- **Cloudflare Workers**: serves the `frontend/` static assets through `worker.js`.
- **Render**: runs the FastAPI application under `backend/`.

## Cloudflare Workers

The source of truth is `wrangler.toml`:

- `main = "worker.js"`
- `assets.directory = "./frontend"`
- `assets.binding = "ASSETS"`
- `assets.run_worker_first = true`
- explicit routes are handled by `worker.js`

For Cloudflare Workers Builds, the production deploy command must be:

```bash
npx wrangler deploy
```

Do not use `wrangler versions upload` as the production deploy command. That command creates a version/preview and does not by itself make the version receive 100% production traffic.

After a production build, confirm the newest version is deployed to production with 100% traffic before testing the `workers.dev` URL.

## Render API

Deploy `/backend` as a Python service with:

```bash
pip install -r requirements.txt
```

and start with:

```bash
uvicorn main:app --host 0.0.0.0 --port $PORT
```

The frontend uses the Render API directly today, while the Cloudflare Worker also exposes the same `/api/*` paths as a proxy.

## Important

Do not put API keys in the frontend repository. Market-data redistribution rights and provider terms must be validated before public/commercial launch.
