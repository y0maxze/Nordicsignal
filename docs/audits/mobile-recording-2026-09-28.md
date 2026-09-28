# Mobile recording review — 2026-09-28

User-supplied 3m53s iPhone PWA recording, device clock approximately 18:57–19:01 Oslo. Reviewed screenshots sampled throughout the recording and inspected individual frames for source/notification details. This is evidence from the owner's signed-in session, not a new interactive browser run. No audio conclusions are drawn.

| Approximate offset | Observed | Finding / action |
| --- | --- | --- |
| 28–44s | TECH lacks quote/name while Opportunity loads | Stock detail required a score row. Quote retrieval and database insertion shared one exception handler. Read-only production inspection confirmed TECH and AKOBO absent from `stocks`, plus `quotes_ticker_fkey` requiring that row. A valid provider quote was therefore discarded when persistence failed. Separate these outcomes; expose persistence status; use the existing exact issuer reconciliation for names without adding scores or universe members. |
| 52s | A `TECH · Early Opportunity` notification from NordicSignal arrives over the official NewsWeb page | Confirms one visible notification arrival only. Does not prove delivery of every event, deduplication or tap navigation. |
| 60s | Varsler says push is disabled in this version | False blanket claim. Replace with separate read-only browser permission, local subscription and server readiness states. A local subscription does not verify its server registration or receipt. |
| 68s | Editorial article `2 Cash-Producing Stocks…` labelled a dated public message | Only `official === true` earns an official label. Other items are media coverage with publisher attribution. Late news responses update the panel. |
| 76–108s | TECH company/financing view exposes missing and stale data and partial archive coverage; source opens NewsWeb | Coverage disclosures visible. Source navigation works in this instance. Missing descriptions/financials remain missing; no guessed replacement. |
| 116–140s | Light theme, Morning Brief → AKOBO, chart and insider sections | Canonical navigation works. Raw `FALLING_OR_WEAK` and narrow all-caps unavailable tile replaced with Norwegian labels. Missing benchmark remains missing. |
| 156–172s | AKSO shows loading while other sections complete | Slow independent request observed; permanent hang not established. Existing 25-second failure/retry behavior covered by a regression test; signal rules unchanged. |
| 180–220s | Market → New/IPO → Outlet Group; Brønnøysund activity, evidence history and financing limitations visible | Navigation, long-page scrolling and recorded evidence disclosures visible. Activity is explicitly distinguished from a group description. |

The production Worker deliberately denies mutating API relay requests, including `/api/push/subscribe` and `/api/push/test`, even behind the current Access boundary. This review does not remove that protection. Existing subscriptions can still receive backend dispatches; enrolment/test delivery requires a separately verified authenticated write path. The status UI must not invite a known-blocked action.

PWA cache v25 accompanies the presentation changes. UI tests exercise the actual stock/alerts scripts, including a late news response, missing data, failed Opportunity, denied permissions, unsupported browsers and server failure. Backend tests use a real SQLite foreign-key constraint and check quote retention, normal persistence, connection cleanup, registry-only reads and unchanged scored-stock output.

Not certified by this recording: desktop, complete dark-theme coverage, offline/update/install behavior, service-worker version on the device, push subscription registration, testpush, notification tap target, duplicate suppression, every financing term and external-page responsiveness. Interactive cloud-browser verification remains blocked by the previously reported Cloudflare CAPTCHA. Token rotation remains pending; no authentication or secrets changed.
