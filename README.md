# NordicSignal

NordicSignal is an Oslo Børs stock-intelligence dashboard built around transparent 0–100 scoring, verified data coverage and per-stock research tools.

## Current product

- Market dashboard with clickable score/coverage summary cards
- Stock Radar, Watchlist, Insider Activity, Short Radar and Markets views
- Per-stock intelligence workspace for every tracked ticker
- Verified company-specific news and reports with original-source links
- Public primary-insider disclosures with structured buy/sell, person/company, shares, price, value, post-trade holding and ownership percentage when available
- Finanstilsynet public short-position data
- Market Pressure view with transparent LONG proxy, public SHORT changes and abnormal-volume alerts
- Opportunity, Event Radar, IPO Radar, Morning Brief, alerts and evidence views
- PostgreSQL production storage with SQLite fallback for local development
- Cloudflare Worker shell with explicit application routes and a shared NordicSignal UI theme
- CI checks for Python tests, frontend JavaScript, Worker syntax, required assets, routes and navigation invariants

Paper Trading, the old user-facing Backtest and the Development/System page are retired product features. Internal validation/backtest jobs used to test signal hypotheses remain as research safeguards and are not user-facing trading tools.

## Architecture

- `frontend/` — static application pages and `theme.css`
- `worker.js` — Cloudflare routing, API proxy and small UI enhancement layer
- `backend/` — FastAPI service, providers, scoring and runtime enrichments
- `render.yaml` — Render API deployment configuration
- `wrangler.toml` — Cloudflare Workers + Static Assets configuration

## Main routes

- `/` — NordicSignal intro and risk acceptance flow
- `/app` — dashboard
- `/stock?ticker=LSG` — per-stock intelligence
- `/history` — historical price view
- `/news` — company news/events view
- `/morning` — morning brief
- `/calendar` — market/event calendar
- `/readiness` — investment check
- `/api/health` — backend health check

## Run locally

### Backend

```bash
cd backend
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload
```

### Frontend

```bash
python -m http.server 8080 --directory frontend
```

For the production-equivalent routing layer, use Wrangler with the repository-level `wrangler.toml`.

## Data integrity

NordicSignal should never invent market data. Public short data, insider details and company news must be traceable to their reported source. LONG/market-pressure indicators that are inferred from price/volume must remain explicitly labelled as proxies rather than Level 2 order-book data.

Before commercial/public redistribution, validate all market-data licences, exchange terms and source-specific redistribution rights.
