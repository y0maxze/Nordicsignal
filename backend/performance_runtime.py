"""Performance orchestration for NordicSignal.

Provides a small dashboard BFF (backend-for-frontend) so mobile/desktop home views
can render critical user state first and defer upstream-heavy market feeds. It also
adds bounded in-process route timing telemetry exposed through /api/performance.
No personalized dashboard response is response-body cached.
"""

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from collections import OrderedDict
import threading
import time

from fastapi import Request

import extra_api


_MAX_WORKERS = 3
_STATS_LOCK = threading.RLock()
_STATS = OrderedDict()
_MAX_STATS = 64


def _route_handler(app, path):
    for route in getattr(app, "routes", []):
        if getattr(route, "path", None) == path and "GET" in (getattr(route, "methods", None) or set()):
            return getattr(getattr(route, "dependant", None), "call", None) or getattr(route, "endpoint", None)
    return None


def _record(path, elapsed_ms, status_code):
    with _STATS_LOCK:
        row = dict(_STATS.get(path) or {"count": 0, "total_ms": 0.0, "max_ms": 0.0, "errors": 0})
        row["count"] += 1
        row["total_ms"] += float(elapsed_ms)
        row["last_ms"] = round(float(elapsed_ms), 2)
        row["max_ms"] = round(max(float(row.get("max_ms") or 0), float(elapsed_ms)), 2)
        row["errors"] += 1 if int(status_code or 0) >= 400 else 0
        row["avg_ms"] = round(row["total_ms"] / max(1, row["count"]), 2)
        row["last_status"] = int(status_code or 0)
        row["updated_at"] = datetime.now(timezone.utc).isoformat()
        _STATS[path] = row
        _STATS.move_to_end(path)
        while len(_STATS) > _MAX_STATS:
            _STATS.popitem(last=False)


def _timed(name, fn):
    started = time.perf_counter()
    try:
        return name, fn(), None, round((time.perf_counter() - started) * 1000.0, 2)
    except Exception as exc:
        return name, None, f"{type(exc).__name__}: {exc}", round((time.perf_counter() - started) * 1000.0, 2)


def _call_sections(tasks):
    sections = {}
    errors = {}
    timings = {}
    if not tasks:
        return sections, errors, timings
    with ThreadPoolExecutor(max_workers=min(_MAX_WORKERS, len(tasks))) as pool:
        futures = [pool.submit(_timed, name, fn) for name, fn in tasks.items()]
        for future in as_completed(futures):
            name, value, error, elapsed = future.result()
            timings[name] = elapsed
            if error:
                errors[name] = error
            else:
                sections[name] = value
    return sections, errors, timings


def install():
    if getattr(extra_api, "_performance_runtime_v1", False):
        return
    original_install = extra_api.install

    def patched_install(app):
        original_install(app)

        holdings = _route_handler(app, "/api/holdings")
        events = _route_handler(app, "/api/holdings/events")
        calendar = _route_handler(app, "/api/holdings/calendar")
        insider = _route_handler(app, "/api/insider-market")
        signal_events = _route_handler(app, "/api/signal-events")
        radar = _route_handler(app, "/api/radar")
        news = _route_handler(app, "/api/news")

        @app.get("/api/dashboard-home")
        def dashboard_home(mode: str = "desktop", phase: str = "full", refresh: bool = False):
            mode = str(mode or "desktop").strip().lower()
            phase = str(phase or "full").strip().lower()
            if mode not in {"desktop", "mobile"}:
                mode = "desktop"
            if phase not in {"core", "deferred", "full"}:
                phase = "full"

            tasks = {}
            if phase in {"core", "full"} and holdings:
                tasks["holdings"] = lambda: holdings()

            if phase in {"deferred", "full"}:
                if events:
                    tasks["events"] = lambda: events(limit=12 if mode == "desktop" else 6)
                if calendar:
                    tasks["calendar"] = lambda: calendar(days=90 if mode == "desktop" else 45, limit=16 if mode == "desktop" else 6)
                if mode == "mobile":
                    if insider:
                        tasks["insider"] = lambda: insider(limit=18, days=7, refresh=bool(refresh))
                    # The mobile "Stock signals" card is a latest-change feed, so use
                    # the same signal-events node as desktop. It now includes score
                    # changes, trend reversals and unusual trading activity.
                    if signal_events:
                        tasks["radar"] = lambda: signal_events(asset_class="Aksjer", limit=8)
                    elif radar:
                        tasks["radar"] = lambda: radar()
                    if news:
                        tasks["news"] = lambda: news(limit=8)

            started = time.perf_counter()
            sections, errors, timings = _call_sections(tasks)
            total_ms = round((time.perf_counter() - started) * 1000.0, 2)
            return {
                "status": "partial" if errors else "ok",
                "mode": mode,
                "phase": phase,
                "sections": sections,
                "errors": errors,
                "timings_ms": timings,
                "total_ms": total_ms,
                "generated_at": datetime.now(timezone.utc).isoformat(),
            }

        @app.get("/api/performance")
        def performance_snapshot():
            with _STATS_LOCK:
                rows = [{"path": path, **dict(value)} for path, value in _STATS.items()]
            rows.sort(key=lambda x: float(x.get("avg_ms") or 0), reverse=True)
            return {
                "status": "ok",
                "items": rows,
                "count": len(rows),
                "note": "Process-local timing since the current backend process started; use avg/max to identify slow routes.",
                "generated_at": datetime.now(timezone.utc).isoformat(),
            }

        if not getattr(app.state, "nordicsignal_route_timing", False):
            app.state.nordicsignal_route_timing = True

            @app.middleware("http")
            async def nordicsignal_route_timing(request: Request, call_next):
                started = time.perf_counter()
                response = await call_next(request)
                elapsed = (time.perf_counter() - started) * 1000.0
                if request.url.path.startswith("/api/"):
                    _record(request.url.path, elapsed, response.status_code)
                    response.headers["server-timing"] = f"app;dur={elapsed:.2f}"
                    response.headers["x-nordicsignal-response-ms"] = f"{elapsed:.2f}"
                return response

    extra_api.install = patched_install
    extra_api._performance_runtime_v1 = True


install()
