"""Bound and freshness-limit the raw HTML cache used by news aggregation.

Issuer investor-relations pages can be large. ``news_runtime`` already protects its
cache with a lock, so replacing the plain dict with this byte-bounded mapping keeps
its public behaviour intact while preventing cached HTML from consuming an
unbounded share of a small Render instance.  The original 15-minute raw TTL was too
stale for a live event dashboard; three minutes is a practical balance between
freshness and upstream/provider load.
"""

from collections import OrderedDict

import news_runtime

_MAX_ENTRIES = 12
_MAX_TOTAL_BYTES = 4_000_000
_MAX_ITEM_BYTES = 1_500_000
_RAW_TTL_SECONDS = 180


class BoundedTextCache(OrderedDict):
    def __init__(self, *args, **kwargs):
        self.total_bytes = 0
        super().__init__()
        if args or kwargs:
            self.update(*args, **kwargs)

    @staticmethod
    def _size(value):
        try:
            payload = value[1] if isinstance(value, tuple) and len(value) >= 2 else value
            return len(str(payload).encode("utf-8", errors="ignore"))
        except Exception:
            return 0

    def __setitem__(self, key, value):
        size = self._size(value)
        if size > _MAX_ITEM_BYTES:
            # Oversized pages are still parsed for the current request; they are just
            # not retained in process memory for the full cache TTL.
            if key in self:
                old = super().__getitem__(key)
                self.total_bytes -= self._size(old)
                super().__delitem__(key)
            return

        if key in self:
            old = super().__getitem__(key)
            self.total_bytes -= self._size(old)
            super().__delitem__(key)
        super().__setitem__(key, value)
        self.total_bytes += size
        self.move_to_end(key)

        while self and (len(self) > _MAX_ENTRIES or self.total_bytes > _MAX_TOTAL_BYTES):
            _, old = self.popitem(last=False)
            self.total_bytes -= self._size(old)

    def __delitem__(self, key):
        old = super().__getitem__(key)
        self.total_bytes -= self._size(old)
        super().__delitem__(key)

    def pop(self, key, default=None):
        if key not in self:
            return default
        value = super().pop(key)
        self.total_bytes -= self._size(value)
        return value

    def clear(self):
        super().clear()
        self.total_bytes = 0


def install():
    if getattr(news_runtime, "_bounded_html_cache_v2", False):
        return
    existing = list((news_runtime._CACHE or {}).items())
    bounded = BoundedTextCache()
    for key, value in existing:
        bounded[key] = value
    news_runtime._CACHE = bounded
    news_runtime._CACHE_TTL = _RAW_TTL_SECONDS
    news_runtime._bounded_html_cache_v1 = True
    news_runtime._bounded_html_cache_v2 = True


install()
