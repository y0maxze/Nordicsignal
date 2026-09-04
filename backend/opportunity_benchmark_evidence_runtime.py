"""Benchmark-relative evidence for NordicSignal Opportunity events.

Measurement only. This module never changes signal thresholds, labels, eligibility,
or the aggregate stock score. It compares settled Opportunity returns with OSEBX
for the same trading-day horizons and exposes excess-return diagnostics.
"""
from statistics import median

import opportunity_tracking_runtime as tracking
import opportunity_evidence_v3_runtime as evidence_v3
import portfolio_benchmark_runtime as benchmarks

HORIZONS = tuple(evidence_v3.HORIZONS)
BENCHMARK_ID = "OSEBX"
MIN_SAMPLE = 20


def _ensure_schema():
    conn = tracking.connect()
    try:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS opportunity_benchmark_evidence (
          event_id BIGINT NOT NULL,
          horizon_days INTEGER NOT NULL,
          benchmark_id TEXT NOT NULL,
          benchmark_return_pct DOUBLE PRECISION,
          excess_return_pct DOUBLE PRECISION,
          settled_at TEXT NOT NULL,
          PRIMARY KEY(event_id,horizon_days,benchmark_id)
        );
        """)
        conn.commit()
    finally:
        conn.close()


def _benchmark_rows():
    provider = benchmarks.YahooProvider()
    definition = benchmarks.BENCHMARKS[BENCHMARK_ID]
    _, rows = benchmarks._first_working(provider, definition["symbols"], "1y")
    return [{"date": d, "close": float(v)} for d, v in rows]


def settle_benchmark_evidence(ticker, benchmark_rows=None):
    ticker = str(ticker or "").upper().replace(".OL", "")
    if not ticker:
        return 0
    rows = benchmark_rows if benchmark_rows is not None else _benchmark_rows()
    if not rows:
        return 0
    _ensure_schema()
    conn = tracking.connect()
    try:
        events = [dict(x) for x in conn.execute("SELECT * FROM opportunity_events WHERE ticker=? ORDER BY id", (ticker,)).fetchall()]
        settled = 0
        for event in events:
            market_day = tracking._entry_date_from_event(event)
            if not market_day:
                continue
            start_idx = next((i for i, row in enumerate(rows) if row["date"] >= market_day), None)
            if start_idx is None:
                continue
            start = float(rows[start_idx]["close"])
            if start <= 0:
                continue
            for horizon in HORIZONS:
                if start_idx + horizon >= len(rows):
                    continue
                exists = conn.execute("SELECT event_id FROM opportunity_benchmark_evidence WHERE event_id=? AND horizon_days=? AND benchmark_id=?", (event["id"], horizon, BENCHMARK_ID)).fetchone()
                if exists:
                    continue
                own = conn.execute("SELECT return_pct FROM opportunity_forward_returns WHERE event_id=? AND horizon_days=?", (event["id"], horizon)).fetchone()
                if not own:
                    continue
                bench_ret = (float(rows[start_idx + horizon]["close"]) / start - 1.0) * 100.0
                excess = float(own["return_pct"]) - bench_ret
                conn.execute("INSERT INTO opportunity_benchmark_evidence(event_id,horizon_days,benchmark_id,benchmark_return_pct,excess_return_pct,settled_at) VALUES(?,?,?,?,?,?)", (event["id"], horizon, BENCHMARK_ID, bench_ret, excess, tracking._now()))
                settled += 1
        conn.commit()
        return settled
    finally:
        conn.close()


def _stats(values):
    values = [float(v) for v in values if v is not None]
    n = len(values)
    return {
        "n": n,
        "mean_excess_return_pct": round(sum(values) / n, 3) if n else None,
        "median_excess_return_pct": round(float(median(values)), 3) if n else None,
        "outperformance_rate_pct": round(sum(v > 0 for v in values) / n * 100.0, 2) if n else None,
        "evidence_status": "usable" if n >= MIN_SAMPLE else "early" if n >= 8 else "insufficient",
        "minimum_usable_sample": MIN_SAMPLE,
    }


def opportunity_performance(limit=100):
    result = evidence_v3.opportunity_performance(limit=limit)
    _ensure_schema()
    conn = tracking.connect()
    try:
        rows = [dict(row) for row in conn.execute("SELECT b.*,e.label FROM opportunity_benchmark_evidence b JOIN opportunity_events e ON e.id=b.event_id WHERE b.benchmark_id=?", (BENCHMARK_ID,)).fetchall()]
    finally:
        conn.close()
    overall = {h: [] for h in HORIZONS}
    by_label = {}
    for row in rows:
        h = int(row["horizon_days"])
        if h not in overall:
            continue
        value = row.get("excess_return_pct")
        overall[h].append(value)
        label = str(row.get("label") or "")
        by_label.setdefault(label, {x: [] for x in HORIZONS})[h].append(value)
    result["benchmark_edge"] = {
        "benchmark": BENCHMARK_ID,
        "horizons": {str(h): _stats(overall[h]) for h in HORIZONS},
        "by_label": {label: {str(h): _stats(group[h]) for h in HORIZONS} for label, group in sorted(by_label.items())},
        "policy": "measurement_only_no_automatic_tuning",
    }
    return result


_original_settle = tracking.settle_forward_returns

def _settle_with_benchmark(ticker, rows=None):
    settled = _original_settle(ticker, rows=rows)
    try:
        settle_benchmark_evidence(ticker)
    except Exception:
        pass
    return settled


def install():
    _ensure_schema()
    tracking.settle_forward_returns = _settle_with_benchmark
    tracking.opportunity_performance = opportunity_performance


install()
