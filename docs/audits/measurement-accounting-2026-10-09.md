# Measurement accounting and fair queue processing — 9 October 2026

## Concrete bugs fixed

Reconciliation previously selected the oldest 100 missing events on every run.
Unversioned/failed events or pre-series rows inside the timestamp slack could
prevent later valid events from being captured indefinitely. A persisted attempt
timestamp now prioritizes unchecked events, then least-recently checked events.
Counts include the whole outstanding candidate set, including unreviewed rows;
a successful later batch does not erase older gaps. Capture returning False is
verified against the database before being treated as successful. Null creation
timestamps are explicitly invalid. There is no historical availability backfill.

The candidate-price queue had the same oldest-100 problem because blocked entries
remain pending. It now rotates checks even when older dates have no usable data.
Both loops keep the existing batch limit, scheduler and no-extra-provider-call
contract. The status is a last-observed check, not continuous source certification.
Database-wide outstanding counts can include conservative timestamp-slack rows
until checked. A truncated pass remains partial even if it later drains the queue.

## Pure accounting module (not activated for live results)

`measurement_accounting.calculate(evidence)` supports one unlevered long position
in NOK with a full exit. There is no broker access, HTTP route, DB write or change
to the frozen measurement policy. It is an internal building block for a reviewed
adapter, not a replacement for missing certified market data.

Inputs require explicit quantity, unadjusted reference entry/exit prices, exact
market timestamps, instrument/currency identity, provenance, complete action
coverage, a cost policy fixed before signal availability and matching gross-return
benchmark timestamps. Strings encode decimal amounts; no costs default to zero.
See `backend/test_measurement_accounting.py::fixture` for the synthetic contract.
An adapter's coverage assertion is not independently verified by this module.

- Splits change units; reverse splits yielding fractions are rejected until cash
  in lieu is supported. Multiple events at the same timestamp are rejected rather
  than guessing the dividend share basis or order.
- Confirmed ordinary cash dividends accrue when entry < ex-time <= exit. Buying
  at the ex-time creates no entitlement. Cash paid and outstanding receivables
  remain distinct. Dividends are not reinvested. Values are before investor tax.
- Commission is max(minimum, notional times rate), rounded half-up to NOK cents
  per side. Explicit half-spread and slippage worsen reference execution on each
  side. This is a declared simulation convention, not a promise of achievable
  fills or exact broker settlement/rounding.
- Net return uses entry outlay including buy costs. Ending value includes net
  sale proceeds, paid dividends and receivables. Benchmark is a gross total-return
  reference index over identical instants, not an investable portfolio with fees.
- Output includes an evidence hash and research status. It explicitly does not
  certify sources, implement a portfolio curve or establish market outperformance.

Unknown actions (rights issues, mergers, spin-offs etc.), price/identity changes,
foreign currencies, missing costs/coverage, duplicate revisions, future evidence,
ambiguous timing and adjusted prices are rejected. Complete loss/delisting with a
zero exit, tax, withholding, FX, corporate action elections, partial fills and
portfolio capital-flow/risk accounting remain outside this v1 contract.

## Sources reviewed

- https://www.nordnet.no/faq/priser/kurtasje/nar-gjelder-prosentsatsen-ved-kurtasje
  Confirms minimum-versus-percentage commission structure. Its illustrative rates
  are not adopted as our live tariff; no account class or current tariff is inferred.
- https://www.nordnet.no/faq/selskapshendelser/utbytte/hva-er-ex-dag
  Describes entitlement before the ex-date and retention when selling on ex-date.
- https://www.dnb.no/dnbnyheter/no/bors-og-marked/aksjesplitt-aksjespleis
  Explains unit changes under splits/reverse splits and fractional holdings.

## Remaining release blockers

A permitted documented opening-data feed and reviewed live instrument/session
mapping are still absent. Corporate-action coverage and same-instant benchmark
observations are not yet connected. The cost policy is not configured for a new
live series. Automatic entries and net-performance publication remain disabled.
No existing raw results, scores, model weights, sizing or push rules are modified.

Validation: 962 backend tests and 78 frontend/Worker tests passed locally. The
new cases include starvation behind an unversioned event, rotation past missing
historical data, retaining earlier gaps, no false-success capture, split invariance,
ex-date boundaries, unpaid dividends, adverse costs, exact benchmark periods and
rejection of unsupported/ambiguous evidence. Full publication gates run on the PR.

## Production verification

PR154 merged as `f318c37d85c55d943ef952daa5fa2163882b085b`. All five PR
checks passed. Main CI and the Worker deployment passed, including the anonymous
Access/backend boundary check. Render deployment `dep-db4m9kuq1p3s73fhffvg`
became live at 22:05:24 UTC on 9 October. Read-only SQL confirmed both new queue
tables. The 22:10:08 UTC reconciliation reported zero outstanding gaps and zero
unreviewed events. There were still ten legacy events and zero measurement entries.
Authenticated Results displayed the new unreviewed count at 22:14:31 UTC.
This confirms the migration and status path, not a real new signal or entry.

## Euronext delayed-trade sample: useful, not a certified opening feed

Retrieved the public download service's Equities / Current Trading Day / Oslo
export on 9 October 2026 UTC. Its ZIP contained `Trades_Equities.csv`, with a
rights notice before the CSV header. No raw exchange data is committed here.

| Observation | Downloaded sample |
| --- | --- |
| Archive bytes | 1,997,190 |
| CSV bytes | 20,267,761 |
| Trade rows / distinct instrument IDs | 115,364 / 283 |
| Venues | XOSL 104,131; MERK 7,990; XOAS 3,243 |
| Currency / price notation | NOK / MONE for every row |
| Trade dates | 9 October 2026 for every row |
| Market mechanisms | 1: 114,694; 3: 593; 4: 77 |
| Modification indicator | `-` for every row; not proof of complete corrections |
| Duplicate venue + trade IDs | 0 within this one export |

Archive SHA-256: `8a87d7133ac1a01347710286ed4a338226930f65f6fb97521d57361fa52786dd`.
CSV SHA-256: `6f0abb186a422193258bf6ce58f7a4e01f35facdf96cf6e62ed210002d2bfbd4`.

The twenty-column schema includes trade/publication timestamps, instrument ID,
currency, price, venue, trade ID and several MMT flags. It does **not** include
`MmtTradingMode`, an auction qualifier, official-open field, adjustment basis,
corporate-action coverage, trading-state history or an index series. Its earliest
row is a mechanism-4 contingent trade at 06:32:11 UTC: selecting the first row is
not an opening-price method. Rows are not globally ordered by trade time.

Euronext's AVD technical explanation distinguishes market mechanism 1 (central
limit order book) from the separate trading-mode field that identifies scheduled
opening/closing auctions. Therefore mechanism 1 or a time near 09:00 Oslo cannot
independently certify the frozen opening-entry contract. This is our inference
from the inspected schema and the exchange's field definitions. The sample also
spans three venues, while the current entry validator accepts only XOSL.

Disposition: exploratory evidence only. No automated collection, entry promotion,
source-certification claim or public redistribution was enabled. The next provider
qualification must resolve opening/auction semantics, complete session and halt
coverage, late corrections/revisions, effective-dated instrument mapping and
permitted intended use. Corporate actions, comparable index observations, an
explicit cost policy and portfolio accounting remain separate requirements.

Sources:
- https://marketdata.euronext.com/data-reporting-service/trades-file
- https://www.euronext.com/en/data/pricing-specs-agreements/mifid-ii-compliant-data
  (delayed export availability and UTC convention, not completeness certification)
- https://www.euronext.com/en/media/14393/download
  (AVD webinar, October 2025, slide 11: market mechanism versus trading mode)
