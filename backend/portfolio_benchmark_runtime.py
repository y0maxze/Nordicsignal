"""Lightweight holdings-vs-benchmark comparison for the home dashboard.

The chart intentionally compares the *current portfolio mix* with a selected market
benchmark. It is not presented as broker-grade time-weighted account performance:
older cash flows and positions that are no longer held cannot be reconstructed from
the current holdings table alone. This method stays transparent, useful and cheap on
Render Free while detailed purchase history continues to improve.
"""

from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
import threading
import time

import extra_api
import holdings_routes
from providers import YahooProvider

BENCHMARKS = OrderedDict([
    ("OSEBX", {"label": "OSEBX", "name": "Oslo Børs Benchmark", "symbols": ("OSEBX.OL", "^OSEBX")}),
    ("OSEAX", {"label": "OSEAX", "name": "Oslo Børs All-Share", "symbols": ("^OSEAX",)}),
    ("SP500", {"label": "S&P 500", "name": "S&P 500", "symbols": ("^GSPC",)}),
    ("NASDAQ100", {"label": "Nasdaq 100", "name": "Nasdaq 100", "symbols": ("^NDX",)}),
    ("OMXS30", {"label": "OMX Stockholm 30", "name": "OMX Stockholm 30", "symbols": ("^OMXS30", "^OMX")}),
    ("DAX", {"label": "DAX", "name": "DAX", "symbols": ("^GDAXI",)}),
])

PERIODS = {
    "1m": (35, "1d", "1M"),
    "3m": (100, "1d", "3M"),
    "1y": (370, "1d", "1Å"),
    "3y": (1100, "1wk", "3Å"),
    "5y": (1830, "1wk", "5Å"),
}

_CACHE = OrderedDict()
_CACHE_LOCK = threading.Lock()
_CACHE_TTL = 300
_CACHE_MAX = 8
_MAX_WORKERS = 2


def _clean_period(period):
    key = str(period or "1y").strip().lower()
    return key if key in PERIODS else "1y"


def _clean_benchmark(value):
    key = str(value or "OSEBX").strip().upper()
    return key if key in BENCHMARKS else "OSEBX"


def _chart_rows(provider, symbol, period):
    days, interval, _ = PERIODS[_clean_period(period)]
    end = datetime.now(timezone.utc) + timedelta(days=1)
    start = end - timedelta(days=days)
    data = provider._get(
        f"{provider.BASE}/v8/finance/chart/{symbol}",
        {
            "period1": int(start.timestamp()),
            "period2": int(end.timestamp()),
            "interval": interval,
            "events": "div,splits",
        },
    )
    result = ((data.get("chart") or {}).get("result") or [])
    if not result:
        raise RuntimeError(f"No history for {symbol}")
    result = result[0]
    timestamps = result.get("timestamp") or []
    quote = (result.get("indicators", {}).get("quote") or [{}])[0]
    closes = quote.get("close") or []
    rows = []
    for i, ts in enumerate(timestamps):
        if i >= len(closes) or closes[i] is None:
            continue
        rows.append((datetime.fromtimestamp(int(ts), timezone.utc).date().isoformat(), float(closes[i])))
    if len(rows) < 2:
        raise RuntimeError(f"Insufficient history for {symbol}")
    return rows


def _first_working(provider, symbols, period):
    last = None
    for symbol in symbols:
        try:
            return symbol, _chart_rows(provider, symbol, period)
        except Exception as exc:
            last = exc
    raise RuntimeError(str(last or "No benchmark history"))


def _position_symbol(provider, item):
    symbol = str(item.get("market_symbol") or "").strip()
    if symbol:
        return symbol
    ticker = str(item.get("ticker") or "").strip().upper()
    return provider.symbol(ticker) if ticker else None


def _normalize(rows):
    if not rows:
        return {}
    base = float(rows[0][1])
    if base <= 0:
        return {}
    return {d: (float(v) / base - 1.0) * 100.0 for d, v in rows if v is not None}


def _carry_value(series, date, previous=None):
    if date in series:
        return series[date]
    return previous


def _combine_current_weighted(benchmark_rows, positions):
    """Combine normalized position returns using today's market-value weights."""
    benchmark_norm = _normalize(benchmark_rows)
    dates = [d for d, _ in benchmark_rows if d in benchmark_norm]
    valid = [x for x in positions if x.get("series") and float(x.get("weight") or 0) > 0]
    total_weight = sum(float(x["weight"]) for x in valid)
    if not dates or total_weight <= 0:
        return []

    state = {i: None for i in range(len(valid))}
    out = []
    for date in dates:
        weighted = 0.0
        covered = 0.0
        for i, pos in enumerate(valid):
            state[i] = _carry_value(pos["series"], date, state[i])
            if state[i] is None:
                continue
            w = float(pos["weight"])
            weighted += state[i] * w
            covered += w
        if covered <= 0:
            continue
        out.append({
            "date": date,
            "portfolio_pct": weighted / covered,
            "benchmark_pct": benchmark_norm.get(date),
            "coverage_pct": covered / total_weight * 100.0,
        })
    return out


def _signature(snapshot):
    rows = []
    for x in snapshot.get("items") or []:
        rows.append((
            str(x.get("ticker") or ""),
            str(x.get("market_symbol") or ""),
            round(float(x.get("market_value") or 0), 2),
        ))
    return tuple(sorted(rows))


def _cache_get(key):
    with _CACHE_LOCK:
        row = _CACHE.get(key)
        if not row or time.time() - row[0] >= _CACHE_TTL:
            if row:
                _CACHE.pop(key, None)
            return None
        _CACHE.move_to_end(key)
        return row[1]


def _cache_put(key, value):
    with _CACHE_LOCK:
        _CACHE[key] = (time.time(), value)
        _CACHE.move_to_end(key)
        while len(_CACHE) > _CACHE_MAX:
            _CACHE.popitem(last=False)


def build_comparison(provider, snapshot, benchmark="OSEBX", period="1y"):
    benchmark = _clean_benchmark(benchmark)
    period = _clean_period(period)
    definition = BENCHMARKS[benchmark]
    benchmark_symbol, benchmark_rows = _first_working(provider, definition["symbols"], period)

    items = [x for x in snapshot.get("items") or [] if x.get("market_value") is not None and float(x.get("market_value") or 0) > 0]
    total_market = sum(float(x.get("market_value") or 0) for x in items)
    positions = []

    def fetch_one(item):
        symbol = _position_symbol(provider, item)
        if not symbol:
            return None
        rows = _chart_rows(provider, symbol, period)
        return {
            "ticker": item.get("ticker"),
            "symbol": symbol,
            "weight": float(item.get("market_value") or 0) / total_market if total_market > 0 else 0.0,
            "series": _normalize(rows),
        }

    if total_market > 0:
        with ThreadPoolExecutor(max_workers=_MAX_WORKERS) as pool:
            futures = [pool.submit(fetch_one, item) for item in items]
            for future in as_completed(futures):
                try:
                    row = future.result()
                    if row:
                        positions.append(row)
                except Exception:
                    pass

    series = _combine_current_weighted(benchmark_rows, positions)
    latest = series[-1] if series else {}
    _, _, period_label = PERIODS[period]
    return {
        "status": "ok" if series else "partial",
        "benchmark": benchmark,
        "benchmark_label": definition["label"],
        "benchmark_name": definition["name"],
        "benchmark_symbol": benchmark_symbol,
        "period": period,
        "period_label": period_label,
        "method": "current_weighted_mix",
        "method_label": "Dagens beholdningsmiks",
        "portfolio_return_pct": latest.get("portfolio_pct"),
        "benchmark_return_pct": latest.get("benchmark_pct"),
        "difference_pp": (latest.get("portfolio_pct") - latest.get("benchmark_pct")) if latest.get("portfolio_pct") is not None and latest.get("benchmark_pct") is not None else None,
        "coverage_pct": latest.get("coverage_pct"),
        "series": series,
        "benchmarks": [{"id": k, "label": v["label"], "name": v["name"]} for k, v in BENCHMARKS.items()],
        "periods": [{"id": k, "label": v[2]} for k, v in PERIODS.items()],
        "note": "Historisk sammenligning av dagens beholdningsmiks, vektet med dagens markedsverdier. Dette er ikke kontoutskrift eller full tidsvektet megleravkastning.",
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


def install():
    if getattr(extra_api, "_portfolio_benchmark_runtime_v1", False):
        return
    original_install = extra_api.install

    def patched_install(app):
        original_install(app)
        provider = YahooProvider()

        @app.get("/api/holdings/compare")
        def holdings_compare(benchmark: str = "OSEBX", period: str = "1y"):
            benchmark_key = _clean_benchmark(benchmark)
            period_key = _clean_period(period)
            snapshot = holdings_routes.build_holdings_snapshot(provider)
            key = (benchmark_key, period_key, _signature(snapshot))
            cached = _cache_get(key)
            if cached is not None:
                return cached
            value = build_comparison(provider, snapshot, benchmark_key, period_key)
            _cache_put(key, value)
            return value

    extra_api.install = patched_install
    extra_api._portfolio_benchmark_runtime_v1 = True


install()
