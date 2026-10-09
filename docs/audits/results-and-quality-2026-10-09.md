# Results and quality centre — 9 October 2026

## Question and evidence

The owner asked whether NordicSignal has beaten the exchange and requested a
smarter, more useful system. Production was inspected with read-only PostgreSQL
queries. The previous release was e9a3c46 (PR149). No broker account, capital
allocation, execution or net portfolio performance was inferred.

At approximately 16:18 UTC the database contained ten Opportunity events: six
EARLY_OPPORTUNITY and four WATCH_CONFLUENCE. No HIGH events were present. These
are not ten independent trades or a measurement of the whole Aksjer Score model.

| Trading-day horizon | Stored pairs | Unique tickers | Mean raw signal return | Mean stored difference vs OSEBX |
| --- | ---: | ---: | ---: | ---: |
| 1 | 10 | 8 | -1.602% | -1.550 pp |
| 5 | 8 | 6 | -1.056% | -0.534 pp |
| 10 | 6 | 5 | -2.105% | -1.214 pp |
| 20 | 5 | 4 | -19.692% | -18.229 pp |
| 60 | 0 | 0 | unknown | unknown |

Conclusion: market outperformance is **not established**. These diagnostics are
negative but also methodologically unsuitable for a net performance claim.
Do not present the 20-day figure as an investor's loss or remove bad observations
to improve the result. Sample sizes differ by horizon.

## Material methodology gaps

- The DVD 20-day record reports -90.0478% price return and -87.2903 pp difference.
  Its window crosses the issuer's NOK 20.60 extraordinary ex-dividend event on
  8 October. The legacy return code uses closes and does not account for that cash
  distribution. It is not verified total return.
- Euronext distinguishes OSEBX GR (NO0007035327), OSEBN NR and OSEBP PR. Comparing
  unadjusted stock prices with gross-return OSEBX is not like-for-like.
- DNB events 1 and 4 reuse 31 August price data; event 4 was recorded on 2 September
  Oslo time. PEXIP events 12 and 13 reuse 2 October price data. A saved signal can
  be real while its historical reference close is not an executable entry price.
- Legacy benchmark rows persist neither the actual benchmark start/end dates nor
  provider-symbol provenance. Stock and index calendar alignment is not certified.
- The data have overlapping events, too few independent observations, no costs,
  no verified portfolio sizing/exposure and no account-level drawdown curve.

Sources inspected:

- https://live.euronext.com/en/markets/oslo/indices/list
- https://live.euronext.com/nb/product/indices/NO0007035327-XOSL
- https://www.marketscreener.com/news/deep-value-driller-as-ex-dividend-nok-20-60-today-ce785ddedf81f025
- Existing source files: opportunity_tracking_runtime.py,
  opportunity_benchmark_evidence_runtime.py, portfolio_benchmark_runtime.py.

## Shipped scope

- `/results`: a dedicated, responsive results/quality centre with labelled raw
  comparisons, signal-type filtering, horizon selection and a full event journal
  for the bounded window. Unknowns stay unknown. Metadata is escaped. Refresh
  failure clears the displayed snapshot and exposes retry; no apparent success.
- `/api/results-audit`: four bounded SELECT queries, no provider requests, schema
  mutation, settlement, scanner scheduling or model imports. Maximum 1,000 most
  recent events with explicit truncation. Missing sources are marked partial.
- Mean signal and benchmark columns use the same paired population. Displayed
  differences are recomputed from stored components; inconsistent legacy derived
  differences are flagged, never overwritten. No bad result is silently excluded.
- Entry-date, repeated-basis, version, missing-benchmark, invalid-number and
  large-price-move diagnostics. A large move is a review flag, not proof of a
  particular corporate action. Absence of a flag is not method certification.
- Market workflow cards: context, measurement and data quality. Shared navigation
  reaches Results on desktop and through the mobile menu. Existing brand retained.
- IR parser rejects undated generic report/calendar/navigation indexes and keeps
  period-specific report links and direct PDFs without inventing publication dates.
- Exchange issuer matching no longer treats a single shared name token as proof
  of identity. Bounded full-name matching prevents Aker Solutions releases being
  attached to Aker ASA simply because both contain Aker. Unknown identity is safer
  than an invented match; rename/alias coverage remains a separate registry task.
- PWA v35 refreshes shared presentation assets. Results/API snapshots are not added
  to offline caching. Anonymous production verification includes the new routes.
- Owner-approved weekly, read-only system/source audit was created for Friday
  evening Europe/Oslo. It does not authorize unattended code or model changes.

Validation: full backend and UI suites, route contract, no-write database fixture,
same-population comparisons, partial sources, repeated and stale entry dates,
nonfinite values, historical preservation, frontend filtering/escaping/retry.
Physical iPhone lifecycle and push delivery remain unverified.

## Next useful work, in dependency order

1. **Measurement v2, separate from legacy:** immutable signal-available timestamp,
   earliest eligible post-signal bar, exact stock/index entry and exit dates,
   provider IDs, currency and explicit price/gross/net return type. Persist raw
   and adjusted series with adjustment-version/source provenance, never overwrite
   the legacy table or retroactively relabel old observations as live execution.
2. **Corporate-action evidence:** issuer/ISIN, split factor and cash dividend with
   ex-date, currency, official source and revision time. Detect pre-adjusted prices
   to avoid double adjustment. Quarantine ambiguous, conflicting and revised data.
   Compare gross to gross or price to price; cost and tax assumptions stay explicit.
3. **Independent validation:** frozen cohorts and model version, issuer/time-block
   independence, holdout/walk-forward periods, transaction costs and liquidity,
   drawdown and uncertainty. Do not optimize thresholds on these ten observations.
4. **Broader source coverage:** review issuer financials, distinguish IR resources
   from dated releases, event calendar and financing deadlines with reliable source
   identity, and exchange suspension/resumption sequence. Missing is not zero.
5. **Real device/recovery readiness:** iPhone PWA lifecycle/push, restore drill and
   coordinated Worker/Render credential rotation. No one-sided secret rotation,
   new security permissions, broker orders or commercial-readiness claim.

Frozen score, Opportunity, High Conviction, sizing and automated push rules are
unchanged. This release makes limitations actionable; it does not manufacture edge.
