"""Diagnostic live validation for Early Opportunity Engine.

Fetches current public Yahoo/Euronext-backed evidence for a small representative
Oslo Børs set. It never modifies production scoring.
"""
import json

from opportunity_confluence_runtime import live_opportunity, _company_name
from providers import NordicRegulatoryProvider

TICKERS = ("XPLRA", "LSG", "MPCC", "EQNR", "DNB")


def _insider_debug(ticker):
    try:
        feed = NordicRegulatoryProvider().insider(ticker, _company_name(ticker)) or {}
        items = feed.get("items") or []
        return {
            "raw_status": feed.get("status"),
            "raw_source": feed.get("source"),
            "raw_item_count": len(items),
            "verified_detail_count": feed.get("verified_detail_count"),
            "raw_buy_count": feed.get("buy_count"),
            "raw_sell_count": feed.get("sell_count"),
            "dates": sorted({str(x.get("trade_date") or x.get("date") or x.get("published_at") or "")[:10] for x in items if x}),
            "actors": sorted({str(x.get("person") or x.get("related_primary_insider") or x.get("entity") or x.get("insider") or "").strip() for x in items if x and (x.get("person") or x.get("related_primary_insider") or x.get("entity") or x.get("insider"))}),
            "actions": [str(x.get("transaction_type") or x.get("direction") or x.get("activity_type") or "") for x in items[:20]],
            "signal": feed.get("insider_signal_v2"),
        }
    except Exception as exc:
        return {"error": str(exc)}


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
                "insider_debug": _insider_debug(ticker),
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
