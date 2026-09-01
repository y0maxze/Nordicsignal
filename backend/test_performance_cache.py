import threading
import time

from performance import invalidate, ttl_cached


def setup_function():
    invalidate()


def test_ttl_cache_reuses_value_until_expiry():
    calls = []

    def load():
        calls.append(1)
        return {"value": len(calls)}

    first = ttl_cached("stocks", 0.05, load)
    second = ttl_cached("stocks", 0.05, load)
    assert first == second == {"value": 1}
    assert len(calls) == 1

    time.sleep(0.06)
    third = ttl_cached("stocks", 0.05, load)
    assert third == {"value": 2}
    assert len(calls) == 2


def test_prefix_invalidation_only_removes_matching_entries():
    ttl_cached("market:stocks", 60, lambda: 1)
    ttl_cached("market:verification", 60, lambda: 2)
    ttl_cached("user:example", 60, lambda: 3)

    invalidate("market:")

    assert ttl_cached("market:stocks", 60, lambda: 10) == 10
    assert ttl_cached("market:verification", 60, lambda: 20) == 20
    assert ttl_cached("user:example", 60, lambda: 30) == 3


def test_cache_is_safe_under_parallel_reads():
    errors = []

    def worker():
        try:
            for _ in range(100):
                value = ttl_cached("shared", 60, lambda: {"ok": True})
                assert value["ok"] is True
        except Exception as exc:
            errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert not errors


def test_parallel_cache_miss_runs_loader_once():
    calls = []
    start = threading.Barrier(12)
    results = []

    def load():
        calls.append(1)
        time.sleep(0.05)
        return {"value": 42}

    def worker():
        start.wait()
        results.append(ttl_cached("stampede", 60, load))

    threads = [threading.Thread(target=worker) for _ in range(12)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert len(calls) == 1
    assert len(results) == 12
    assert all(result == {"value": 42} for result in results)


def test_failed_loader_does_not_deadlock_followers():
    attempts = []
    start = threading.Barrier(2)
    outcomes = []

    def flaky():
        attempts.append(1)
        if len(attempts) == 1:
            time.sleep(0.03)
            raise RuntimeError("temporary")
        return "ok"

    def worker():
        start.wait()
        try:
            outcomes.append(ttl_cached("flaky", 60, flaky))
        except RuntimeError:
            outcomes.append("failed")

    threads = [threading.Thread(target=worker) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert sorted(outcomes) == ["failed", "ok"]
    assert len(attempts) == 2
