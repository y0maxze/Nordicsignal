"""Push bridge for fresh Capital Flow Radar events.

Loaded after push/alert-history runtimes so capital-flow events use the existing
retry, dedupe, delivery-history and Web Push infrastructure. This does not alter
score or signal eligibility.
"""
import extra_api
from database import connect
import push_runtime as push


def _body(row):
    direction = str(row.get("direction") or "neutral").lower()
    direction_text = "kjøp" if direction == "buy" else "salg" if direction == "sell" else "eierendring"
    actor = str(row.get("actor") or "").strip()
    value = row.get("value_nok")
    parts = [direction_text]
    if actor:
        parts.append(actor)
    if isinstance(value, (int, float)) and value >= 1_000_000:
        parts.append(f"{value / 1_000_000:.1f} mill. kr")
    evidence = str(row.get("evidence_level") or "").lower()
    parts.append("verifisert" if evidence == "verified" else "rapportert")
    return " · ".join(parts)


def install():
    if getattr(extra_api, "_capital_flow_push_bridge_v1", False):
        return
    original_event_rows = push._event_rows

    def event_rows_with_capital_flow(since):
        items = list(original_event_rows(since) or [])
        conn = connect()
        try:
            try:
                rows = conn.execute(
                    "SELECT id,fingerprint,ticker,instrument_name,event_type,direction,actor,value_nok,event_at,first_seen_at,evidence_level "
                    "FROM capital_flow_events WHERE alert_eligible=1 AND first_seen_at>? ORDER BY first_seen_at DESC LIMIT ?",
                    (since, push._MAX_EVENTS_PER_CYCLE),
                ).fetchall()
            except Exception:
                rows = []
        finally:
            conn.close()
        for raw in rows:
            d = dict(raw)
            ticker = str(d.get("ticker") or "").upper().replace(".OL", "")
            name = ticker or d.get("instrument_name") or "Kapitalflyt"
            items.append({
                "event_key": f"capital-flow:{d['fingerprint']}",
                "ticker": ticker or None,
                "title": f"{name} · Ny kapitalbevegelse",
                "body": _body(d),
                "url": f"/capital-flow?ticker={ticker}" if ticker else "/capital-flow",
                "created_at": d.get("first_seen_at") or d.get("event_at"),
            })
        items.sort(key=lambda x: str(x.get("created_at") or ""))
        return items[-push._MAX_EVENTS_PER_CYCLE:]

    push._event_rows = event_rows_with_capital_flow

    # Teach alert history the new class without coupling the generic history module
    # to this optional radar.
    try:
        import alert_history_runtime as history
        original_classify = history._classify

        def classify_with_capital_flow(payload):
            tag = str((payload or {}).get("tag") or "").lower()
            if tag.startswith("capital-flow:"):
                return "CAPITAL_FLOW"
            return original_classify(payload)

        history._classify = classify_with_capital_flow
    except Exception:
        pass

    extra_api._capital_flow_push_bridge_v1 = True


install()
