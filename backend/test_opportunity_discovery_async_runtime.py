import time

import opportunity_data_coverage_runtime as coverage
import opportunity_discovery_async_runtime as async_discovery


def test_stale_discovery_returns_immediately_and_starts_background_refresh(monkeypatch):
    with coverage._CACHE_LOCK:
        coverage._DISCOVERY_CACHE.update({"at": 0.0, "rows": [], "meta": {}})
    monkeypatch.setattr(async_discovery, "_REFRESHING", False)

    direct_calls = []
    monkeypatch.setattr(
        coverage,
        "_build_discovery_universe",
        lambda: direct_calls.append(True) or ([], {"status": "test"}),
    )

    started = []

    class FakeThread:
        def __init__(self, target=None, daemon=None, name=None):
            self.target = target
            self.name = name

        def start(self):
            started.append(self.name)

    monkeypatch.setattr(async_discovery.threading, "Thread", FakeThread)
    rows = async_discovery.nonblocking_discovery_rows(force=False)

    assert rows == []
    assert direct_calls == []
    assert started == ["nordicsignal-opportunity-discovery-refresh"]


def test_fresh_discovery_cache_avoids_refresh(monkeypatch):
    with coverage._CACHE_LOCK:
        coverage._DISCOVERY_CACHE.update({
            "at": time.time(),
            "rows": [{"ticker": "DISC", "name": "Discovery ASA"}],
            "meta": {"status": "ok"},
        })
    monkeypatch.setattr(async_discovery, "_REFRESHING", False)
    rows = async_discovery.nonblocking_discovery_rows(force=False)
    assert rows == [{"ticker": "DISC", "name": "Discovery ASA"}]
    assert async_discovery.discovery_refreshing() is False
