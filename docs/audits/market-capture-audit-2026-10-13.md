# Market capture audit — 13 October 2026

## Read-only production baseline

Main and live Render deployment: `e3c2e9c022cea3dcb7d81b3b8f9de65baa7d6692`.
Database and API service available. Baseline queries precede any UI-triggered news refresh.

- Public persistent news snapshot: generated 10 October 13:24:12 UTC, stored
  13:24:20 UTC; 30 items, latest publication 9 October 19:48 UTC.
- Measurement reconciliation: 13 October 07:10:29 UTC, status `ok`, no gaps,
  **zero prospective signals and zero certified entries**. This is not evidence
  of investment performance or complete market coverage.
- Capital-flow storage includes Borr and Hafnia insider announcements from
  12 October; first observations 06:40:17 and 05:39:52 UTC respectively.
- Huddly's cancellation of its subsequent offering is already in company
  context: NewsWeb message 683086, published 25 September, observed 27 September
  21:09:42 UTC, historical lifecycle `cancelled`. Do not treat the earlier
  planned October share delivery as completed.
- No 12–13 October records in `event_evidence_events` at the baseline query.
  No company-context matches for bankruptcy/decommission/ABG observed since
  12 October. These narrow queries do not prove that no transient consumer
  ever saw a story or that a push was delivered.

## External comparison

Official Euronext Oslo company-news listing on 13 October includes NEXT's
12 October 15:51 CEST decision to file for bankruptcy and DOF's 12 October
17:09 CEST contract announcement. Both are absent from the persisted public
snapshot described above. An old cache is not proof of failure in every scanner.

DOF's issuer announcement describes a USD 15–25 million North Sea
decommissioning contract, with offshore execution scheduled Q1 2027.
Inify's official calendar lists Q3 publication on 28 October 2026.
HydrogenPro's inspected issuer notice page has August results as its latest
visible entries; this alone cannot certify absence of newer announcements.

Market context, not a current quote: E24 reports Oslo's main index closed
12 October up 0.13%, with Frontline gaining over 4%. DN reports ABG Q3 revenue
of NOK 594 million on 13 October. No current intraday index level is certified
by this audit; the Euronext landing-page quote dated 9 October is stale.

Sources:

- https://live.euronext.com/en/markets/oslo/equities/company-news
- https://www.dof.com/news/dof-group-asa---awarded-subsea-decommissioning-contract-in-the-north-sea
- https://www.huddly.com/investor-relations/investor-news/huddly-as-cancellation-of-the-subsequent-offering/
- https://hydrogenpro.com/stock-exchange-notices/
- https://www.inify.com/financial-calendar/
- https://e24.no/boers-og-finans/i/Vgjzx6/nedgang-paa-oslo-boers-oljeaksjer-faller
- https://www.dn.no/bors/abg-sundal-collier/oslo-bors/inntektsloft-for-abg-omsatte-for-594-mill-kroner-i-tredje-kvartal/2-1-2057584

## Implemented correction

The existing capital-flow scanner already calls the general news collector.
Previously only the public HTTP route updated `runtime_feed_cache`, so its
timestamp could diverge from background observations. No new provider polling
or scheduler is needed.

Every actual general-news fetch now records bounded public metadata into
`market_news_observations` and source status into `market_news_capture_state`.
It also updates the existing public snapshot when usable. Failed empty fetches
record failure without overwriting the last usable snapshot. In-memory cache
hits do not manufacture captures. Storage failure is logged and does not hide
available news. First-seen is the actual observation, never publication time.

This is a prospective observation ledger, **not a complete exchange archive**:
only the existing latest-page window is ingested. Long gaps or high announcement
volume can still miss items. URL aliases are not certified as identical events.
No historical first-seen dates, alerts, ticker identities or score changes are
inferred. Existing score, Opportunity, High Conviction and push rules unchanged.

## Measurement gate and next work

Validation: 1,019 backend tests and 89 UI/Worker tests passed; `git diff --check`
passed. Six backend warnings remain, including an existing background benchmark
backfill thread reporting unavailable Yahoo OSEBX history. Passing tests do not
certify that provider. No benchmark fallback or weakened measurement gate added.

Certified opening-price requirements remain unchanged. Yahoo daily opens and
Euronext's previously inspected delayed-trade sample do not establish official
opening-auction identity, adjustment basis, instrument trading status or complete
corporate-action coverage. Automatic entries remain disabled; no net benchmark
outperformance claim is justified. New provider rights/access are not purchased.

Next: verify the new ledger after deployment against official source URLs, then
continue provider qualification and session/identity evidence. Backfill coverage
must be explicit and must not rewrite prospective observation times.
