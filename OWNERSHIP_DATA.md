# NordicSignal ownership data policy

NordicSignal keeps ownership observations separate from the investment score until point-in-time outcomes justify a model change.

## Source matrix

| Source | Authority | Cadence / scope | Machine use in NordicSignal | Current state |
| --- | --- | --- | --- | --- |
| Euronext Securities Oslo — Top Shareholder Information | Official shareholder register | Daily, previous banking day; ranked top holders | Licensed structured/SFTP adapter | Adapter-ready, **not connected** |
| Euronext Securities Oslo — Organisational Shareholders | Official shareholder register | Daily, previous banking day; full-depth organisational owners, private individuals filtered | Licensed CSV/SFTP adapter | Adapter-ready, **not connected** |
| Euronext Securities Oslo — Top Shareholder Changes | Official shareholder register | Daily changes among the largest holders | Licensed structured feed; future verified event adapter | Not connected |
| Euronext Securities Oslo — Public Shareholder Portal | Official shareholder register | Latest available register per company; interactive lookup, no historical series | Human verification only unless Euronext provides/authorizes a documented machine interface | Free portal, **not an automated market-wide feed** |
| Skatteetaten — Aksjonærregisteret | Official annual register | Annual historical ownership snapshot | Annual import adapter | Adapter-ready, not connected |
| Euronext / NewsWeb disclosures | Official exchange disclosure | Event-driven | Capital Flow / insider / flagging evidence | Active where implemented |
| Media / public reports | Reported context | Event-driven | Context only | Never promoted to verified holdings data |

Official product references:

- Top Shareholder Information: https://www.euronext.com/en/products-services/top-shareholder-information
- Top Shareholder Changes: https://www.euronext.com/en/products-services/top-shareholder-changes
- Organisational Shareholders: https://www.euronext.com/en/products-services/organisational-shareholders
- Public Shareholder Portal: https://www.euronext.com/en/csd/oslo/data-services/public-shareholder-portal
- Skatteetaten Aksjonærregisteret: https://www.skatteetaten.no/deling/aksjonarregisteret/

## Daily-source policy

### Euronext Securities Oslo — Top Shareholder Information

This is an official daily shareholder-register product and a preferred ranked-holder source. It is professional/licensed data. NordicSignal must not claim daily Top Shareholder coverage until the actual delivery and credentials are connected and verified.

A ranked list has an observation boundary. A holder disappearing from a top-20/top-200 snapshot means the holder left the **observed scope**, not necessarily that the holder sold the full position. Adapter scopes therefore form part of the provider identity and different depths must never be diffed against each other.

### Euronext Securities Oslo — Organisational Shareholders

This official product provides daily structured ownership for organisational holders with no depth limit while private individuals are filtered out. It is especially relevant to institutional/smart-capital research, but it is still licensed professional data and is not currently connected.

### Euronext Securities Oslo — Top Shareholder Changes

This is an official daily changes product. It is suitable for a future verified ownership-event adapter, but it should not be treated as a substitute for a complete point-in-time snapshot when reconstructing the full holder base.

### Euronext Securities Oslo — Public Shareholder Portal

The free portal is useful for current human verification of an individual company. It does not provide NordicSignal with a documented automated market-wide historical feed. NordicSignal therefore does not scrape it or present it as daily machine coverage.

### Skatteetaten — Aksjonærregisteret

This is an official public annual ownership source. It is useful for long-horizon ownership history and baseline research, but it is not a daily ownership feed and must never be presented as current daily positioning.

## Snapshot contract

`backend/ownership_snapshot_runtime.py` stores provider, ticker, as-of date, holder identity, shares, percentage, rank and source reference. Each later snapshot is compared only with a prior snapshot from the same provider identity.

The first snapshot is a baseline, not evidence that every visible holder bought that day. Later deltas are classified as `ENTERED`, `EXITED`, `INCREASED`, `DECREASED` or `UNCHANGED`; for depth-limited feeds, `ENTERED`/`EXITED` describe entrance/exit from the observed snapshot scope and must not be interpreted as proof of a full position opening/closing.

Read endpoints:

- `GET /api/ownership/status`
- `GET /api/ownership/{ticker}`

There is intentionally no public unauthenticated ingestion endpoint.

## Feed-adapter contract

`backend/ownership_feed_adapters.py` is the server-side normalization boundary for future authorized files.

It deliberately contains **no scraper, credentials, SFTP client or guessed provider column aliases**. A real provider sample/schema must supply an explicit field map into the canonical fields:

- ticker (or an explicit resolver such as verified ISIN → ticker mapping)
- as-of date (or an explicit file-level date)
- holder name
- optional stable holder id
- optional holder type and country
- shares
- ownership percentage
- rank

Every batch also requires a stable `scope_id`. For example, `top20` and `top200` become distinct provider identities, preventing false deltas caused by changing list depth.

The adapter can prepare batches while a source is unconnected, but persistence is blocked until an authorized machine connection is explicitly enabled. Interactive-only sources such as the Public Shareholder Portal cannot be promoted to machine ingestion by toggling connection state.

Provider adapters call the canonical runtime ingestion function from trusted server-side jobs only.

## Validation roadmap

Ownership evidence stays outside the investment model while point-in-time data is collected. Once an authoritative feed is connected, forward research should evaluate at minimum:

- 5D excess return vs OSEBX
- 20D excess return vs OSEBX
- 60D excess return vs OSEBX
- direction/magnitude of ownership delta
- holder type and number of independent accumulating holders
- interaction with verified primary-insider activity, company events and technical reversal signals

Any future score/Opportunity/High Conviction proposal requires preregistered statistical evidence and the existing change-control gates. Sample-size thresholds must not be lowered to manufacture significance.

## Model policy

Ownership snapshots, Capital Flow events and reported institutional context currently have **no effect** on NordicSignal score, Opportunity, High Conviction activation, thresholds or position sizing. Evidence must be collected forward before any such change is considered.
