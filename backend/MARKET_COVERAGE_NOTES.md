# Market coverage blind-spot fix

## Observed 2026-09-10 case: DVD

Production `insider_history` did capture the official Deep Value Driller event for Gunnar Hvammen: buy, 1,700,000 shares, trade date 2026-09-10. However, `stocks` and `insider_trades` had no DVD row because DVD was outside the fixed 24-stock scored universe. The market-wide collector therefore saw the disclosure, but the core stock refresh/score/Opportunity path did not cover DVD. Detail enrichment also lacked a parsed price/value in the captured row, so value-based insider logic could not use the NOK 35.36m magnitude.

This change closes the first problem by adding DVD to scored coverage and issuer aliases. It also adds AKER after an observed news/ownership-context blind spot around Nscale and foreign/institutional interest.

## Policy

Coverage expansion is not evidence for changing score weights or thresholds. No score formula, signal threshold, Opportunity rule, High Conviction activation or position-sizing rule is changed here. Institutional/fund ownership changes remain context until NordicSignal has a reliable point-in-time ownership source and forward evidence; they must not be mislabeled as primary-insider trades.

## Follow-up

The next data-quality improvement should enrich Euronext attachment-based insider disclosures so price and transaction value are retained when the HTML release contains only partial transaction detail. That work should be tested generically against multiple issuers rather than special-casing DVD.
