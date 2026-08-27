"""Small persistent hot-feed cache for market news and Insider Pulse.

In-memory provider caches disappear on every Render process restart. This layer keeps
only the latest already-renderable public feed JSON in Postgres/SQLite. Fresh cache
is returned immediately; slightly stale cache is served while one bounded background
refresh updates it. Personalized holdings data is never stored here.
"""

import json
import threading
import time

import extra_api
from database import connect


_FRESH_SECONDS = 120
_MAX_STALE_SECONDS = 300
_REFRESH_LOCK = threading.RLock()
_REFRESHING = set()


def _ensure_schema():
    conn = connect()
    try:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS runtime_feed_cache (cache_key TEXT PRIMARY KEY, payload TEXT NOT NULL, updated_at DOUBLE PRECISION NOT NULL)"
        )
        conn.commit()
    finally:
        conn.close()


def _read_cache(key):
    try:
        conn = connect()
        try:
            row = conn.execute("SELECT payload,updated_at FROM runtime_feed_cache WHERE cache_key=? LIMIT 1", (key,)).fetchone()
        finally:
            conn.close()
    except Exception:
        return None
    if not row:
        return None
    try:
        payload = json.loads(row["payload"])
        updated_at = float(row["updated_at"])
    except Exception:
        return None
    return payload, updated_at


def _write_cache(key, payload):
    text = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), default=str)
    now = time.time()
    conn = connect()
    try:
        conn.execute(
            "INSERT INTO runtime_feed_cache(cache_key,payload,updated_at) VALUES(?,?,?) "
            "ON CONFLICT(cache_key) DO UPDATE SET payload=excluded.payload,updated_at=excluded.updated_at",
            (key, text, now),
        )
        conn.commit()
    finally:
        conn.close()


def _route_handler(app, path):
    for route in getattr(app, "routes", []):
        if getattr(route, "path", None) == path and "GET" in (getattr(route, "methods", None) or set()):
            return getattr(getattr(route, "dependant", None), "call", None) or getattr(route, "endpoint", None)
    return None


def _replace_route(app, path, handler):
    for route in getattr(app, "routes", []):
        if getattr(route, "path", None) == path and "GET" in (getattr(route, "methods", None) or set()):
            route.endpoint = handler
            dependant = getattr(route, "dependant", None)
            if dependant is not None:
                dependant.call = handler
            return True
    return False


def _annotate(payload, state, age):
    result = dict(payload or {})
    result["persistent_cache"] = {"state": state, "age_seconds": round(max(0.0, age), 1)}
    return result


def _slice_items(payload, limit):
    result = dict(payload or {})
    if isinstance(result.get("items"), list):
        result["items"] = list(result["items"])[: max(1, int(limit or 1))]
    return result


def _background_refresh(key, builder):
    with _REFRESH_LOCK:
        if key in _REFRESHING:
            return
        _REFRESHING.add(key)

    def run():
        try:
            payload = builder()
            if isinstance(payload, dict):
                try:
                    _write_cache(key, payload)
                except Exception:
                    pass
        except Exception:
            pass
        finally:
            with _REFRESH_LOCK:
                _REFRESHING.discard(key)

    threading.Thread(target=run, name=f"nordicsignal-cache-{key}", daemon=True).start()


def _cached(key, builder, limit, force=False):
    if not force:
        cached = _read_cache(key)
        if cached:
            payload, updated_at = cached
            age = max(0.0, time.time() - updated_at)
            if age <= _FRESH_SECONDS:
                return _slice_items(_annotate(payload, "fresh", age), limit)
            if age <= _MAX_STALE_SECONDS:
                _background_refresh(key, builder)
                return _slice_items(_annotate(payload, "stale_while_revalidate", age), limit)

    payload = builder()
    if isinstance(payload, dict):
        try:
            _write_cache(key, payload)
        except Exception:
            pass
        return _slice_items(_annotate(payload, "refreshed", 0), limit)
    return payload


def install():
    if getattr(extra_api, "_persistent_feed_cache_v1", False):
        return
    original_install = extra_api.install

    def patched_install(app):
        original_install(app)
        try:
            _ensure_schema()
        except Exception:
            # Cache persistence is an optimization only. The existing live providers
            # remain the source of truth if storage is temporarily unavailable.
            pass
        news_handler = _route_handler(app, "/api/news")
        insider_handler = _route_handler(app, "/api/insider-market")

        if news_handler:
            def cached_market_news(limit: int = 30):
                limit = max(1, min(int(limit or 30), 50))
                return _cached("market_news:v1", lambda: news_handler(50), limit, False)
            _replace_route(app, "/api/news", cached_market_news)

        if insider_handler:
            def cached_insider_market(limit: int = 60, days: int = 14, refresh: bool = False):
                limit = max(1, min(int(limit or 60), 100))
                days = max(1, min(int(days or 14), 90))
                key = f"insider_market:v1:{days}d"
                return _cached(key, lambda: insider_handler(100, days, True), limit, bool(refresh))
            _replace_route(app, "/api/insider-market", cached_insider_market)

    extra_api.install = patched_install
    extra_api._persistent_feed_cache_v1 = True


install()
