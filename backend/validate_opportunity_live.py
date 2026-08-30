"""Universe-wide live validation for Early Opportunity Engine.

Fetches current public Yahoo/Euronext-backed evidence for every stock in the
NordicSignal universe. It never modifies production scoring.
"""
import json

from main import TICKERS
from opportunity_confluence_runtime import live_opportunity, _company_name
from providers import NordicRegulatoryProvider


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
            "signal": feed.get("insider_signal_v2"),
        }
    except Exception as exc:
        return {"error": str(exc)}


def main():
    results = []
    failures = []
    labels = {}
    insider_covered = 0
    insider_missing = 0

    for ticker in TICKERS:
        try:
            item = live_opportunity(ticker)
            opp = item.get("opportunity") or {}
            components = opp.get("components") or {}
            debug = _insider_debug(ticker)
            raw_count = int(debug.get("raw_item_count") or 0)
            if raw_count > 0:
                insider_covered += 1
            else:
                insider_missing += 1
            label = str(opp.get("label") or "UNKNOWN")
            labels[label] = labels.get(label, 0) + 1
            row = {
                "ticker": ticker,
                "status": item.get("status"),
                "label": label,
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
                "insider_coverage": "covered" if raw_count > 0 else "no_recent_detail",
            }
            results.append(row)
            print(json.dumps(row, ensure_ascii=False))
            if item.get("status") != "ok" or opp.get("score") is None:
                failures.append(ticker)
        except Exception as exc:
            failures.append(ticker)
            print(json.dumps({"ticker": ticker, "error": str(exc)}, ensure_ascii=False))

    summary = {
        "universe_size": len(TICKERS),
        "validated": len(results),
        "failures": failures,
        "label_counts": labels,
        "insider_detail_covered": insider_covered,
        "insider_detail_missing": insider_missing,
        "coverage_pct": round((len(results) / len(TICKERS)) * 100.0, 2) if TICKERS else 0.0,
    }
    print(json.dumps({"summary": summary}, ensure_ascii=False))

    with open("opportunity_live_validation.json", "w", encoding="utf-8") as f:
        json.dump({"summary": summary, "results": results}, f, ensure_ascii=False, indent=2)

    # A provider can legitimately have no recent insider detail. What must not pass
    # silently is broad engine/data failure across the universe.
    minimum = max(3, int(len(TICKERS) * 0.85))
    if len(results) < minimum or len(failures) > max(2, int(len(TICKERS) * 0.15)):
        raise SystemExit("Universe-wide live validation coverage too low")


if __name__ == "__main__":
    main()
