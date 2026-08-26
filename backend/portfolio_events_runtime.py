"""Portfolio-scoped event feed for the NordicSignal home dashboard.

The dashboard should surface only events that matter to positions the user has
actually entered in Holdings.  This module aggregates the already-installed news,
report and insider routes without introducing another provider implementation.
"""

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import threading
import time

import extra_api
from database import connect

_CACHE_LOCK = threading.Lock()
_CACHE = {"key": None, "at": 0.0, "value": None}
_CACHE_TTL = 60
_MAX_WORKERS = 2


def _route_handler(app, path):
    for route in getattr(app, "routes", []):
        if getattr(route, "path", None) == path and "GET" in (getattr(route, "methods", None) or set()):
            return getattr(getattr(route, "dependant", None), "call", None) or getattr(route, "endpoint", None)
    return None


def _holding_rows():
    conn = connect()
    try:
        rows = conn.execute(
            "SELECT DISTINCT h.ticker,COALESCE(s.name,h.ticker) AS company_name "
            "FROM holdings h LEFT JOIN stocks s ON s.ticker=h.ticker ORDER BY h.ticker"
        ).fetchall()
    except Exception:
        return []
    finally:
        try:
            conn.close()
        except Exception:
            pass
    return [dict(row) for row in rows]


def _iso(value):
    if not value:
        return None
    text = str(value).strip()
    try:
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).isoformat()
    except Exception:
        # Insider dates are commonly YYYY-MM-DD and sort correctly as strings.
        if len(text) == 10 and text[4:5] == "-" and text[7:8] == "-":
            return text + "T00:00:00+00:00"
        return None


def _event(ticker, company, kind, title, url=None, occurred_at=None, importance="normal", **extra):
    row = {
        "ticker": ticker,
        "company": company,
        "kind": kind,
        "title": title,
        "url": url,
        "occurred_at": _iso(occurred_at),
        "importance": importance,
    }
    row.update({k: v for k, v in extra.items() if v is not None})
    return row


def _events_for_one(row, news_handler, reports_handler, insider_handler):
    ticker = str(row.get("ticker") or "").upper()
    company = row.get("company_name") or ticker
    events = []

    # Reports are always material enough to surface on the portfolio home page.
    if reports_handler:
        try:
            data = reports_handler(ticker, 4) or {}
            for item in (data.get("items") or [])[:4]:
                events.append(_event(
                    ticker, company, "report", item.get("title") or "Finansiell rapport",
                    item.get("url"), item.get("published_at"), "high",
                    category="Rapport", source=item.get("publisher") or item.get("source_type"),
                ))
        except Exception:
            pass

    # Insider events get richer actor/direction metadata from the regulatory route.
    if insider_handler:
        try:
            data = insider_handler(ticker) or {}
            for item in (data.get("items") or [])[:3]:
                direction = item.get("transaction_type") or item.get("direction") or "other"
                actor = item.get("person") or item.get("entity") or item.get("insider")
                role = item.get("role")
                label = "Insiderkjøp" if direction == "buy" else "Insidersalg" if direction == "sell" else "Insiderhendelse"
                title = f"{label}: {actor}" if actor else (item.get("title") or label)
                events.append(_event(
                    ticker, company, "insider", title, item.get("url"),
                    item.get("trade_date") or item.get("date"), "high",
                    direction=direction, actor=actor, role=role,
                    shares=item.get("shares"), price=item.get("price"),
                ))
        except Exception:
            pass

    # Keep only meaningful company announcements; generic media chatter stays on News.
    if news_handler:
        try:
            data = news_handler(ticker, 8) or {}
            for item in data.get("items") or []:
                category = item.get("category") or "Nyhet"
                official = bool(item.get("official"))
                if category in ("Rapport", "Insider"):
                    continue
                if category not in ("Børsmelding", "Selskap", "Utbytte") and not official:
                    continue
                kind = "dividend" if category == "Utbytte" else "announcement"
                importance = "high" if category == "Børsmelding" else "normal"
                events.append(_event(
                    ticker, company, kind, item.get("title") or category,
                    item.get("url"), item.get("published_at"), importance,
                    category=category, source=item.get("publisher") or item.get("source_type"),
                ))
        except Exception:
            pass

    return events


def _dedupe_and_sort(events, limit):
    out = []
    seen = set()
    for item in events:
        key = (
            str(item.get("ticker") or "").upper(),
            str(item.get("url") or "").split("?", 1)[0].rstrip("/").lower(),
            " ".join(str(item.get("title") or "").lower().split()),
        )
        compact = (key[0], key[1] or key[2])
        if compact in seen:
            continue
        seen.add(compact)
        out.append(item)

    priority = {"high": 0, "normal": 1}
    out.sort(key=lambda x: (x.get("occurred_at") is None, -(datetime.fromisoformat(x["occurred_at"]).timestamp()) if x.get("occurred_at") else 0, priority.get(x.get("importance"), 9)))
    return out[:limit]


def install():
    if getattr(extra_api, "_portfolio_events_runtime_v1", False):
        return
    original_install = extra_api.install

    def patched_install(app):
        original_install(app)
        news_handler = _route_handler(app, "/api/news/{ticker}")
        reports_handler = _route_handler(app, "/api/reports/{ticker}")
        insider_handler = _route_handler(app, "/api/insider/{ticker}")

        @app.get("/api/holdings/events")
        def holdings_events(limit: int = 16):
            limit = max(1, min(int(limit or 16), 40))
            holdings = _holding_rows()
            key = tuple((str(x.get("ticker") or "").upper(), str(x.get("company_name") or "")) for x in holdings)
            now = time.time()
            with _CACHE_LOCK:
                if _CACHE["key"] == key and _CACHE["value"] is not None and now - _CACHE["at"] < _CACHE_TTL:
                    cached = dict(_CACHE["value"])
                    cached["items"] = list(cached.get("items") or [])[:limit]
                    return cached

            events = []
            with ThreadPoolExecutor(max_workers=_MAX_WORKERS) as pool:
                futures = [pool.submit(_events_for_one, row, news_handler, reports_handler, insider_handler) for row in holdings]
                for future in as_completed(futures):
                    try:
                        events.extend(future.result())
                    except Exception:
                        pass

            items = _dedupe_and_sort(events, 40)
            value = {
                "status": "ok",
                "holding_count": len(holdings),
                "event_count": len(items),
                "high_priority_count": sum(1 for x in items if x.get("importance") == "high"),
                "items": items,
                "generated_at": datetime.now(timezone.utc).isoformat(),
            }
            with _CACHE_LOCK:
                _CACHE.update({"key": key, "at": now, "value": value})
            result = dict(value)
            result["items"] = items[:limit]
            return result

    extra_api.install = patched_install
    extra_api._portfolio_events_runtime_v1 = True


install()
