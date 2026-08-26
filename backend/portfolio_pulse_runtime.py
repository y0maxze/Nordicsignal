"""Unified portfolio pulse for the NordicSignal home dashboard.

The dashboard consumes one coherent payload for recent material events and upcoming
financial-calendar events.  The underlying event and calendar routes remain useful
as focused public endpoints; this layer merely composes their already-cached results
so the home UI does not duplicate orchestration logic.
"""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import time

import extra_api

_CACHE_TTL = 45
_CACHE = {"at": 0.0, "value": None}


def _route_handler(app, path):
    for route in getattr(app, "routes", []):
        if getattr(route, "path", None) == path and "GET" in (getattr(route, "methods", None) or set()):
            return getattr(getattr(route, "dependant", None), "call", None) or getattr(route, "endpoint", None)
    return None


def install():
    if getattr(extra_api, "_portfolio_pulse_runtime_v1", False):
        return
    original_install = extra_api.install

    def patched_install(app):
        original_install(app)
        events_handler = _route_handler(app, "/api/holdings/events")
        calendar_handler = _route_handler(app, "/api/holdings/calendar")
        if not events_handler or not calendar_handler:
            return

        @app.get("/api/holdings/pulse")
        def holdings_pulse(event_limit: int = 12, calendar_limit: int = 16, days: int = 90):
            event_limit = max(1, min(int(event_limit or 12), 40))
            calendar_limit = max(1, min(int(calendar_limit or 16), 80))
            days = max(1, min(int(days or 90), 366))
            now = time.time()
            cached = _CACHE.get("value")
            if cached is not None and now - _CACHE.get("at", 0.0) < _CACHE_TTL:
                out = dict(cached)
                out["events"] = dict(out.get("events") or {})
                out["calendar"] = dict(out.get("calendar") or {})
                out["events"]["items"] = list(out["events"].get("items") or [])[:event_limit]
                out["calendar"]["items"] = list(out["calendar"].get("items") or [])[:calendar_limit]
                return out

            with ThreadPoolExecutor(max_workers=2) as pool:
                event_future = pool.submit(events_handler, max(event_limit, 16))
                calendar_future = pool.submit(calendar_handler, days, max(calendar_limit, 24))
                try:
                    events = event_future.result()
                except Exception as exc:
                    events = {"status": "unavailable", "items": [], "high_priority_count": 0, "error": str(exc)}
                try:
                    calendar = calendar_future.result()
                except Exception as exc:
                    calendar = {"status": "unavailable", "items": [], "error": str(exc)}

            full = {
                "status": "ok" if events.get("status") != "unavailable" or calendar.get("status") != "unavailable" else "partial",
                "events": events,
                "calendar": calendar,
                "generated_at": datetime.now(timezone.utc).isoformat(),
            }
            _CACHE.update({"at": now, "value": full})
            out = dict(full)
            out["events"] = dict(events)
            out["calendar"] = dict(calendar)
            out["events"]["items"] = list(events.get("items") or [])[:event_limit]
            out["calendar"]["items"] = list(calendar.get("items") or [])[:calendar_limit]
            return out

    extra_api.install = patched_install
    extra_api._portfolio_pulse_runtime_v1 = True


install()
