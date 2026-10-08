# Reviewed company research — 2026-10-08 UTC

The first source-reviewed company pilot covers HydrogenPro (HYPRO), Huddly (HDLY)
and Inify Laboratories (INIFY). It addresses missing financial coverage without
making arbitrary PDF extraction or ticker-only joins authoritative.

## Evidence and maintenance

`backend/data/company_reviewed_research.json` retains source URLs, publication
and review dates, PDF SHA-256 hashes and page/section locators. Financial statement
pages were visually checked against the original annual 2025 and interim Q2/H1
2026 reports. Quarterly and half-year figures are unaudited. All comparisons use
the same report's consolidated statement and the same unit and period duration.
Huddly cash comparatives follow the interim report's presentation. Inify accounts
remain SEK. Values are not converted, annualized, added to later financing, or
used to estimate present cash, runway, dilution or valuation multiples.

The versioned research is maintained through source review and PRs. It is not an
automatic report-extraction feed. On GET, a local read-only projection requires
exact ticker and normalized issuer name plus corroborating ISIN or an unambiguous
NewsWeb issuer ID. Conflicting IDs fail closed. Production read-only inspection
confirmed IDs 12809, 12850 and 12973 respectively; HYPRO and INIFY also have matching
stored ISINs. No claim of exhaustive historical source coverage is made.

Snapshots cannot appear before review time. The UI requests another review after
35 days, a newer stored financing publication, or an observed correction to a
reviewed NewsWeb source. These are bounded stored-evidence checks, not complete
monitoring of every publisher. Past calendar dates are explicitly marked passed
using the Oslo date. Updates should increment the snapshot revision and preserve
publication dates and source locators in Git history.

## User-visible changes

- A summary near the top of the stock page covers business, documented report
  developments, risks and the next reviewed calendar date.
- The financial section separates quarter, half-year, balance and annual figures.
  Tables show comparable periods, currency and absolute changes, including losses.
- Financing timelines group only explicitly reviewed relationships. Private and
  subsequent offerings remain separate: Huddly's September cancellation does not
  cancel its registered August private placement. Inify's registration is not
  presented as evidence of later payment/delivery; HydrogenPro's final allocation
  notice retains its payment/registration conditions.
- The full existing document archive, pagination and evidence history remain
  available below the reviewed transactions. Generic provider rendering remains
  for companies outside the pilot.
- Registry activity is now a fallback and cannot overwrite a verified business
  description; an older verified description keeps its stale provenance on failure.
- PWA cache and existing version contracts advance from v31 to v32.

## Validation and release boundaries

834 backend tests passed from the CI working directory (`backend`); 57 UI/Worker
tests passed. All 15 inline scripts passed syntax checks. New coverage exercises
identity conflicts, invalid/future provenance, period compatibility, finite units,
source corrections, calendar expiry, rendering, response races and failure cleanup.
Source facts were checked against the original statements; tests are not a
substitute for report review.

The pilot changes read-only research presentation. Scores, Opportunity, High
Conviction, sizing, model inputs, automatic push and authentication rules are not
changed. GitHub gates and both independent deployments require verification.
The browser currently reaches the Cloudflare Access sign-in page, so authenticated
visual QA and actual mobile/offline behavior remain unverified in this round.
Coordinated credential rotation remains a separate access-dependent task.
