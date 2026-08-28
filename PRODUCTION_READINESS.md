# NordicSignal production readiness

NordicSignal is currently designed as an internal/single-user finance intelligence tool. This checklist is deliberately conservative: code support is not the same thing as an externally verified control.

## Implemented in the application

- Persistent PostgreSQL storage with health reporting.
- Same-origin Cloudflare Worker API proxy.
- API timing and performance telemetry.
- Persistent news/insider feed caching and persistent Euronext detail caching.
- Data-quality endpoint: `/api/data-quality`, including source/cache freshness timestamps.
- Operational readiness endpoint: `/api/ops-readiness`.
- Security status endpoint: `/api/security-status`.
- Write/refresh audit log and bounded rate limiting.
- Worker-to-backend shared-secret verification.
- Private-mode lock that rejects direct Render API access for every API route except `/api/health`.
- Security headers on Worker/API responses.
- Real Web Push subscription/delivery code with local-notification fallback and a mobile delivery-test control.
- Safe local VAPID generator: `backend/generate_vapid_keys.py`.
- Non-destructive restored-database verifier: `backend/backup_verify.py`.
- Historical signal-evidence replay for trend/activity signals at 5/20/60 trading-day horizons, with sample-size-aware UI.
- Mobile `Siden sist` priority brief.

## Current operating mode

Authentication is intentionally deferred while NordicSignal remains a single-user internal project. Keep:

```text
NORDICSIGNAL_EXTERNAL_AUTH_CONFIGURED=false
```

until real Cloudflare Access (or equivalent) has actually been enabled and tested. The public URL must therefore still be treated as discoverable; do not put passwords, API secrets or sensitive personal data in frontend code.

## Required before calling the deployment private

### 1. Real access authentication

Put Cloudflare Access or an equivalent server-side identity layer in front of NordicSignal. A password embedded in HTML/JavaScript is **not** acceptable authentication.

Do not set `NORDICSIGNAL_EXTERNAL_AUTH_CONFIGURED=true` yet. First complete the Worker secret in step 2 and verify Cloudflare Access actually blocks an unauthenticated browser.

### 2. Worker-to-backend internal secret

Generate a long random secret and configure the **same value** as `NORDICSIGNAL_WRITE_TOKEN` in:

- Cloudflare Worker secret/environment configuration
- Render backend secret/environment configuration

The browser never needs to know this value. Cloudflare attaches it to every proxied `/api/*` request.

After both copies of the secret are configured, `/api/security-status` through the Worker should report:

```text
shared_secret_configured: true
write_protection: shared_secret
```

### 3. Enable the direct-backend lock

Only after Cloudflare Access has been tested and the same internal secret exists on both Cloudflare and Render, set on Render:

```text
NORDICSIGNAL_EXTERNAL_AUTH_CONFIGURED=true
```

This switches the Render backend to fail-closed private mode. Every `/api/*` request except `/api/health` must then carry the internal Worker secret. A browser opening the direct `onrender.com` API URL should receive `401 BACKEND_PROXY_AUTH_REQUIRED`, while the same API route through the Cloudflare Worker should still return normally after Access login.

Private readiness requires all three controls:

```text
external_auth: ready
write_secret: ready
direct_backend_lock: ready
```

## True iPhone/PWA background push

The code is complete, but delivery remains disabled until VAPID secrets exist on Render.

Generate a pair **once** from an environment where backend dependencies are installed:

```text
cd backend
python generate_vapid_keys.py
```

The script prints:

```text
NORDICSIGNAL_VAPID_PUBLIC_KEY=...
NORDICSIGNAL_VAPID_PRIVATE_KEY=...
NORDICSIGNAL_VAPID_SUBJECT=...
```

Copy those values directly into Render environment variables. Never commit or paste the private key into source code. Regenerating the pair invalidates existing browser push subscriptions.

Use:

```text
NORDICSIGNAL_VAPID_SUBJECT=https://nordicsignal.8pnwk5r8f4.workers.dev
```

After deployment, `/api/push/status` must report `delivery_ready: true`. Install NordicSignal to the iPhone Home Screen, enable notifications from the installed PWA, then use the **Test push** button on the mobile overview. A successful test must be verified with the PWA minimized/closed, not merely while the page is foregrounded.

A sleeping backend cannot originate a push until it wakes. If reliable low-latency alerts are required, use an always-on backend or an external scheduler/queue.

## Backup + restore verification

Use provider-managed PostgreSQL backups and/or an independent encrypted backup process. A backup is not considered verified until a restore into a **separate** database has succeeded.

After restoring, compare production and restored database non-destructively:

```text
DATABASE_URL=<production read-only database URL>
NORDICSIGNAL_RESTORE_DATABASE_URL=<separate restored database URL>
python backend/backup_verify.py
```

The tool prints table counts/fingerprints only; it does not print row contents and does not mutate either database. It fails if an important table is missing or row counts differ. The restored application should also receive a normal smoke test before declaring backup readiness.

Only after a successful restore comparison **and** smoke test set:

```text
NORDICSIGNAL_BACKUP_VERIFIED=true
```

Do not add a public database-export endpoint as a substitute for backup infrastructure.

## Required before multi-user/commercial use

- Real authenticated user identity on every private/read-write request.
- User-owned holdings/watchlists/accounts keyed by an immutable user ID.
- Row-level/application-level authorization tests proving one user cannot read or modify another user's data.
- Authenticated push subscriptions scoped to the owning user.
- CSRF/session protection appropriate to the selected identity model.
- Retention/deletion/export policy for user data.
- Monitoring/alerting for backend/database failures.
- Backup restore drills.
- External legal/financial review of product copy, risk language, data licensing and intended commercial use.

`multi_user_isolation` intentionally remains a blocker in `/api/ops-readiness` until this work is done together with real authentication.

## Legal review

The existing risk/disclaimer gate is product copy, not legal certification. After an appropriately qualified external review has actually been completed, set:

```text
NORDICSIGNAL_LEGAL_REVIEW_CONFIRMED=true
```

Do not use the flag as a self-certification mechanism.

## Readiness endpoints

Use these together:

- `/api/system-health` — storage/table/runtime health
- `/api/data-quality` — finance-data validation, provenance and freshness
- `/api/performance` — in-process API latency
- `/api/security-status` — Worker secret and direct-backend lock status
- `/api/push/status` — Web Push readiness
- `/api/ops-readiness` — consolidated maturity blockers

The intended progression is:

```text
internal_single_user -> private_ready -> commercial_ready
```

The system should fail visibly and conservatively when a required external control is missing rather than claiming readiness from UI state alone.
