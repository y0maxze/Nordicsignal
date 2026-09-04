"""Lightweight NordicSignal API load test harness.

Usage:
  python load_test.py --base-url https://example.com --users 50 --requests 1000

The tool uses only the standard library so it can run locally or in CI without
adding production dependencies. It reports throughput, error rate and latency
percentiles and exits non-zero when configured SLOs are missed.
"""
from __future__ import annotations

import argparse
import json
import math
import statistics
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

DEFAULT_PATHS = ("/api/health", "/api/stocks", "/api/verification")


def percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, math.ceil((pct / 100.0) * len(ordered)) - 1))
    return ordered[index]


def _request(base_url: str, path: str, timeout: float) -> tuple[bool, float, int | None]:
    started = time.perf_counter()
    status = None
    ok = False
    try:
        req = Request(base_url.rstrip("/") + path, headers={"User-Agent": "NordicSignal-load-test/1.0"})
        with urlopen(req, timeout=timeout) as response:
            status = int(response.status)
            response.read()
            ok = 200 <= status < 400
    except HTTPError as exc:
        status = int(exc.code)
    except (URLError, TimeoutError, OSError):
        pass
    return ok, (time.perf_counter() - started) * 1000.0, status


def run_load_test(base_url: str, users: int, requests: int, paths: tuple[str, ...], timeout: float) -> dict:
    if users < 1 or requests < 1 or not paths:
        raise ValueError("users, requests and paths must be non-zero")

    lock = threading.Lock()
    counter = 0

    def next_path():
        nonlocal counter
        with lock:
            path = paths[counter % len(paths)]
            counter += 1
            return path

    started = time.perf_counter()
    latencies = []
    statuses: dict[str, int] = {}
    successes = 0

    with ThreadPoolExecutor(max_workers=users) as pool:
        futures = [pool.submit(_request, base_url, next_path(), timeout) for _ in range(requests)]
        for future in as_completed(futures):
            ok, latency, status = future.result()
            latencies.append(latency)
            successes += int(ok)
            key = str(status) if status is not None else "network_error"
            statuses[key] = statuses.get(key, 0) + 1

    duration = max(time.perf_counter() - started, 1e-9)
    failures = requests - successes
    return {
        "base_url": base_url,
        "concurrency": users,
        "requests": requests,
        "successes": successes,
        "failures": failures,
        "error_rate_pct": failures / requests * 100.0,
        "duration_seconds": duration,
        "requests_per_second": requests / duration,
        "latency_ms": {
            "mean": statistics.fmean(latencies) if latencies else 0.0,
            "p50": percentile(latencies, 50),
            "p95": percentile(latencies, 95),
            "p99": percentile(latencies, 99),
            "max": max(latencies) if latencies else 0.0,
        },
        "statuses": statuses,
        "paths": list(paths),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Load test NordicSignal read APIs")
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--users", type=int, default=25)
    parser.add_argument("--requests", type=int, default=250)
    parser.add_argument("--timeout", type=float, default=10.0)
    parser.add_argument("--path", action="append", dest="paths")
    parser.add_argument("--max-error-rate", type=float, default=1.0)
    parser.add_argument("--max-p95-ms", type=float, default=1000.0)
    args = parser.parse_args()

    result = run_load_test(
        args.base_url,
        args.users,
        args.requests,
        tuple(args.paths or DEFAULT_PATHS),
        args.timeout,
    )
    print(json.dumps(result, indent=2, sort_keys=True))

    if result["error_rate_pct"] > args.max_error_rate:
        return 2
    if result["latency_ms"]["p95"] > args.max_p95_ms:
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
