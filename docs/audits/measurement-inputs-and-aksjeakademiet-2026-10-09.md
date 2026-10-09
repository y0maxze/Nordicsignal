# Measurement inputs and public comparator review — 9 October 2026

## Implemented

Journal reconciliation runs at startup and through the existing guarded scan
scheduler, with bounded work and an in-process lock. Missing verified events are
captured with current availability, never backdated to pretend live collection.
Unversioned/invalid/failed captures and truncated batches remain visible. Health
older than 30 minutes is stale. GET only reads persisted health.

Existing scheduled 3-month market-history refreshes now save candidate opening
observations for pending journal events without adding provider requests. Candidate
revisions are append-only, duplicate payloads are idempotent, and no candidate is
promoted to a measurement entry. Currency/ISIN/adjustment and auction identity
cannot be certified from the existing historical provider output. There is no
reliable verified-open adapter connected; this is an explicit remaining blocker.

The reviewed 2026 Oslo calendar excludes the exchange's published holidays,
marks the 1 April half-day, uses Europe/Oslo DST, and refuses unknown years. The
09:00 planning boundary is a scheduled market-open convention, NOT verified
instrument auction execution. Extraordinary closures, instrument suspensions and
auction extensions are not certified. Source date and version remain visible.

Sources reviewed:
- https://live.euronext.com/en/resources/trading-hours-holidays
- https://www.euronext.com/en/trading/trading-hours-holidays
- https://live.euronext.com/sites/default/files/company_press_releases/attachments_oslo/2026/01/20/663892_260120%20Aqua%20Bio%20Technology%20ASA%20Prospectus.pdf
  (issuer prospectus describes the 09:00 start; not live auction evidence)
- Current providers.py historical output (drops adjustment/identity provenance).

No live signals, costs, sizing, push rules or previous measurement policy changed.
Tests cover holiday/weekend/DST planning, unsupported-year refusal, delayed gap
repair, idempotency, absent model versions, stale/partial status, invalid/future
observations and preserving quarantined revisions with zero simulated entries.

## Aksjeakademiet.no: what the public evidence does and does not establish

Reviewed the homepage, public login presentation and terms. No independently
verifiable, dated portfolio track record against a specified total-return benchmark
was established from these pages. This is not evidence that no such record exists
elsewhere, nor a conclusion about a different similarly named provider.

Their terms (updated 5 August 2026) describe fictional practice capital, primarily
Yahoo data, and omission of commissions/spread/liquidity. The current homepage's
practice order form nevertheless displays simulated commission. This inconsistency
means the current cost implementation cannot be established from public text alone.
A displayed positive percentage or hypothetical compounding example does not
prove market outperformance. No paid account or private portfolio was inspected.

Sources:
- https://aksjeakademiet.no/
- https://aksjeakademiet.no/vilkar
- https://aksjeakademiet.no/logg-inn

## Proposed improvements for NordicSignal (hypotheses, not proven alpha)

1. Explain each signal in plain Norwegian: triggering evidence, publication time,
   competing evidence, missing inputs and conditions that would invalidate the idea.
2. Make report/dividend/financing dates useful in context; attach source and revision
   timestamps. A calendar event is not a prediction of price direction.
3. Separate research, practice trading and certified performance visually, with a
   single versioned method and matching terminology across UI and documentation.
4. Require realistic costs, same-period comparable benchmark returns, capital-flow
   handling, exposure, turnover and drawdown before a market-beating claim.
5. Evaluate pre-registered hypotheses on new data. For example quality/cash flow,
   valuation and event context could be tested separately; do not silently change
   frozen live scoring or tune on the ten old observations.
6. Add decision reviews showing what the system knew at the time and why the
   hypothesis failed. This supports learning without rewriting losing history.

Priority remains a source that certifies instrument identity, auction/open basis
and adjustments, followed by corporate actions and cost-aware portfolio accounting.
Feature richness and clear education are useful product qualities, not evidence
that either platform possesses a durable market edge.
