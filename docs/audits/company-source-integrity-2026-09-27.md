# Company source integrity and registry activity

Adds Brønnøysundregistrene Enhetsregisteret open-data v2 as an official source for registered activity, full legal company name, organisation number and NACE industry. API reference: https://data.brreg.no/enhetsregisteret/api/dokumentasjon/no/index.html . Attribution and NLOD 2.0 are retained. No personal/contact/role fields are collected.

Matching requires a provided full Norwegian AS/ASA legal name. No suffix is guessed for a shortened stock name or foreign parent. The bounded contiguous-name search must be complete (one page, matching counts) and have exactly one exact legal-name match. Deleted entities and legal-form mismatches are rejected. A Yahoo legal name is usable only after the existing symbol and issuer-name check; an official-news registry legal name may independently supply the legal name. Conflicting legal identities in the local universe are excluded.

Registered activity is labelled explicitly: it can differ from the consolidated group's operating description and is not a freshly researched investment narrative. It has its own source and captured/attempted times, independent of Yahoo financial facts. A live read of Techstep ASA returned HTTP 200, one exact entity, organisation 977037093 and registered activity through the documented v2 API.

Corrects the previous financials identity gap: a matching ticker alone no longer admits financials when Yahoo's issuer-name verification fails. Legacy financial snapshots without identity-verification evidence are withheld until a verified refresh. Partial source failures retain previously verified fields separately with their original captured time and a stale marker. Existing IPO-registry ISINs are preserved when unambiguous and carry source/listing date; conflicting ISINs stay unknown.

Background enrichment remains four profiles per scheduled batch; GET handlers remain snapshot-only. No changes to score, Opportunity, High Conviction, sizing, signal thresholds, push or secrets. PWA cache v16.

Limitations: this adapter does not infer a shortened legal name, resolve foreign parents through Norwegian subsidiaries, invent an ISIN, or provide audited financial statements. Complete historical financing backfill and cross-document transaction reconciliation still need a reliably accessible official source. Euronext direct requests encountered verification pages in this session. Production browser navigation timed out, so signed-in desktop/mobile and actual push/PWA behavior remain pending.
