"""Small in-process cache for public, read-only market endpoints.

The cache deliberately excludes holdings, paper trading, watchlists and every write
request. Its purpose is to collapse repeated Yahoo/Euronext/SSR reads while keeping
user-entered state immediately consistent.
"""

from collections import OrderedDict
import threading
import time

from fastapi import Request
from starlette.responses import Response

import extra_api

# Keep this cache intentionally small on Render Free. The previous 96 x 600 kB
# theoretical ceiling could retain about 58 MB of response bodies alone, before
# Python/container overhead. Most NordicSignal JSON responses are far smaller than
# 192 kB, so a 32-entry cache still removes duplicate upstream work with a much
# tighter worst-case memory footprint (~6 MB of bodies).
_MAX_ENTRIES = 32
_MAX_BODY_BYTES = 192_000
_CACHE = OrderedDict()
_LOCK = threading.RLock()


def _ttl_for(path):
    """Return cache TTL in seconds. Zero means never cache this route."""
    if not path.startswith("/api/"):
        return 0
    if path.startswith(("/api/holdings", "/api/paper", "/api/watchlist", "/api/refresh")):
        return 0
    if path == "/api/search":
        return 45
    if path.startswith("/api/quote/"):
        return 10
    if path.startswith("/api/market-pressure/"):
        return 20
    if path.startswith("/api/signal-events"):
        return 10
    if path.startswith("/api/instrument-signals"):
        return 45
    if path.startswith("/api/history/"):
        return 60
    if path.startswith("/api/instrument/"):
        # Instrument detail/history/news/analytics are upstream-heavy. A short TTL
        # still keeps navigation fresh while avoiding duplicate provider calls.
        if path.endswith("/analytics"):
            return 180
        return 45
    if path.startswith(("/api/insider/", "/api/short/", "/api/news/")):
        return 60
    if path.startswith("/api/reports/"):
        return 120
    if path.startswith("/api/dividends/"):
        return 300
    if path.startswith(("/api/research/", "/api/fundamentals/", "/api/score-explanation/")):
        return 180
    if path in {"/api/stocks", "/api/verification", "/api/radar", "/api/markets", "/api/health"}:
        return 15
    if path.startswith("/api/stocks/"):
        return 15
    return 0


def _clear():
    with _LOCK:
        _CACHE.clear()


def _get(key):
    now = time.monotonic()
    with _LOCK:
        item = _CACHE.get(key)
        if not item:
            return None
        expires, status, headers, body = item
        if expires <= now:
            _CACHE.pop(key, None)
            return None
        _CACHE.move_to_end(key)
        return status, headers, body


def _put(key, ttl, status, headers, body):
    if ttl <= 0 or len(body) > _MAX_BODY_BYTES:
        return
    clean_headers = {
        k: v for k, v in headers.items()
        if k.lower() not in {"content-length", "transfer-encoding", "connection"}
    }
    with _LOCK:
        _CACHE[key] = (time.monotonic() + ttl, status, clean_headers, body)
        _CACHE.move_to_end(key)
        while len(_CACHE) > _MAX_ENTRIES:
            _CACHE.popitem(last=False)


def install():
    if getattr(extra_api, "_public_http_cache_installed", False):
        return
    original_install = extra_api.install

    def patched_install(app):
        original_install(app)
        if getattr(app.state, "nordicsignal_public_cache", False):
            return
        app.state.nordicsignal_public_cache = True

        @app.middleware("http")
        async def public_market_cache(request: Request, call_next):
            path = request.url.path
            method = request.method.upper()

            if method not in {"GET", "HEAD"}:
                # User-state writes are deliberately uncached and should not evict
                # unrelated public market responses. Catalog registration is the one
                # write that can change a cached public signal universe.
                response = await call_next(request)
                if response.status_code < 400 and path == "/api/instrument-signals/register":
                    _clear()
                return response

            ttl = _ttl_for(path)
            refresh = str(request.query_params.get("refresh", "")).lower() in {"1", "true", "yes"}
            if ttl <= 0 or refresh:
                response = await call_next(request)
                if path == "/api/refresh" and response.status_code < 400:
                    _clear()
                return response

            key = f"{method}:{path}?{request.url.query}"
            cached = _get(key)
            if cached is not None:
                status, headers, body = cached
                headers = dict(headers)
                headers["x-nordicsignal-cache"] = "HIT"
                return Response(content=body, status_code=status, headers=headers)

            response = await call_next(request)
            if response.status_code != 200:
                return response

            body = b"".join([chunk async for chunk in response.body_iterator])
            headers = dict(response.headers)
            _put(key, ttl, response.status_code, headers, body)
            headers.pop("content-length", None)
            headers["x-nordicsignal-cache"] = "MISS"
            return Response(
                content=body,
                status_code=response.status_code,
                headers=headers,
                background=response.background,
            )

    extra_api.install = patched_install
    extra_api._public_http_cache_installed = True
