# Visual system review — 10 October 2026

Baseline: main `86cc43f2f5fa0278cdefd376a9bfadb7917d4e06`.
Production inspected through the authenticated browser. This is a desktop browser review; it does not certify physical iPhone installation, offline recovery, or received push notifications.

## Surfaces inspected

| Surface | Observed state / action | Outcome and change |
|---|---|---|
| Home | Opening screen and market entry | Clear entry point |
| Market | 26 covered stocks, sorting, Early, Opportunity, owner/insider, empty search | Empty filters are explicit; sorting caption now follows selected sort |
| IPO | Upcoming (0), recently listed (3), annual count (21) | Partial coverage disclosed; remove market-table styling from the IPO workspace |
| Morning | Calendar and fresh issuer items with original sources | Readable source and time context |
| Results | Signal type, horizon, disclosures, quality anchor, theme | Raw diagnostics remain separate from prospective measurement |
| Alerts | Feed, permission/subscription/server status | Blocked browser permission previously still offered activation; now disabled with recovery instructions |
| Stock: DVD | Quote, current status, timeline, capital flow, dividends, chart, historical evidence | Fix misleading “since last” label, missing Capital Flow source/date, and unsupported point-in-time certainty |
| Stock: HYPRO / HDLY / INIFY | Reviewed quarterly financial tables and original report links | Correct comparable periods; NOK/NOK/SEK retained; unsupported valuation remains unknown |
| News | General feed and automatic overview | Fix white-on-white text; identify rule-based selection and avoid asserting a full report from its title |
| Calendar | Default failure, then successful market filter (5 events) | Remove retired private-holdings default; show public events and explicitly incomplete coverage |
| Capital Flow | Loaded counts and ownership unavailable state | Retain unavailable ownership; improve primary-button contrast |
| Insider | Loaded market cards and detailed disclosures | Fix unreadable cards/filters; retain source link on narrow layouts; disclose extraction uncertainty |
| History | LSG, 1 month, 22 observations | Remove mixed dark/light gradient; analysis link now follows ticker; null prices are not zero |
| Intelligence / Instrument | Search entry; no selected symbol | Empty instrument no longer stays on “Loading”; provide an actionable search link |
| Readiness | Empty search state | Readable initial state; no model recomputation requested |
| Research | Model, pipeline health, locked sandbox and shadow sections | Fix dark panels in light mode; label stored outcomes as research, not confirmed net performance |
| Legal / unknown route | Risk text and 404 navigation | Legal contrast fixed; 404 offers recovery links |

The shared menu now exposes the existing secondary tools. Secondary pages no longer falsely select Market as their current page. Market-only grid CSS is scoped to its table. Theme aliases and hardcoded legacy surfaces now use foreground/background pairs in both themes.

## Next priority completed: reviewed corporate-action context

Added a versioned, read-only evidence projection for selected cash dividends. The first reviewed event is DVD (ISIN NO0010955917): NOK 20.60 per share, approved 7 October, ex-date 8 October, record date 9 October, expected payment around 16 October 2026. Payment remains unconfirmed and conditional on registration of the interim balance. The name-change resolution is recorded as context; effective registration is not certified.

Primary evidence:
- [Issuer EGM minutes, pages 2–3, item 6](https://www.deepvaluedriller.no/wp-content/uploads/2026/10/Deep-Value-Driller-AS-Minutes-of-EGM-7-October-2026-incl.-appendices.pdf)
- [Issuer publication page](https://www.deepvaluedriller.no/deep-value-driller-as-minutes-of-egm-7-october-2026-incl-appendices/)
- [Euronext instrument identity](https://live.euronext.com/en/product/equities/NO0010955917-XOSL)

Validation rejects malformed identifiers, dates, amounts, unsafe links, future review timestamps and conflicting revisions. Source publication, effective date and review time are separate. Results receive retrospective context only when the ex-date falls after the stored entry date and on/before the outcome date. The old record has no certified historical instrument identity, so the association is explicitly ticker context. Neither prices, stored returns, model rules nor history are rewritten. Missing events never imply complete coverage. The projection cannot authorize accounting or simulated execution.

## Verification

- Browser review above reproduces concrete defects before editing.
- Frontend/Worker: 86 tests pass, including new public-calendar, blocked-permission, safe-source, dated-history, empty-instrument, null-price, Capital Flow mapping and corporate-action regressions.
- Backend: all 1,004 tests passed in required CI on the merged change. Frontend/Worker and backend together: 1,090 passing tests.
- Edited inline scripts parse; `git diff --check` passes.
- Deployment and post-deployment visual verification are recorded with the PR and task result.

## Remaining evidence gaps

- No certified opening-price feed / complete corporate-action coverage; prospective entries stay blocked. No documented net outperformance claim.
- A single reviewed dividend is a pilot, not complete dividend/split/name-change history.
- Research pipeline shows degraded subsystems and incomplete source coverage; making those warnings readable does not resolve them.
- Machine-extracted insider actor names can contain source narrative. Original disclosures remain available; this presentation change does not alter the frozen insider model.
- Physical iPhone PWA/push receipt, restore drill, and effective security-identity histories require their own evidence.

## Production follow-up

PR #157 deployed successfully to Cloudflare and Render (merge `ebe776e4d3cf84ba0bde5f7f134eab400ee9fa83`; Render deployment `dep-db4t95gae00c739500g0`). Live checks confirmed the public calendar, blocked-notification recovery, dated stock history, original Capital Flow source, reviewed DVD context and empty-instrument state.

The post-deployment screenshots revealed two remaining color issues: a pale Insider label in light-mode news and positive-green research pills for non-passing states. A final presentation-only correction uses paired theme colors for the label and warning color for incomplete/non-passing research states, leaving their recorded status unchanged. News separators now use the shared border token. Cache generation advances to v37.
