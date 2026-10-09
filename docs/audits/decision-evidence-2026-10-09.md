# Frozen decision evidence and opening-data review — 9 October 2026

New prospective captures atomically retain the exact source object already used
for the signal hash. Evidence is inserted only with a new measurement signal;
retries and initialization never reconstruct missing historical evidence. This
preserves the current availability boundary, model identity and frozen policy.

The read-only results response verifies the stored snapshot against the signal
hash and exposes a bounded allowlist: model reasons, Opportunity score, reversal
score, volume ratio and insider components. It does not return the raw payload.
Missing snapshots, malformed payloads and integrity failures remain explicit.
The results UI distinguishes the original analysis time from capture availability,
translates known model reasons and escapes all source text. Newer source analysis
cannot rewrite the displayed snapshot. This is application-level append-only
storage and an integrity check, not externally signed or tamper-proof archival.

No model weights, thresholds, signal selection, sizing, alerts, entries, costs or
performance calculations change. Existing records without snapshots stay missing.
The first real new capture after deployment is still required to verify natural
production evidence; synthetic records must not be added to the live journal.

Validation: 922 backend tests and 77 frontend/Worker tests passed locally. Tests
cover source revision, atomic rollback, retry without backfill, snapshot damage,
malformed data, bounded projection, missing numeric values and HTML escaping.

## Primary-source data review

Euronext NextHistory Cash specification v2.2.4 (10 April 2026) covers Oslo and
provides calendar, identity, dividend, adjustment and trading datasets. Its EOD
field 5.10 describes the first trade price of the day. That definition alone does
not certify an opening auction or its execution timestamp. A daily first price
must therefore not be relabelled as our frozen official-session-open observation.

Euronext's Oslo equity market data product includes opening/closing messages and
prices, separately from the Continental package. Web Services offers API access
including historical and reference data. Public product descriptions do not
establish our account access, licensing, field semantics or complete instrument
session coverage. No subscription was purchased and no provider was contacted.

Sources reviewed:
- https://connect2.euronext.com/en/data/client-specifications
- https://connect2.euronext.com/sites/default/files/documentation/clearing/nexthistory-cash-client-specification-v22410042026.pdf
- https://www.euronext.com/en/products-services/euronext-real-time-data
- https://www.euronext.com/en/data/how-access-market-data/web-services

Next adapter acceptance requires actual permitted sample data plus documented
ISIN/currency/venue identity, auction/open semantics and timestamp, adjustment
basis, calendar completeness, suspensions, corrections and revision provenance.
Until those pass, candidates remain quarantined and automatic entries disabled.
Corporate-action accounting, comparable benchmark returns and net costs follow.
