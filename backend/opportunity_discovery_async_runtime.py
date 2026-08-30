"""Keep extended Opportunity discovery off the latency-critical core scan path."""
import threading
import time

import opportunity_data_coverage_runtime as coverage

_REFRESH_LOCK = threading.Lock()
_REFRESHING = False


def _refresh_cache():
    global _REFRESHING
    try:
        rows, meta = coverage._build_discovery_universe()
        with coverage._CACHE_LOCK:
            coverage._DISCOVERY_CACHE.update({
                "at": time.time(),
                "rows": [dict(row) for row in rows],
                "meta": dict(meta),
            })
    finally:
        with _REFRESH_LOCK:
            _REFRESHING = False


def nonblocking_discovery_rows(force=False):
    global _REFRESHING
    now = time.time()
    with coverage._CACHE_LOCK:
        cached = [dict(row) for row in coverage._DISCOVERY_CACHE.get("rows") or []]
        age = now - float(coverage._DISCOVERY_CACHE.get("at") or 0)
        fresh = bool(coverage._DISCOVERY_CACHE.get("at")) and age < coverage.DISCOVERY_CACHE_SECONDS
    if fresh:
        return cached

    if force:
        rows, meta = coverage._build_discovery_universe()
        with coverage._CACHE_LOCK:
            coverage._DISCOVERY_CACHE.update({"at": now, "rows": [dict(row) for row in rows], "meta": dict(meta)})
        return [dict(row) for row in rows]

    with _REFRESH_LOCK:
        if not _REFRESHING:
            _REFRESHING = True
            threading.Thread(
                target=_refresh_cache,
                daemon=True,
                name="nordicsignal-opportunity-discovery-refresh",
            ).start()
    # Return stale data (or empty on first boot) immediately so core scanning starts.
    return cached


def discovery_refreshing():
    with _REFRESH_LOCK:
        return bool(_REFRESHING)


def install():
    coverage._discovery_rows = nonblocking_discovery_rows
    original_status = coverage.discovery_status

    def status_with_refresh_state():
        result = original_status()
        result["discovery"]["refreshing"] = discovery_refreshing()
        result["discovery"]["refresh_mode"] = "background_nonblocking"
        return result

    coverage.discovery_status = status_with_refresh_state


install()
