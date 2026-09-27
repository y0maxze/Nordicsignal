# Financing document evidence, slice 2

The first lifecycle slice is merged in main 456a536e0c08b3ce18f0b0a2f135cefe93c85d24. Exact tested PR head a2caeea6b2eae45a3d27327cd232b19f8b1225c6 passed all five checks. Render deploy dep-daslmjavcj2c73b0b350 is live on that main SHA, Cloudflare production workflow passed and backend health returned HTTP 200.

This slice adds a bounded background document collector (two documents per scheduler wakeup, one-day retry after failure, seven-day recheck after capture). GET handlers remain snapshot-only. The collector accepts only HTTPS official Euronext announcement URLs, rejects redirects/challenges/errors/oversized bodies, and independently checks the exact document title and issuer. Initial supported documents are English labelled key-information notices with one financing type. Unsupported documents, conflicting labels and absent fields remain explicitly unknown. No fallback to broad prose regexes.

Facts retain original wording, including qualifications, document URL/date, attempt/capture times, content hash and per-field evidence. A failed recheck retains prior facts as stale. Counts, currency and dates are not reconstructed from price/proceeds or other documents. Maximum share counts are separate from exact counts. Dilution requires exact pre-issue and new counts explicitly referring to the rights issue and an explicit shared class in the same document. It is a document scenario for a nonparticipating holder, not a completed-event claim or price-loss estimate.

Stock presentation adds historical title status, evidence, source state, a terms panel and dilution inputs/formula/limitations. No status is presented as current. Stored observations no longer disappear at 180 days; the latest 20 are shown with a visible total/truncation notice. Old snapshots are conservatively classified without provider calls. Service-worker cache advances to v15 with matching contracts.

## Validation and limitations

- 651 backend tests and 21 UI tests passed locally before final CI; compilation and diff whitespace checks passed. Tests cover hostile URLs, identity mismatch, duplicated fields, approximate/max/secondary counts, source failure retention, background request bounds, historical retention, missing data and UI injection.
- Euronext example checked: https://live.euronext.com/en/products/equities/company-news/2026-06-02-norse-atlantic-asa-updated-key-information-relating . Search-indexed official text supports labelled price/date/max-count distinctions. Direct source access in this environment returned a JavaScript verification page. No protection was bypassed. Production document acquisition is NOT certified from fixtures; blocked sources remain unavailable.
- Parser fixtures are synthetic regression examples, not a claim of full production provider coverage. PDF attachments, arbitrary prose, Norwegian term labels, multiple tranches, cross-document reconciliation and historical backfill are not implemented by this slice.
- Existing historical documents are retained; this does not recover announcements missed before monitoring or during source outages. No current issue-state inference from newest title or missing completion notices.
- Authenticated browser navigation repeatedly timed out. Mobile/desktop signed-in UX, installation/update and real Web Push delivery remain unverified. CI is not a substitute for that check.
- No score, Opportunity, High Conviction, sizing, signal threshold, push rule or secret changes.
