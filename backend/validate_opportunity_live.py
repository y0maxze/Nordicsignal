"""Universe-wide live validation for Early Opportunity Engine.

Fetches current public Yahoo/Euronext-backed evidence for every stock in the
NordicSignal universe. It never modifies production scoring. The validation also
asserts that the canonical Smart Money bridge is present on every successful result
and that monetary insider evidence is always attributable to at least one actor.
"""
import json

from main import TICKERS
from opportunity_confluence_runtime import live_opportunity, _targeted_market_rows


def _compact_raw_rows(ticker):
    rows = []
    try:
        raw = _targeted_market_rows(ticker, 14)
    except Exception as exc:
        return [{"error": str(exc)}]
    for x in raw[:20]:
        rows.append({
            "node_id": x.get("node_id"),
            "trade_date": x.get("trade_date") or x.get("date"),
            "published_at": x.get("published_at"),
            "direction": x.get("direction") or x.get("transaction_type"),
            "person": x.get("person"),
            "entity": x.get("entity"),
            "related_primary_insider": x.get("related_primary_insider"),
            "role": x.get("role"),
            "shares": x.get("shares"),
            "price": x.get("price"),
            "transaction_value": x.get("transaction_value"),
            "title": x.get("title"),
            "summary": str(x.get("summary") or "")[:360],
        })
    return rows


def main():
    results = []
    failures = []
    integration_failures = []
    labels = {}
    insider_covered = 0
    insider_missing = 0
    insider_unavailable = 0
    diagnostics = {}

    for ticker in TICKERS:
        try:
            item = live_opportunity(ticker)
            opp = item.get("opportunity") or {}
            components = opp.get("components") or {}
            insider = item.get("insider_signal_v2") or {}
            item_count = int(insider.get("evidence_item_count") or 0)
            coverage = str(insider.get("evidence_coverage") or ("verified_detail" if item_count else "no_recent_detail"))
            if coverage == "verified_detail":
                insider_covered += 1
                diagnostics[ticker] = _compact_raw_rows(ticker)
                print(json.dumps({"insider_raw_debug": ticker, "rows": diagnostics[ticker]}, ensure_ascii=False))
            elif coverage == "unavailable":
                insider_unavailable += 1
            else:
                insider_missing += 1

            if "smart_money_quality" not in components:
                integration_failures.append(f"{ticker}:missing_smart_money_quality")
            try:
                independent_buyers = int(components.get("independent_buyers") or 0)
                buy_value_nok = float(components.get("buy_value_nok") or 0.0)
            except (TypeError, ValueError):
                independent_buyers, buy_value_nok = 0, 0.0
            if independent_buyers == 0 and buy_value_nok > 0:
                integration_failures.append(f"{ticker}:unattributed_buy_value:{buy_value_nok:.2f}")

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
                "smart_money_quality": components.get("smart_money_quality"),
                "smart_money_points": components.get("smart_money_points"),
                "meaningful_actors_500k_plus": components.get("meaningful_actors_500k_plus"),
                "million_plus_actors": components.get("million_plus_actors"),
                "senior_actors": components.get("senior_actors"),
                "reasons": opp.get("reasons") or [],
                "insider_coverage": coverage,
                "insider_evidence_source": insider.get("evidence_source"),
                "insider_evidence_items": item_count,
                "rejected_value_row_count": insider.get("rejected_value_row_count"),
                "deduplicated_row_count": insider.get("deduplicated_row_count"),
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
        "integration_failures": integration_failures,
        "label_counts": labels,
        "insider_detail_covered": insider_covered,
        "insider_no_recent_detail": insider_missing,
        "insider_unavailable": insider_unavailable,
        "coverage_pct": round((len(results) / len(TICKERS)) * 100.0, 2) if TICKERS else 0.0,
    }
    print(json.dumps({"summary": summary}, ensure_ascii=False))

    with open("opportunity_live_validation.json", "w", encoding="utf-8") as f:
        json.dump({"summary": summary, "results": results, "diagnostics": diagnostics}, f, ensure_ascii=False, indent=2)

    minimum = max(3, int(len(TICKERS) * 0.85))
    max_failures = max(2, int(len(TICKERS) * 0.15))
    if len(results) < minimum or len(failures) > max_failures:
        raise SystemExit("Universe-wide live validation coverage too low")
    if insider_unavailable > max_failures:
        raise SystemExit("Insider evidence provider unavailable for too much of universe")
    if integration_failures:
        raise SystemExit("Canonical insider/Smart Money integration invariants failed")


if __name__ == "__main__":
    main()
