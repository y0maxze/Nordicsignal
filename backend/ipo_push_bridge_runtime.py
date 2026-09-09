"""Feed newly archived IPO candidates into the existing push event stream.

This bridge is intentionally tiny: push delivery/retry semantics remain owned by
push_runtime, while IPO candidate identity and persistence remain owned by the IPO
archive.
"""

import ipo_archive_runtime as archive
import push_runtime


def _ipo_push_event(row):
    d = dict(row)
    candidate_id = str(d.get("candidate_id") or "")
    if not candidate_id:
        return None
    company = str(d.get("company") or d.get("ticker") or "Nytt selskap")
    market = str(d.get("market") or "Oslo-markedet")
    listing_date = str(d.get("expected_listing_date_text") or "").strip()
    price = d.get("offer_price_nok")

    details = [market]
    if listing_date:
        details.append(f"forventet notering {listing_date}")
    if isinstance(price, (int, float)):
        details.append(f"tilbudspris {float(price):.2f} kr")

    return {
        "event_key": f"ipo:{candidate_id}",
        "ticker": d.get("ticker"),
        "title": f"Ny børsnotering · {company}",
        "body": " · ".join(details),
        "url": "/ipo-radar",
        "created_at": d.get("first_seen_at"),
    }


def install():
    if getattr(push_runtime, "_ipo_push_bridge_runtime_v1", False):
        return
    original_event_rows = push_runtime._event_rows

    def event_rows_with_ipo(since):
        items = list(original_event_rows(since) or [])
        try:
            for row in archive.recent_candidates(since=since, limit=push_runtime._MAX_EVENTS_PER_CYCLE):
                event = _ipo_push_event(row)
                if event:
                    items.append(event)
        except Exception:
            pass
        deduped = {}
        for item in items:
            key = str(item.get("event_key") or "")
            if key:
                deduped[key] = item
        merged = list(deduped.values())
        merged.sort(key=lambda x: str(x.get("created_at") or ""))
        return merged[-push_runtime._MAX_EVENTS_PER_CYCLE:]

    push_runtime._event_rows = event_rows_with_ipo
    push_runtime._ipo_push_bridge_runtime_v1 = True


install()
