"""Small in-process TTL cache for shared, read-heavy API responses.

This cache deliberately stores only market-wide data that is identical for all
users. It is not suitable for authentication or per-user subscription data.
"""
from __future__ import annotations

import threading
import time
from typing import Callable, TypeVar

T = TypeVar("T")

_lock = threading.Lock()
_cache: dict[str, tuple[float, object]] = {}
_inflight: dict[str, threading.Event] = {}


def ttl_cached(key: str, ttl_seconds: float, loader: Callable[[], T]) -> T:
    while True:
        now = time.monotonic()
        with _lock:
            entry = _cache.get(key)
            if entry and entry[0] > now:
                return entry[1]  # type: ignore[return-value]

            event = _inflight.get(key)
            if event is None:
                event = threading.Event()
                _inflight[key] = event
                leader = True
            else:
                leader = False

        if leader:
            try:
                value = loader()
                expires = time.monotonic() + max(0.0, ttl_seconds)
                with _lock:
                    _cache[key] = (expires, value)
                return value
            finally:
                with _lock:
                    finished = _inflight.pop(key, None)
                    if finished is not None:
                        finished.set()

        event.wait()


def invalidate(prefix: str | None = None) -> None:
    with _lock:
        if prefix is None:
            _cache.clear()
            return
        for key in list(_cache):
            if key.startswith(prefix):
                _cache.pop(key, None)
