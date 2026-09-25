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


## Follow-up after PR #109

PR #109 passed all three gates on `5e34f23f83d8822c991c14070e8d12ab646f9dae`,
merged with expected head into `1cebea8422ed010c0d7efd9e787b614ef2aff27d`.
Main CI and Cloudflare deploy succeeded on that SHA; Render deploy
`dep-daqfr77f3r2c739b2l2g` was verified live on the same commit. Actual Stock
showed EQNR delayed quote with real market time, 26-stock ranking, research-only
ownership state and a continuous analysis. Browser console showed no application
JavaScript errors (browser-extension metadata errors excluded).

The next audit found and repairs an eager `import main` in
`early_discovery_runtime.py` that could create the FastAPI app before subsequent
runtime route wrappers were installed. The runtime now participates in the same
idempotent extra_api.install chain as the other integrations. A fresh-process
regression test requires the affected routes exactly once.

Presentation findings: undated IR landing-page links must not be called new
announcements; valuation ratios with unverified currency alignment must not be
presented as validated multiples; dividend totals need duplicate-event validation.
These values are suppressed or labelled in presentation. **The existing valuation
scoring implementation in providers.py/main.py also needs a separate point-in-time
currency audit before any production score change. No score rule was changed.**

A read-only post-deployment check now verifies actual production routes, source
HTML, research policy, API availability, personal-read protection and PWA assets.
The report is uploaded by the Cloudflare workflow. This is independent of the
three pre-merge mandatory gates. It does not certify authentication or mobile
visual behavior.

Full backend suite after startup fix: 567 passed, four startup deprecation warnings.


Additional production findings in the follow-up: Market now prefers a newer dated
price observation over an older quote; search excludes unsupported funds and foreign
instruments from the Oslo stock route; the legacy dashboard aggregation route is
protected as personal data. General news issuer cleanup now requires a unique exact
normalized company alias, preventing Kongsberg Maritime from being linked to KOG.
Private-mode authorization runs before HTTP-cache hits, covered by the real middleware
chain in a regression test.

Remaining test debt: background Opportunity market-context backfill can outlive a
SQLite monkeypatch fixture and report a missing test table in an intermittent thread
warning. Isolate/disable asynchronous research jobs in fixtures before stress-running
the suite; do not change production model behavior to suppress a test warning.

## Access activation follow-up (2026-09-24)

The owner enabled Zero Trust Free and Worker-level Access on `nordicsignal`, scope
**All traffic**, with the **Cloudflare account members** allow policy. This allows
account members, not necessarily only one person; membership must stay restricted.
An anonymous browser opening `/app` reached the tenant
`lucky-darkness-5204.cloudflareaccess.com` login page. The owner confirmed that
signing in opens the app. This supersedes the earlier Cloudflare-not-configured
finding. Direct Render reads were still public when inspected; the existing
shared secret is configured. This PR sets the documented private-mode configuration
and requires anonymous Render API reads to return 401 in production verification.
Apply the same non-secret setting to the existing Render service after the exact
PR head passes all three gates and is merged; verify its redeploy before closing
that finding. The public `/api/health` remains available for health checks.

Actual Render start command was corrected to `uvicorn api_entrypoint:app --host
0.0.0.0 --port $PORT`. Deploy `dep-daqg4u0u01pc738245jg` was verified live on
`c0b1071087cc47555c9c44fcb614470546184c15`. This supersedes the earlier entrypoint
mismatch. PR #110 passed all gates on `321e14c19777d79df63ed2be090d395fc93794b3`;
main CI passed 570 tests and Cloudflare deploy passed on the c0b1071 merge commit.

Anonymous production checks now validate the exact Access tenant redirect on pages,
assets and APIs, plus direct-backend denial. They do **not** treat a login-page 200
as app availability. Reports explicitly say authenticated content checks were not
run when no Access session is available. The previous content assertions are kept
as `run_content_checks` for an authenticated verification integration; they are not
executed by this anonymous workflow. Authenticated deployment QA remains a separate
requirement and must not be reported complete from this boundary check alone.

Remaining: authenticated browser QA after backend lockdown, mobile visual review,
Access-aware push/write enrollment, and the concrete data/startup debts above. The
Worker continues to deny browser writes and personal legacy API reads; do not relax
that containment merely because an Access configuration exists. Existing scheduler
requests use the internal secret directly and do not traverse the browser login.

## Stability and verification follow-up, 24 September 2026

PRs 111–115 are merged. Render private mode is active; anonymous API reads return
401 and the Worker requires Access. Main d36cfae was verified live on Render and
Cloudflare, with 25 anonymous boundary checks passing. This supersedes the pending
private-mode activation note above.

Owner iPhone screenshots confirm Market, Morning, stock header/rank, sample-size
presentation, compact financial cards and corrected light-mode decision contrast.
They do not certify desktop interaction, console errors or offline PWA behavior.
The cloud browser remains at Access sign-in; the owner's Safari login does not
transfer to it. Cloudflare admin sign-in previously hit an anti-bot challenge.
Do not bypass Access or request exported credentials/cookies.

Opportunity showed unavailable at 14:20 Oslo and loaded at 14:21. A Render request
log query for AKSO during 12:19–12:22 UTC returned no records: the precise incident
cause is unknown. Code inspection identified a separate reproducible race: calendar
completion could render an absent Opportunity as no action. The stock page now
preserves loading/unavailable states, requires a model label and offers explicit
retry. Execution tests cover failure, calendar rerender and successful retry.
Production model thresholds and scoring remain unchanged.

Service worker v8 rejects redirected and opaque-redirect responses in installation
and runtime caching. Previously a successful redirected Access page could enter
the shell cache. Activation clears the older cache. Tests execute install/fetch
handlers and confirm API requests are not intercepted. Fresh data is never implied
offline; actual iOS offline installation testing remains outstanding.

Remaining concrete limitations and next steps:
- Authenticated desktop/PWA checks require a working Access browser session.
- worker.js intentionally denies browser writes and push enrollment. Define and
  validate authenticated writes before enabling them; server push tests do not
  certify notification delivery to the phone.
- backend/main.py and market_coverage_runtime.py retain startup-hook deprecations;
  migrate lifespan only with startup-order regression coverage.
- frontend/stock_analysis.js hides ratios when currency alignment is unverified.
  Validate the underlying valuation methodology point-in-time before changing score.
- Benchmark excess, full daily ownership and calendar dates outside verified
  coverage remain unavailable/unknown as documented above.

The full Definition of Done is not certified while authenticated desktop/PWA and
push verification remain outstanding. Automated tests and deployment checks must
not be reported as substitutes for these checks.

## Push client regression audit — 2026-09-24

- Removed the mobile shell's legacy holdings/insider polling fallback. A saved
  alert preference no longer starts personal-data reads when opening the inbox.
- Registration now requires an HTTP success, a valid success response and
  delivery_ready=true before presenting registration as successful. Permission
  alone and a browser subscription do not prove server registration.
- Registration confirmation is intentionally session-local until a secure
  per-subscription server-status route is available. Reloading never asserts
  active push based solely on a local preference. API and service-worker waits
  are bounded. Failed tests clear the session confirmation.
- Browser write proxy remains closed. The canonical inbox still does not expose
  activation: verified Access identity, subscription ownership/endpoint safety,
  server configuration and actual phone delivery remain required before enabling
  that flow. No production scoring or notification thresholds changed.
- Regression test executes the actual client with an old stored preference,
  denied registration, unconfigured delivery and successful registration.

## Finance navigation and presentation — 2026-09-24

- Canonical Market, Morning, Stock and Alerts share finance_shell.css/js:
  neutral light/dark surfaces, compact numeric hierarchy, a sticky branded header,
  native disclosure menu, visible alerts/theme controls, persistent table density,
  and stock section links that keep the continuous analysis visible.
- Primary navigation remains Market and Morning; legacy portfolio/readiness
  routes are not added to the menu. The shell makes no API requests. Existing
  data-status, ownership limitations and research/score separation are preserved.
- finance_shell.js owns the canonical header; ui_shell.js skips its legacy
  injection on these pages. The Worker-injected old home badge is removed.
- Mobile retains a single-row two-link bottom nav, safe-area spacing, 44px
  controls and constrained grid columns. Offline assets advance to shell v9.
- Four DOM integration tests exercise actual scripts: unique navigation, Escape
  and outside-click dismissal, density persistence, both theme directions, and
  stock anchors matching actual analysis sections. All 577 backend tests passed
  with four existing startup deprecations. Visual production QA remains limited
  by the separate Cloudflare Access session; local cloud-browser preview could
  not connect. Do not equate DOM tests with a visual desktop/mobile check.

## IPO discovery workspace (September 25, 2026)

- `/app?filter=ipo` now contains upcoming plans, admissions in the last 90 Oslo
  calendar days, and admissions in the current Oslo year, independent of the scored
  universe. Menu shortcut and canonical stock context share the same presentation.
- Read-only `/api/ipo-radar/discovery` uses three bounded DB queries, separate short
  connections and partial-source reporting. No provider calls, writes, per-company
  requests, score changes or notification threshold changes on this path.
- Euronext's public Oslo IPO table was fetched successfully (HTTP 200, 20 parsed
  rows on page 1). Existing six-hour scheduled registry ingestion is retained.
  Empty/challenge HTML now reports unavailable instead of claiming successful sync.
- Upcoming plans must have an official archived payload, allowlisted Euronext HTTPS
  source, explicit pre-listing language and a publication within 90 days. Past
  expected dates, known completions, cancellation/postponement/transfer/bond and
  subsequent-share language are excluded. This is deliberately incomplete coverage,
  not a claim that no other upcoming companies exist.
- Registry admissions are not asserted to be first-ever IPOs. Operation type remains
  unknown when unproven; the UI warns about transfers/new share classes. An analysis
  link appears only for an active tracked ticker; untracked companies retain their
  source link and discovery card without fabricated score/financial information.
- Cards explain the documented reason to follow the listing process, conditional
  next date, risks, source observation/publication and missing diligence. Business,
  sector, valuation, profitability, debt, use of proceeds and lock-up are unknown
  until sourced. No automatic attractive-investment rating is introduced.
- `backend/ipo_evidence_runtime.py`: existing benchmark measurement advances by row
  count independently and can have differing stock/benchmark exit dates; first
  available close need not equal listing-day close. Raw closes are not a verified
  corporate-action-adjusted total return. Existing outcomes are therefore NOT exposed
  by discovery as validated 5/20/60-day or excess returns. Next action: version the
  methodology, align exact dates, verify splits/closed sessions and recompute into
  new evidence records. Risk: misleading performance if old data is presented as
  validated. Existing production scoring is untouched.
- `backend/ipo_prelisting_profile_runtime.py`: legacy provider values are labelled NOK
  without currency confirmation; EV omits cash and document extraction is not a
  complete diligence review. This endpoint is deliberately not used by the new cards.
  Next action: point-in-time, currency/period/issuer verified financial facts before
  exposing valuations. Risk: false multiples if reused unchanged.
- Service worker v10 adds discovery assets; API responses remain uncached and Access
  redirects are not cached. Authenticated visual/phone testing remains unverified.


## 2026-09-25 — secondary shell and mobile scrolling audit

The reported defect is the entire navigation covering content during scrolling. Mobile now uses separate header, scroll-content and navigation grid rows within the dynamic viewport. Navigation is outside the scroll area, with safe-area padding and keyboard-focusable content. This requires authenticated iPhone scroll verification; DOM contracts do not establish Safari visual correctness.

Worker secondary routes now share the finance shell. Retired mobile_learning_nav, alert_nav_ui and alert_local_capture injections were removed: they appended an extra navigation row, floating alert control and unnecessary blocked API polling. The cached learning-navigation script is inert. Capital Flow light-theme ownership metrics use theme surfaces, missing numbers remain unknown, source URLs accept HTTPS only, timestamps use Oslo time and old requests cannot overwrite new selections. Its refresh control performs a read rather than requesting a protected backend refresh. Worker refresh protection covers alternate true boolean spellings accepted by the backend. Shell cache is v11. No scoring or signal policy changed.

### Performance evidence — no validated Oslo outperformance claim

Insider Confluence Backtest artifact 10844262496 from run 36087881243 reports `inconclusive_insufficient_publication_history`: only 3 evaluated cluster events. Raw 5D stock return: N=3, mean +0.997%, median +0.617%; 20D: N=1, -8.211%; 60D: N=0. All stronger confluence cohorts contain zero events. These are not benchmark excess returns or a validated whole-system portfolio record. Passing CI verifies execution/contracts, not investment performance.

Concrete remaining methodological debt: `backend/opportunity_benchmark_evidence_runtime.py` independently selects benchmark dates and advances by row count without checking the own-return target_date. `backend/opportunity_tracking_runtime.py` settles own returns separately. Mismatched trading dates or entry conventions can bias apparent excess; require matched actual start/end sessions and prices, versioned re-settlement and out-of-sample validation before claiming alpha. IPO benchmark evidence needs the same alignment audit before presentation. Never relabel ordinary stock returns as excess.

Other remaining debt: `backend/main.py` and `backend/market_coverage_runtime.py` startup decorators emit FastAPI deprecations. Migrate only with explicit startup-order and scheduler lifecycle coverage. Authenticated browser scrolling, push and offline/install lifecycle remain unverified in this environment. Historical internal pages may retain old read-refresh controls; they must not be made writable to accommodate legacy presentation.
