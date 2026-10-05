# Financing field boundaries — 2026-10-05

## Observed production baseline

Main and the live Render deploy were `d07eeb5` (PR #144), with no open pull
requests. Read-only production queries found 170 company profiles, 165 using
registry identity version 1, 62 with a stored description and 50 with registry
data. These are coverage counts, not guarantees of freshness or complete company
descriptions. Techstep now has the exact Brreg organisation 977037093, linked to
NewsWeb message 682643; its registered activity is not a consolidated business
description. Financial facts remain unavailable for that profile.

The financing store contained 24 partially parsed and 262 unsupported documents.
Inspection found fields merged into preceding values, and some successfully
downloaded key-information notices with no extracted fields still labelled as
partially parsed. This does not justify treating unsupported prose as structured
terms or current offering status.

## Confirmed causes and correction

Parser v5 recognises one list marker with or without a following space, including
the middle dot used in HydrogenPro's notice. Matching still requires an exact
label and at most three wrapped lines. Explicit template aliases now separate
announcement, last inclusive trading day, ex-date, managers and rights listing.
Duplicate aliases remain ambiguous. Unknown colon-bearing conditions remain part
of the preceding value; neither numeric inputs nor text are silently truncated.

The old 700-character evidence limit discarded final fields followed by lengthy
conditions and legal text. Evidence is now bounded at 10,000 characters. Longer
values are not reduced to an unqualified price or share count. The UI folds values
over 500 characters behind a full-source-text disclosure, retaining all accepted
qualifications and escaping HTML. Documents without recognised terms have the
distinct `no_supported_terms` state and a seven-day revisit interval, consistent
with successful partial extraction rather than a failed download.

Older parser output is withheld pending the existing bounded background
revalidation. No new ingestion source, expanded scan frequency, live GET fetch,
identity relaxation, financing lifecycle inference or dilution formula is added.
PWA shell and its existing contract checks advance together to v30.

## Source-grounded replay

The existing NewsWeb message adapter fetched three actual source bodies. Their
identity metadata, dates and title bindings were checked through `adapt` and
`collect`; no production rows were manually changed.

| NewsWeb message | Ticker | v4 stored fields | v5 replay fields | Dilution |
| --- | --- | --- | --- | --- |
| 635542 | HYPRO | 0 | 7 | Unknown |
| 634721 | HDLY | 4 | 7 | Unknown |
| 634741 | INIFY | 4 | 8 | Unknown |

HYPRO and HDLY retain respectively 6,271 and 7,605 characters of price evidence,
including subsequent conditions. INIFY's price and rights-listing fields are now
distinct. Additional production examples of the manager/listing-label issue were
VOW messages 629227 and 632671. Test fixtures use synthetic values and companies.

References: `https://newsweb.oslobors.no/message/635542`,
`https://newsweb.oslobors.no/message/634721`,
`https://newsweb.oslobors.no/message/634741`.

## Verification boundaries

Targeted parser, identity and background-job tests passed (103); the full backend
suite passed (812, four existing FastAPI deprecation warnings), and UI/Worker tests
passed (47). Existing asset, navigation and PWA contracts passed. GitHub release
gates must also pass before merge.
The authenticated browser session had expired at the start of this review;
database and adapter replay checks do not substitute for logged-in visual QA.
Device background/offline/PWA scenarios and coordinated secret rotation are not
certified by this change. Signal, Opportunity, High Conviction, sizing and
automatic push rules remain unchanged.
