# System review — 9 October 2026 (Europe/Oslo)

Scope: production health and stored-data diagnostics, source spot checks against
Nordnet and Euronext, full regression suite, authenticated desktop inspection,
and the next pending offline/update-lifecycle work. This is not a claim that
every listed security, disclosure or physical device has been validated.

## Observed production baseline

- Main/deploy baseline: `30e032a8d1af451e68c1ea15a2efb96e9390d157` (PR148).
  Render uses the intended `api_entrypoint:app` start command, not the old main
  entrypoint cited in the original V1 audit. No error-level application logs were
  returned for 00:00–15:49 UTC on 9 October. This is not proof of zero errors.
- Five 15-minute resource samples from 14:45–15:45 UTC: 0.0095–0.0172 CPU against
  0.15 CPU limit; 215–230 MB memory against 537 MB limit. HTTP latency metrics were
  unavailable, so no p95 claim is made.
- 26 active scored stocks, all latest rows marked live, created around 15:17 UTC.
  Opportunity scheduler state was fresh and triggered at 15:50 UTC. Neither
  observation certifies market-data completeness or strategy profitability.
- The registry already includes VLCC (5 October), OUTLT (24 September), OMC
  (28 August), POLAR and PLCAN. Latest registry observation: 10:57 UTC today.
- Company profiles remain incomplete: 63 partial, 76 stale, 47 unavailable in
  the diagnostic snapshot. The three reviewed financial pilots are separate
  projections, not evidence that all 186 automatic profiles are complete.
- The optional persistent news/insider hot-feed cache has September timestamps.
  This is not a current market-feed clock: canonical Morning loaded a fresh
  9 October 17:00 Oslo disclosure and was generated at 17:58 Oslo. Do not infer
  current page freshness from a dormant cache table or from retrieval time.

## Nordnet / exchange comparison

Sources consulted (retrieved 9 October; search-index dates vary):

- https://www.nordnet.no/aksjer/kurser/huddly-hdly-merk
- https://www.nordnet.no/aksjer/kurser/inify-laboratories-inify-merk
- https://www.nordnet.no/aksjer/kurser/hydrogen-pro-hypro-xosl
- https://live.euronext.com/en/ipo-showcase
- https://live.euronext.com/nl/markets/oslo/equities/company-news
- https://newsweb.oslobors.no/message/683853

Nordnet's Huddly page confirms the 25 September cancellation and the separate
4 September private-placement registration already distinguished in our pilot.
Its Q3 calendar lists 5 November, matching the reviewed snapshot. Nordnet's
historical calendar says 27 August for Q2 while its own news list dates the
results release 26 August. Original report/publication provenance stays primary;
we do not replace it with a conflicting aggregator calendar. Inify's indexed
page was older; it is not a reliable latest-calendar authority. No live quote
comparison is claimed from pages with empty or index-aged quote fields.

Euronext's recent Oslo admissions match VLCC, OUTLT and OMC in our registry.
This spot check is not a full exchange-universe reconciliation. Euronext also
lists a NEXT trading-suspension publication at 08:22 CEST on 9 October (683853).
The application has no independently verified instrument-tradability feed.
The quote's market-session field must not be mistaken for suspension/resumption
status. This release explicitly labels it as a stock-exchange session, not an
assertion that a specific security is tradable. Scores are not altered based on
an indexed headline, and no one-off historical status is presented as current.

## Fixes and next-list work

1. **Stored price provenance:** quote retrieval time was used to rank price
   freshness and could conceal an older trade. Persist `market_time` separately;
   add an idempotent, nullable SQLite/PostgreSQL migration. Never backfill old
   rows from capture time. Reject future, invalid or timezone-less trade times
   when comparing with dated daily closes. Undated fallback prices retain
   unknown trade time and no unverified daily return. Scores/signals untouched.
2. **Market transparency:** show price time in each row (not just a hover), state
   that the ranking is a selected universe rather than all Oslo-listed stocks,
   and keep partial-source warnings visible after research panels finish loading.
3. **Offline/update lifecycle:** restrict service-worker interception to the
   explicit shell allowlist and bounded non-secret query parameters. API,
   identity/Access paths, unknown URLs and credential-bearing queries bypass it.
   Require a Worker-only shell marker for HTML and correct asset MIME types.
   Never use cached content to mask an online 401 or other failed response.
   Read only the current cache version, await writes, let independent precache
   entries survive another entry failing, and remove only older Aksjer caches.
   Invalid/external/auth/API notification destinations fall back to the app.
   Cache contracts advance to v34. No Access policy or push enrollment change.

Local validation: 838 backend tests (four existing FastAPI lifecycle deprecation
warnings), 66 UI/Worker tests. New tests cover legacy migration, preservation of
trade/capture timestamps, unknown/future dates, visible mobile-readable times,
partial-source rendering and executable service-worker offline/upgrade behavior.
PR checks and independent production deployments remain release requirements.

## Remaining priorities — not concealed by this release

- Actual iPhone PWA install/update/offline and push receipt/tap/deduplication.
  Desktop browser and simulated service-worker tests do not certify iOS.
- Broader source-reviewed financial/description coverage; automated profile gaps
  above remain real. Review issuer identity, period and currency for each addition.
- Dedicated exchange trading-status coverage (halt/resumption/delisting), with
  exact issuer IDs, publication ordering, stale/unknown states and source links.
- Coordinated Worker/Render secret rotation needs both authorized endpoints;
  no one-sided rotation, access expansion or public exposure is attempted.
- 2027 Oslo calendar coverage and exceptional half-day source verification;
  unknown sessions remain unknown rather than guessed.
- Dependency-aware startup/lifespan modernization and point-in-time benchmark
  alignment remain separately gated work; no score/rule/threshold change here.
- Licence/redistribution review, verified restore and per-user isolation remain
  required before a commercial/multi-user readiness claim.
