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

### Persistent SQLite storage

The backend now supports the `NORDICSIGNAL_DB_PATH` environment variable. This is required if SQLite data such as watchlists and paper trades must survive Render restarts and deploys.

Recommended Render setup for the current single-instance SQLite architecture:

1. Attach a Render Persistent Disk to the API service.
2. Use mount path `/var/data`.
3. Set the environment variable:

```text
NORDICSIGNAL_DB_PATH=/var/data/nordicsignal.db
```

4. Keep the service at one instance. Render persistent disks are single-instance storage and cannot be combined with autoscaling.

If `NORDICSIGNAL_DB_PATH` is not set, local development continues to use `backend/nordicsignal.db`.

## Paper trading integrity

Starting capital cannot be changed after the first paper trade. Reset the paper account first if a new starting balance is required. This prevents historical trades from being revalued against a different starting-capital assumption.

## Important

Do not put API keys in the frontend repository. Market-data redistribution rights and provider terms must be validated before public/commercial launch.
