# NordicSignal production readiness

NordicSignal is currently designed as an internal/single-user finance intelligence tool. This checklist is deliberately conservative: code support is not the same thing as an externally verified control.

## Implemented in the application

- Persistent PostgreSQL storage with health reporting.
- Same-origin Cloudflare Worker API proxy.
- API timing and performance telemetry.
- Persistent news/insider feed caching and persistent Euronext detail caching.
- Data-quality endpoint: `/api/data-quality`.
- Operational readiness endpoint: `/api/ops-readiness`.
- Security status endpoint: `/api/security-status`.
- Write/refresh audit log and bounded rate limiting.
- Worker-to-backend shared-secret verification.
- Private-mode lock that rejects direct Render API access for every API route except `/api/health`.
- Security headers on Worker/API responses.
- Real Web Push subscription/delivery code with local-notification fallback.
- Historical signal-evidence replay for trend/activity signals at 5/20/60 trading-day horizons.
- Mobile `Siden sist` priority brief.

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

## Required to enable true iPhone/PWA background push

Generate a VAPID key pair and configure on Render:

```text
NORDICSIGNAL_VAPID_PUBLIC_KEY=<public application server key>
NORDICSIGNAL_VAPID_PRIVATE_KEY=<private key; secret>
NORDICSIGNAL_VAPID_SUBJECT=https://nordicsignal.8pnwk5r8f4.workers.dev
```

Never commit the private VAPID key to GitHub.

After deployment, `/api/push/status` must report `delivery_ready: true`. Then install NordicSignal to the iPhone Home Screen, enable notifications from the installed PWA and use `/api/push/test` through the authenticated application to verify a real background notification.

A sleeping backend cannot originate a push until it wakes. If reliable low-latency alerts are required, use an always-on backend or an external scheduler/queue.

## Required before calling backups verified

Use provider-managed PostgreSQL backups and/or an independent encrypted backup process. A backup is not considered verified until a restore into a separate database has succeeded and the restored tables/counts have been checked.

Only after a successful restore test set:

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
- `/api/data-quality` — finance-data validation and freshness
- `/api/performance` — in-process API latency
- `/api/security-status` — Worker secret and direct-backend lock status
- `/api/push/status` — Web Push readiness
- `/api/ops-readiness` — consolidated maturity blockers

The intended progression is:

```text
internal_single_user -> private_ready -> commercial_ready
```

The system should fail visibly and conservatively when a required external control is missing rather than claiming readiness from UI state alone.
