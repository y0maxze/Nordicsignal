# Company research overview

Canonical Stock now opens its company section with a compact two-column overview (one column on narrow screens). It identifies the newest published document in the stored issuer-scoped data, preserves the original source link, and explicitly lists missing identity, financial and financing information. No current transaction status, risk score or recommendation is inferred.

A local per-issuer revision cursor shows newly stored versions since the last successful rendered visit. This is limited to the 30-version history window, not a full account-wide activity stream. Different issuers sharing a ticker cannot inherit the same cursor. Failed history retrieval does not advance it; unavailable browser storage does not hide company facts. Revision changes include source/interpretation/status changes and are not signals or financial materiality assessments.

PWA shell version v18. The existing shared theme variables and responsive layout serve both mobile and desktop. DOM tests cover missing-data language, identity scoping, revision counting, failed history and blocked local storage. Actual authenticated browser, installed-PWA and push delivery checks remain outstanding; DOM checks do not substitute for these.

The history now opens an individual archived version on demand through an issuer-scoped, snapshot-only endpoint. Archived financing terms and profile facts remain inspectable even if the original web page has changed. Historical profile views withhold unverified legacy financials. This is a stored extraction snapshot, not a preserved full copy of the publisher's web page.
