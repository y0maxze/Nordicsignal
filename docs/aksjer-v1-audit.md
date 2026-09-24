# Aksjer V1 audit — 2026-09-24

This is an audit checkpoint, not a V1 completion certificate.

## Verified baseline

PR #108 was repaired after reading failing CI job 107576522515. The duplicate
`openStock` function and remaining `showStock` callers were removed. All three
mandatory gates passed on 76da3d89365f1c15de391a552ed8e39dc4fe64f7.
PR #108 was merged with that expected head into
`a0562d9b2b5e8150c71b12e2179dc32ce26bdfda`. Main CI, Cloudflare deployment and
Render deploy dep-daqf4uou01pc73cp9ivg were verified on that SHA.

## This change

- Market uses one read-only stored snapshot; two DB queries independent of universe
  size. No per-stock Opportunity provider calls or portfolio requests on initial load.
- Rankings survive filtering. Missing prices and returns remain missing. Insider
  filtering requires verified evidence, not a numeric score. No daily ownership claim.
- Stock uses continuous analysis sections. Retired readiness/Opportunity injections
  remain absent. Historical evidence is lazy-loaded with N/maturity and raw-return labels.
- Yahoo quote timestamps are market timestamps, not retrieval timestamps. Multi-day
  chartPreviousClose is not used as yesterday's closing price. Realtime is never assumed.
- Morning uses at most eight deduplicated points, Oslo timezone, verified calendar
  boundaries, source links and partial/unavailable states.
- Public Worker requests cannot borrow the internal secret for writes or personal
  holdings/watchlist reads. Scheduler refresh uses POST directly to the protected backend.
- Primary pages do not start legacy alert polling. PWA shell v7 handles uncached
  offline routes explicitly and does not navigate notifications to external origins.
- Main score, Opportunity rules, High Conviction, alerts and sizing are unchanged.
  Early Discovery, IPO, ownership and Capital Flow remain research-only.

## Outstanding operational blockers and debt

| File / setting | Finding and risk | Required next action |
|---|---|---|
| Cloudflare Access / `worker.js`, `backend/security_runtime.py` | Production security-status reports external authentication NOT configured. Public analysis pages remain public. Blocking unauthenticated writes is containment, not authentication. Browser push enrollment is therefore unavailable. | Establish owner identity and authenticated Cloudflare access for the Worker; verify JWT/Access enforcement before enabling browser writes. Then enable and verify direct-backend private mode. Never claim the service is private before negative unauthenticated tests pass. |
| Render service start command / `backend/api_entrypoint.py` | Actual service starts `main:app`, while render.yaml expects `api_entrypoint:app`. Provider-free startup and production wrappers are not guaranteed by repository configuration alone. | Change actual service start command to documented api_entrypoint after review, redeploy exact tested SHA and verify startup logs/health. The available Render connector does not expose this setting; browser requires sign-in. |
| `backend/main.py`, `backend/market_coverage_runtime.py`, `backend/production.py`, `backend/api_entrypoint.py` | Startup callbacks are registered and selectively removed by layered runtime imports. Four FastAPI deprecation warnings remain. Blind lifespan conversion could double-run or omit startup work. | First reconcile actual Render entrypoint. Then migrate all participating callbacks together with provider-free startup and shutdown tests in a separate gated PR. |
| `backend/oslo_session.py` | Calendar verified for 2026 only; exceptional 1 April half-day close is unknown. Unknown dates return partial coverage rather than guessed boundaries. | Add versioned official timetable and year coverage with source-backed holiday/half-day tests before 2027. |
| `frontend/stock_analysis.js` / providers | Benchmark-relative strength and licensed daily ownership are unavailable. Financial reporting period/currency may be absent in upstream response. | Maintain explicit missing states until verified source fields exist; do not relabel raw return as excess or infer ownership from insider scores. |
| `backend/signal_evidence_runtime.py` | Historical replay is research, not a tradable execution simulation. Same-close observations do not establish executable after-close fills, costs or benchmark excess returns. | Validate decision timestamp, execution lag and benchmark alignment point-in-time before any score/threshold change. |
| Legacy secondary assets and contract checks | Retained files contain portfolio/readiness/Market Pressure code needed by existing runtime or tests. They must remain outside canonical page execution. | Remove in a separate dependency-aware cleanup after replacing legacy asset-presence tests with behavior checks. |

## Validation

Local full backend suite: 566 passed, 4 startup deprecation warnings.
Node execution tests cover canonical navigation, stored market semantics, evidence
sections, missing-value handling, fixed ranks, morning dedup/cap and Worker token-relay denial.
Frontend inline and external JavaScript plus both Workers are syntax checked.
Remote gates, post-merge deploy verification, visual desktop/mobile and final production
recheck must be recorded before this checkpoint can be considered complete.
