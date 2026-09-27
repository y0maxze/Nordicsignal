# Durable financing document jobs

The existing authenticated scheduler remains the wakeup mechanism. Document attempts now have durable database leases, attempt counts, states and completion times. Only the lease holder may publish a result, and publication still requires the original event snapshot to match. Expired leases are recoverable by a later wakeup. Interrupted workers cannot overwrite a replacement worker or a corrected announcement.

Successful partial document captures are revisited after seven days; unavailable/stale sources retry after one day while retaining previous same-document evidence. Parser-version changes are eligible immediately. Unsupported document formats remain explicitly unsupported. At most four jobs can run per batch (default two); no provider calls are added to GET routes.

State counts are exposed in the protected system-health response, without credentials or document bodies. The next-attempt field is an operational projection; eligibility is derived from durable document snapshots so document corrections and parser-version changes cannot be blocked by a stale job schedule. This uses the existing Postgres/SQLite layer rather than introducing another infrastructure dependency.

Tests cover lease exclusion, process-loss recovery, expired results, source correction during fetch, stale retention and retry timing. Frozen model and push rules remain unchanged.
