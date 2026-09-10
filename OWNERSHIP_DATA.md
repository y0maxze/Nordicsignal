# NordicSignal ownership data policy

NordicSignal keeps ownership observations separate from the investment score until point-in-time outcomes justify a model change.

## Supported source classes

### Euronext Securities Oslo — Top Shareholder Information / Top Shareholder Changes

Preferred daily source. These are official shareholder-register data products. The runtime is adapter-ready, but a licensed feed must be connected before NordicSignal may claim daily top-holder coverage.

### Skatteetaten — Aksjonærregisteret

Official public annual snapshot source. It is useful for long-horizon ownership history, but it is not a daily ownership feed and must never be presented as current daily positioning.

### Euronext / NewsWeb disclosures

Flagging and primary-insider disclosures remain event evidence in Capital Flow Radar. They can be timely and official but do not represent a complete shareholder register.

### Media / public reports

These remain `reported` context. They are never silently promoted to verified ownership positions.

## Snapshot contract

`backend/ownership_snapshot_runtime.py` stores provider, ticker, as-of date, holder identity, shares, percentage, rank and source reference. Each later snapshot is compared only with a prior snapshot from the same provider. Deltas are classified as `ENTERED`, `EXITED`, `INCREASED`, `DECREASED` or `UNCHANGED`.

Read endpoints:

- `GET /api/ownership/status`
- `GET /api/ownership/{ticker}`

There is intentionally no public unauthenticated ingestion endpoint. Provider adapters call the runtime ingestion function from trusted server-side jobs.

## Model policy

Ownership snapshots, Capital Flow events and reported institutional context currently have **no effect** on NordicSignal score, Opportunity, High Conviction activation, thresholds or position sizing. Evidence must be collected forward before any such change is considered.
