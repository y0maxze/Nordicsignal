# Authenticated pilot review and report list — 2026-10-09 Oslo

After the user completed Cloudflare Access sign-in, the published HYPRO, HDLY
and INIFY pilot pages were inspected in the authenticated desktop browser.
The summaries, original-report financial tables and separate financing timelines
rendered successfully. HydrogenPro and Inify balance and annual disclosures were
expanded and checked, including Inify's SEK currency and dated balances.
Huddly's registered private placement remained separate from its cancelled
subsequent offering.

The review exposed a presentation inconsistency: the Reports section showed no
results even though the financial tables used reviewed annual and interim PDFs.
This patch reuses those exact, deduplicated source links and publication dates in
Reports, including the existing review date and stale-review notice. It makes no
additional request. The independent automatic report feed has its own container
and scoped empty/error wording, so late responses cannot erase reviewed sources.
Failed or superseded company requests cannot leave stale report links behind.

Local validation: 58 UI/Worker tests, including real stock-page feed races and
success/empty/failure states; 16 PWA/theme/navigation contract tests; 15 inline
JavaScript syntax checks. PWA cache and version contracts advance to v33.
Remote PR gates, deployments and post-release report visibility are checked as
part of release. The earlier audit's Access sign-in block is now resolved.

No source facts, score/model inputs, Opportunity, High Conviction, sizing,
automatic push or authentication rules changed. Actual-device mobile/offline
behavior and coordinated credential rotation remain outside this browser review.
