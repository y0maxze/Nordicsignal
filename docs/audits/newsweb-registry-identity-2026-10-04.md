# Documented NewsWeb identity for registry enrichment

Production inspection found 166 stored company profiles, of which 48 had a
description, 33 had registry data and 12 had financial facts. These are stored
coverage counts, not a freshness guarantee. Techstep's profile used the short name
`TECHSTEP`, while its already reconciled official NewsWeb notice dated 2026-09-17
explicitly supplied `Techstep ASA`. Yahoo verification was unavailable. The exact
Brreg lookup for Techstep ASA returned HTTP 200 and one entity, organisation
977037093. The independently sourced register data could therefore fill a gap
without guessing a suffix or relaxing issuer matching.

## Selection boundary

During background collection only, a missing Norwegian legal name may be supplied
by stored NewsWeb evidence with the same ticker and normalized issuer identity.
The existing ingestion boundary already verifies issuer, ticker and document
title prefix. Selection rechecks those bindings, the official message URL and
positive issuer/message IDs, the AS/ASA suffix, non-corrected document state, and
valid publication/observation times. Publication must be within 180 days. Older
documents remain financing history but cannot supply this fallback identity.
This is an explicit freshness limit for identity lookup, not a financing rule.

Conflicting legal names or issuer IDs fail closed. More than 500 candidate
documents reports unavailable rather than silently truncating away conflicts.
A fresh exact Brreg lookup must still pass its independent complete-result,
legal-name and legal-form checks. A registry identity conflict cannot resurrect
an older registry-derived description through failure retention. Other source
failures retain prior facts with their original capture date and stale status.

The profile retains the linking document's URL, issuer ID, publication date and
capture date. The canonical Stock page exposes the identity link separately from
Brreg's activity/source and explicitly describes ambiguous or incomplete identity
coverage. The official activity is still labelled as registered activity, which
may differ from the consolidated business. It does not authorize Yahoo financials,
invent an ISIN or establish a current financing status.

## Refresh and validation

Registry identity version 1 makes older snapshots eligible for one bounded
background revisit. The existing four-profile batch limit and 24-hour retry rule
continue after that revisit; no external provider is called by GET requests.
PWA shell cache is v29 for the new source disclosure.

796 backend tests and 45 UI/Worker tests passed locally, including the unchanged
compare-and-swap concurrent-writer protection. Four existing FastAPI deprecation
warnings and the known background test-fixture missing-table warning remain.
Tests cover source/date/identity conflicts, corrected documents, stale evidence,
missing providers, retained data, batch limits, one-time revalidation and escaped
source presentation. Production-wide complete coverage is not claimed. Missing
financials, ISINs and unsupported financing documents remain visible.

No score, Opportunity, High Conviction, sizing, automatic push rules or secrets
changed. The earlier push confirmation remains an owner-reported device test,
not certification of every background/offline or PWA installation scenario.
