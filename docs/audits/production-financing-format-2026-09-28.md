# Production financing data verification

Read-only Render Postgres inspection on 2026-09-28 around 16:00 UTC confirmed live commit 9f3f4554b4dce0e7ce6318c5632092f476dbb3be, 88 financing events, 138 profiles and 255 evidence versions. Profiles were 98 partial, 33 unavailable and 7 stale. NewsWeb had queried 213 days, oldest 2026-02-28, with no unavailable or truncated windows at that observation. This remains partial coverage of a 730-day target and a strictly matched issuer universe, not proof of complete history or absence of financing risk.

All 88 event documents used parser v3: 84 unsupported titles and four partially supported documents. Two of the four had zero extracted fields. The scheduled jobs continued updating without manual production writes.

The official public NewsWeb message bodies were downloaded read-only and their SHA-256 hashes matched all four stored production captures:

- https://newsweb.oslobors.no/message/680919 (HDLY)
- https://newsweb.oslobors.no/message/676716 (HYPRO)
- https://newsweb.oslobors.no/message/682643 (TECH)
- https://newsweb.oslobors.no/message/668763 (XPLRA)

Observed defects: list markers hid exact labels; long labels wrapped across lines; approval dates were appended to record dates; preferential-rights allocation and subscription ratio shared a key and appeared ambiguous. Parser v4 fixes those formats with exact aliases, one optional bullet and a three-line label bound. Unknown colon-bearing qualifications and trailing prose remain attached. No arbitrary footer or blank-line truncation is introduced. Fields over the existing evidence length limit remain unknown, including some final price/other-information fields. No general prose or PDF extraction is claimed.

The four replays expose 7, 6, 12 and 8 fields respectively, without changing document identity or producing any dilution calculation. Expected approval has a separate UI label. All current lifecycle statuses remain unknown. Old parser output is withheld explicitly until background revalidation; prior evidence remains stored. PWA cache v24 updates the presentation.

Regression fixtures use synthetic values. Score, Opportunity, High Conviction, sizing, push and authentication rules are unchanged. Authenticated UI/PWA/push verification and token rotation remain separate unfinished tasks; deployment checks do not certify them.
