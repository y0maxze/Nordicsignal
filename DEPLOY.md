# NordicSignal Cloudflare deployment

This package contains a static frontend at the repository root (`index.html`) so it can be deployed as a simple Cloudflare static site.

For the current GitHub-connected Cloudflare setup:
- Build command: leave empty
- Build output directory: repository root (`/`)
- Do not enable Cloudflare Access for the public site
- No environment variables are required for the static demo

The FastAPI backend remains in `/backend` and is intentionally separated. It can be deployed later as a Worker/container/service and then connected to the frontend through an API URL.

The current frontend uses demo data when the API is unavailable, so the site remains viewable before the backend is deployed.
