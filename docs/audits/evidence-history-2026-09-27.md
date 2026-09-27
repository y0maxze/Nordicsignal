# Research evidence history

Append-only versions now preserve source snapshots when financial documents or company context change. Repeated collection timestamps do not create new versions. A -> B -> A creates three versions. Source and extraction-status changes are retained too, and the UI explicitly distinguishes these from factual company changes.

A correction on the same official document URL updates the current snapshot and invalidates previously extracted terms. The old snapshot is retained in the same database transaction. Concurrent document enrichment uses compare-and-swap to avoid overwriting corrections.

History is scoped to the current exact issuer identity, capped at 30 displayed versions with an explicit truncation notice, and served from storage without provider calls. The complete version payload is retained in the database. The UI shows a revision index and changed field groups; it does not yet show a full side-by-side field comparison.

Recorded time begins when version storage runs. It must not be interpreted as original public availability or used as point-in-time market research without additional provenance. Legacy documents get a baseline at actual recording time, never a backdated version. Historical state remains independent of current financing status.

No scoring, Opportunity, High Conviction, sizing, push rules, or credentials changed. PWA shell version is v17. Authenticated production browser verification remains outstanding because the available browser transport has timed out before reaching the application.
