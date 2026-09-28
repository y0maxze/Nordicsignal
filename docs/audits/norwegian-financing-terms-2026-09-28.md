# Norwegian financing key-information terms

Parser v3 adds labelled Norwegian key-information notices with exactly one financing type. It preserves source text, including decimal commas, spaces in numbers, qualifications and inconsistent source dates. Utsteder is accepted as an issuer heading; all issuer headings must still agree with the exact stored identity. NewsWeb retains its existing strict message/issuer identity checks.

Separate fields expose maximum shares, allocation ratio, subscription ratio, stated decision date, rights listing, rights ISIN, arranger, settlement agent and additional information. A stated decision date does not set lifecycle status. A promised ISIN or proposed listing remains verbatim source text, not a validated identifier or listing confirmation. Maximum counts and Norwegian number formats do not supply dilution inputs.

Official reference labels inspected on 2026-09-28:

- [Euronext notice 4.3.5.2A template](https://www.euronext.com/sites/default/files/2020-11/Notis%204.3.5.2A%20-%20Separat%20melding%20-%20N%C3%B8kkelinformasjon%20ved%20fortrinnsrettsemisjon.pdf). Used for field labels only, not current settlement rules.
- [Nordic Financials, 13 June 2025](https://live.euronext.com/nb/products/equities/company-news/2025-06-13-nordic-financials-asa-nokkelinformasjon-i-tilknytning-til). Distinct rights ratios, Norwegian decimal comma and maximum share count.
- [Aega, 2 December 2024](https://live.euronext.com/nb/products/equities/company-news/2024-12-02-aega-asa-nokkelinformasjon-i-tilknytning-til). Unannounced identifiers, conditional listing and inconsistent stated years must not be silently corrected.

Fixtures use synthetic values. Regression tests cover identity conflicts, duplicate aliases, compound titles, retained qualifications, missing data, no lifecycle inference, no dilution from maximum counts and escaped UI evidence.

This is partial coverage of labelled HTML/plain-text notices, not PDF extraction or general prose interpretation. Parser v2 snapshots remain stored but their terms/calculations are withheld in the public response pending v3 revalidation. Existing bounded background jobs perform revalidation; GET requests do not contact providers. A failed revalidation must not resurrect old parser output. PWA cache is v23.

Score, Opportunity, High Conviction, sizing, push rules and secrets are unchanged. Authenticated production checks remain incomplete: Render requires explicit workspace selection confirmation, and the available browser is blocked by Cloudflare verification. This slice does not certify production database coverage, mobile/desktop behavior, push delivery or token rotation.
