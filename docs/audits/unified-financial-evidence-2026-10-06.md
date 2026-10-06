# Unified financial evidence — 2026-10-06

## Production evidence and cause

Read-only production inspection confirms parser v5 has refreshed HYPRO message
635542, HDLY message 634721 and INIFY message 634741. They contain respectively
7, 7 and 8 documented fields. The first two preserve 6,271 and 7,605 characters
of price evidence, including qualifications. INIFY's rights-listing field remains
separate from its price. Dilution remains unknown for all three: these documents
do not establish a current offering state or a complete dilution denominator.

The stored profile sample contained 171 profiles, 63 descriptions and 12 profiles
with financial facts. These are coverage counts, not freshness guarantees.

The stock page previously combined the identity-checked cached company profile
with an independent research response. The latter flattened statement facts and
did not display each fact's reporting period or currency. This could show amounts
below a company panel that correctly reported missing verified financial facts.

## Correction

Both panels now consume the same company-context response and share its financial
renderer. Amounts require verified provider identity and finite numeric values.
Each fact retains its period, period type and currency, including explicit unknown
values; source timestamps and stale status appear in both panels. Empty data,
failed requests, redirects, wrong tickers and late responses are handled
consistently. Ratios remain unknown without the necessary comparable inputs.

The existing bounded profile job also projects annual EBITDA with its own period
and currency. There is no additional provider request or identity fallback.
PWA assets and existing contracts advance together to v31.

## Validation and scope

Local checks: 813 backend tests and 53 UI/Worker tests passed. The six new UI tests
cover shared snapshots, unverified identity, stale data, unknown currencies,
failure/redirect handling, wrong issuers, response races and escaping. Existing
navigation/theme/PWA checks also pass. GitHub release gates and live deployment
verification are required before release completion.

This corrects presentation and provenance; missing financial coverage still needs
verified source data. Provider research, signals, Opportunity, High Conviction,
sizing and automatic push rules are unchanged. Actual device installation,
offline/background behaviour and coordinated secret rotation are separate checks;
they must not be claimed from these automated tests.
