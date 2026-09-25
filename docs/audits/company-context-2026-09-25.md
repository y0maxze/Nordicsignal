# Automatic company context and financing documents

Replaces manual-only coverage with background enrichment of every active stock and Oslo listing with an unambiguous issuer identity. New rows are enrolled on the next existing IPO/Opportunity scheduler wakeup. Four profiles per wakeup, oldest/unattempted first; 24-hour per-issuer retry interval. No per-row browser fetch, no provider work in GET, no score or alert writes. Upcoming issuers without a verified admitted ticker remain unknown; Yahoo symbols are not fabricated for them.

Snapshots store attempted/captured times separately. Total source failure preserves older facts marked stale. Annual figures retain individual reporting dates and currency; no currency conversion, valuation multiples or cash-runway estimates. Description requires an exact normalized Yahoo issuer and Oslo symbol. Missing sources stay missing.

One shared official Euronext latest-feed scan flags explicit financing-document titles. Exact unique issuer-name matching, HTTPS Euronext sources and dated nonfuture releases are required. Stored flags retain observation time and original release date. This is a document watchlist, not a verified active-issue lifecycle. Cancellations and completions remain visible as documents. No inference of an acute cash emergency, no automatic dilution percentage, no investment recommendation. The current observation projection is NOT a point-in-time backtest dataset.

## Validation

589 backend tests and 18 UI tests passed before final route-contract update; full suite rerun in required CI. Additional cases exercise automatic enrolment, symbol/name mismatch, ambiguous issuer exclusion, stale retention, unknown currency, future data, title false positives, hostile source links and fetch failure. Canonical Stock and IPO cards share presentation; service worker shell v14 includes the asset.

## Known coverage limitations / next work

- `backend/company_context.py`: quoteSummary descriptions can be unavailable or fail strict name matching. Financial facts may still be partial. Add vetted issuer/ISIN sources and source-specific adapters before relaxing identity checks.
- `backend/company_context.py`: latest exchange feed is not a historical corporate-actions feed; events before monitoring starts or between outages can be absent. UI explicitly rejects “no hits = no risk”. Add a licensed or verified paginated issuer archive and reconciled issue lifecycle before claiming complete financing monitoring.
- Capital use, shareholder sales, exact lock-up dates and offering rights need issuer documents; this release does not pretend to extract them reliably from short titles. The prior reviewed Pelican document remains supplementary.
- Background work uses an in-process daemon guarded per process. A process restart may interrupt a batch; next scheduler wakeup retries. For horizontal scaling use a DB lease/queue. Four-per-wakeup initial enrichment is gradual, not instantaneous.
- Source calls inherit Yahoo timeouts/host fallback. This is separate from HTTP rendering and core scan; stalled providers can delay only the next enrichment batch.
- No new push alerts or threshold changes. Worker Access boundary can be verified anonymously, but authenticated production content still requires a signed-in browser. Do not infer successful content rendering from a login page.
