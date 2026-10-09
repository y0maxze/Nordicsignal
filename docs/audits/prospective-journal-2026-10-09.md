# Prospective measurement journal — foundation

Starts a separate prospective series without reviving the retired Paper Trading
product. No broker, order, score, sizing or push-rule changes.

## Shipped scope

Three new measurement tables initialized at provider-free API startup. Series
start time and SHA-256 policy fingerprint are insert-once. Changing policy under
the same identifier fails instead of mixing rules. Capture only versioned events
created after series start. Store label, ticker, model identity, original times,
conservative capture availability and source hash. Never backfill old signals or
rewrite legacy returns. Capture failures are logged without blocking signals.

Version stamping selects the unique ticker/event key of the emitted event rather
than the latest event for a ticker. Both transitions and first observations are
covered. Frozen rule functions and fingerprint inputs remain unchanged.

Results exposes series start, captured count, simulated-entry count and at most 20
recent identities. Missing journal state stays unavailable. GET remains read-only;
there is no new HTTP write route or permission expansion.

## Entry contract: implemented/tested, provider adapter NOT connected

Frozen research rule: next verified exchange session opening strictly after
capture. Capture at or after opening waits for the next session. This is a
simulation convention, not a claim of executable fills or earliest possible tick.

Adapter must provide a complete authoritative session calendar covering signal
availability through evaluation, source/version, exact opens and exchange-local
dates; ISIN/provider symbol/currency/exchange; unadjusted official open with market
time, retrieval time, source and revision. Only XOSL supported. This validator
cannot independently prove upstream source/completeness assertions.

No guessed weekday calendar, no conversion of existing Yahoo closes into opens.
Missing first eligible open waits rather than using a later price. Naive/future
times, nonfinite/nonpositive prices, ambiguous observations, wrong identity or
adjusted prices fail closed. Entries preserve decimal price text and full evidence.
Retries are idempotent; conflicting revisions cannot overwrite prior evidence.
Concurrent insert requires retry. Internal functions only, no write API.

## Tests and next dependencies

Tests cover historical preservation, prospective-only capture, frozen policy,
source conflicts, weekends, exact-open boundaries, timezone/DST, missing bars,
invalid prices/timestamps/identity, calendar ambiguity, immutable entry persistence,
exact-key attribution and real first-observed capture through version stamping.
UI tests distinguish collection from performance and escape provenance strings.

Remaining: verified calendar/instrument/open provider adapter; capture-gap and
conservative reconciliation monitoring; corporate-action ledger; comparable
stock/index return bases and dates; frozen cost/exposure rules; portfolio equity,
drawdown and independent forward evaluation. No exits, costs, positions, net
performance or outperformance claim in this release. No fabricated sample signals;
first production capture awaits a real qualifying event after deployment.
