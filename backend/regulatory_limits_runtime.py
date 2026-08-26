"""Memory and upstream-load limits for regulatory data providers.

The dashboard can request many insider/short rows at once. On a 512 MB Render
instance, allowing all of those Euronext/SSR parses to run concurrently creates
avoidable memory spikes and duplicate upstream work. This runtime keeps the public
API unchanged while bounding expensive regulatory concurrency and reusing recent
insider results.
"""

from collections import OrderedDict
import threading
import time

from providers import NordicRegulatoryProvider

_INSIDER_TTL_SECONDS = 300
_INSIDER_ERROR_TTL_SECONDS = 30
_INSIDER_CACHE_MAX = 64
_INSIDER_CACHE = OrderedDict()
_CACHE_LOCK = threading.RLock()
_INSIDER_SEMAPHORE = threading.BoundedSemaphore(2)
_SHORT_SEMAPHORE = threading.BoundedSemaphore(1)


def _cache_get(key):
    now = time.monotonic()
    with _CACHE_LOCK:
        item = _INSIDER_CACHE.get(key)
        if not item:
            return None
        expires, payload = item
        if expires <= now:
            _INSIDER_CACHE.pop(key, None)
            return None
        _INSIDER_CACHE.move_to_end(key)
        return payload


def _cache_put(key, payload, ttl):
    with _CACHE_LOCK:
        _INSIDER_CACHE[key] = (time.monotonic() + ttl, payload)
        _INSIDER_CACHE.move_to_end(key)
        while len(_INSIDER_CACHE) > _INSIDER_CACHE_MAX:
            _INSIDER_CACHE.popitem(last=False)


def _cache_clear_for_tests():
    with _CACHE_LOCK:
        _INSIDER_CACHE.clear()


def install():
    if getattr(NordicRegulatoryProvider, "_resource_limits_v1", False):
        return

    original_insider = NordicRegulatoryProvider.insider
    original_short = NordicRegulatoryProvider.short

    def limited_insider(self, ticker, company_name=""):
        symbol = str(ticker or "").upper().strip()
        key = (symbol, str(company_name or "").strip())
        cached = _cache_get(key)
        if cached is not None:
            return cached

        # Re-check after waiting because another request may have filled the cache.
        with _INSIDER_SEMAPHORE:
            cached = _cache_get(key)
            if cached is not None:
                return cached
            try:
                result = original_insider(self, symbol, company_name)
            except Exception:
                raise
            status = result.get("status") if isinstance(result, dict) else None
            ttl = (
                _INSIDER_TTL_SECONDS
                if status in {"live", "partial_live", "no_recent_disclosures"}
                else _INSIDER_ERROR_TTL_SECONDS
            )
            _cache_put(key, result, ttl)
            return result

    def limited_short(self, ticker, company_name=""):
        # NordicRegulatoryProvider already caches the full SSR register for 15 min.
        # The semaphore prevents several simultaneous first requests from all filling
        # that same cache independently.
        with _SHORT_SEMAPHORE:
            return original_short(self, ticker, company_name)

    NordicRegulatoryProvider.insider = limited_insider
    NordicRegulatoryProvider.short = limited_short
    NordicRegulatoryProvider._resource_limits_v1 = True


install()
