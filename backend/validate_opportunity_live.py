"""Diagnostic live validation for Early Opportunity Engine.

Fetches current public Yahoo/Euronext-backed evidence for a small representative
Oslo Børs set. It never modifies production scoring.
"""
import json

from opportunity_confluence_runtime import live_opportunity

TICKERS = ("XPLRA", "LSG", "MPCC", "EQNR", "DNB")


def main():
    results = []
    failures = []
    for ticker in TICKERS:
        try:
            item = live_opportunity(ticker)
            opp = item.get("opportunity") or {}
            components = opp.get("components") or {}
            row = {
                "ticker": ticker,
                "status": item.get("status"),
                "label": opp.get("label"),
                "score": opp.get("score"),
                "confidence": opp.get("confidence"),
                "reversal_score": components.get("reversal_score"),
                "reversal_regime": components.get("reversal_regime"),
                "volume_ratio": components.get("volume_ratio"),
                "volume_state": components.get("volume_state"),
                "insider_label": components.get("insider_label"),
                "independent_buyers": components.get("independent_buyers"),
                "buy_value_nok": components.get("buy_value_nok"),
                "reasons": opp.get("reasons") or [],
            }
            results.append(row)
            print(json.dumps(row, ensure_ascii=False))
            if item.get("status") != "ok" or opp.get("score") is None:
                failures.append(ticker)
        except Exception as exc:
            failures.append(ticker)
            print(json.dumps({"ticker": ticker, "error": str(exc)}, ensure_ascii=False))

    with open("opportunity_live_validation.json", "w", encoding="utf-8") as f:
        json.dump({"results": results, "failures": failures}, f, ensure_ascii=False, indent=2)

    if len(results) < 3:
        raise SystemExit("Live validation coverage too low")


if __name__ == "__main__":
    main()
