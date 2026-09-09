"""Forward outcome settlement for archived NordicSignal Event Evidence.

Measurement only. Archived verified events are evaluated after enough trading days
have elapsed. Events published after the Oslo close are anchored to the next trading
session to avoid using a close that occurred before the information was public.
"""
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import event_evidence_runtime as evidence
import portfolio_benchmark_runtime as benchmarks
from database import connect
from providers import YahooProvider

OSLO = ZoneInfo("Europe/Oslo")
BENCHMARK_ID = "OSEBX"
HORIZONS = tuple(evidence.HORIZONS)
CLOSE_HOUR = 16
CLOSE_MINUTE = 20


def _ensure_schema():
    conn = connect()
    try:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS event_evidence_outcomes (
          event_id TEXT NOT NULL,
          horizon_days INTEGER NOT NULL,
          benchmark_id TEXT NOT NULL,
          entry_date TEXT NOT NULL,
          exit_date TEXT NOT NULL,
          entry_close REAL NOT NULL,
          exit_close REAL NOT NULL,
          return_pct REAL NOT NULL,
          benchmark_return_pct REAL,
          excess_return_pct REAL,
          max_drawdown_pct REAL,
          max_runup_pct REAL,
          settled_at TEXT NOT NULL,
          PRIMARY KEY(event_id,horizon_days,benchmark_id)
        );
        CREATE INDEX IF NOT EXISTS idx_event_evidence_outcomes_event
          ON event_evidence_outcomes(event_id,horizon_days);
        """)
        conn.commit()
    finally:
        conn.close()


def _parse_time(value):
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except Exception:
        return None


def _target_market_date(published_at):
    """Return earliest close we can fairly use after the announcement became public."""
    dt = _parse_time(published_at)
    if not dt:
        return None
    local = dt.astimezone(OSLO)
    target = local.date()
    close = local.replace(hour=CLOSE_HOUR, minute=CLOSE_MINUTE, second=0, microsecond=0)
    if local > close:
        target += timedelta(days=1)
    return target.isoformat()


def _stock_rows(provider, ticker):
    rows = benchmarks._chart_rows(provider, provider.symbol(ticker), "1y")
    return [{"date": d, "close": float(v)} for d, v in rows]


def _benchmark_rows(provider):
    definition = benchmarks.BENCHMARKS[BENCHMARK_ID]
    _, rows = benchmarks._first_working(provider, definition["symbols"], "1y")
    return [{"date": d, "close": float(v)} for d, v in rows]


def _start_index(rows, target_date):
    if not target_date:
        return None
    return next((i for i, row in enumerate(rows) if row["date"] >= target_date), None)


def _path_stats(rows, start_idx, end_idx):
    start = float(rows[start_idx]["close"])
    if start <= 0:
        return None, None
    changes = [(float(rows[i]["close"]) / start - 1.0) * 100.0 for i in range(start_idx, end_idx + 1)]
    return (min(changes), max(changes)) if changes else (None, None)


def _benchmark_return(rows, entry_date, horizon):
    start_idx = _start_index(rows, entry_date)
    if start_idx is None or start_idx + horizon >= len(rows):
        return None
    start = float(rows[start_idx]["close"])
    if start <= 0:
        return None
    return (float(rows[start_idx + horizon]["close"]) / start - 1.0) * 100.0


def settle_event_outcomes(ticker="", provider=None, benchmark_rows=None):
    """Settle every matured horizon exactly once. Returns inserted outcome rows."""
    _ensure_schema()
    provider = provider or YahooProvider()
    wanted = str(ticker or "").strip().upper().replace(".OL", "")
    conn = connect()
    try:
        if wanted:
            events = [dict(x) for x in conn.execute(
                "SELECT * FROM event_evidence_events WHERE ticker=? ORDER BY published_at,event_id", (wanted,)
            ).fetchall()]
        else:
            events = [dict(x) for x in conn.execute(
                "SELECT * FROM event_evidence_events WHERE ticker IS NOT NULL AND ticker<>'' ORDER BY ticker,published_at,event_id"
            ).fetchall()]
    finally:
        conn.close()
    if not events:
        return 0

    bench = benchmark_rows if benchmark_rows is not None else _benchmark_rows(provider)
    by_ticker = {}
    for event in events:
        symbol = str(event.get("ticker") or "").strip().upper().replace(".OL", "")
        if symbol:
            by_ticker.setdefault(symbol, []).append(event)

    settled = 0
    for symbol, group in by_ticker.items():
        try:
            rows = _stock_rows(provider, symbol)
        except Exception:
            continue
        conn = connect()
        try:
            for event in group:
                target = _target_market_date(event.get("published_at") or event.get("observed_at"))
                start_idx = _start_index(rows, target)
                if start_idx is None:
                    continue
                entry = float(rows[start_idx]["close"])
                if entry <= 0:
                    continue
                entry_date = rows[start_idx]["date"]
                for horizon in HORIZONS:
                    end_idx = start_idx + int(horizon)
                    if end_idx >= len(rows):
                        continue
                    exists = conn.execute(
                        "SELECT event_id FROM event_evidence_outcomes WHERE event_id=? AND horizon_days=? AND benchmark_id=?",
                        (event["event_id"], horizon, BENCHMARK_ID),
                    ).fetchone()
                    if exists:
                        continue
                    exit_close = float(rows[end_idx]["close"])
                    own = (exit_close / entry - 1.0) * 100.0
                    bench_ret = _benchmark_return(bench, entry_date, horizon)
                    excess = own - bench_ret if bench_ret is not None else None
                    drawdown, runup = _path_stats(rows, start_idx, end_idx)
                    conn.execute(
                        "INSERT INTO event_evidence_outcomes(event_id,horizon_days,benchmark_id,entry_date,exit_date,entry_close,exit_close,return_pct,benchmark_return_pct,excess_return_pct,max_drawdown_pct,max_runup_pct,settled_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                        (
                            event["event_id"], horizon, BENCHMARK_ID, entry_date, rows[end_idx]["date"],
                            entry, exit_close, own, bench_ret, excess, drawdown, runup, evidence._now(),
                        ),
                    )
                    settled += 1
            conn.commit()
        finally:
            conn.close()
    return settled


def evidence_samples(ticker=""):
    """Return archived events with matured horizon outcomes in summarize_samples format."""
    _ensure_schema()
    wanted = str(ticker or "").strip().upper().replace(".OL", "")
    conn = connect()
    try:
        params = (wanted,) if wanted else ()
        where = "WHERE e.ticker=?" if wanted else ""
        events = [dict(x) for x in conn.execute(
            f"SELECT e.* FROM event_evidence_events e {where} ORDER BY e.published_at,e.event_id", params
        ).fetchall()]
        outcomes = [dict(x) for x in conn.execute(
            f"SELECT o.* FROM event_evidence_outcomes o JOIN event_evidence_events e ON e.event_id=o.event_id {where} ORDER BY o.event_id,o.horizon_days",
            params,
        ).fetchall()]
    finally:
        conn.close()

    by_event = {}
    for row in outcomes:
        by_event.setdefault(row["event_id"], {})[str(int(row["horizon_days"]))] = row
    samples = []
    for event in events:
        group = by_event.get(event["event_id"])
        if not group:
            continue
        forward = {str(h): (group.get(str(h)) or {}).get("return_pct") for h in HORIZONS}
        excess = {str(h): (group.get(str(h)) or {}).get("excess_return_pct") for h in HORIZONS}
        longest = max((int(k) for k in group), default=0)
        path = group.get(str(longest)) or {}
        samples.append({
            "event_id": event["event_id"],
            "ticker": event.get("ticker"),
            "event_type": event.get("event_type"),
            "materiality_label": event.get("materiality_label"),
            "published_at": event.get("published_at"),
            "forward_return_pct": forward,
            "excess_return_pct": excess,
            "max_drawdown_pct": path.get("max_drawdown_pct"),
            "max_runup_pct": path.get("max_runup_pct"),
        })
    return samples


def build_event_evidence(ticker="", settle=True, provider=None):
    settled = 0
    if settle:
        try:
            settled = settle_event_outcomes(ticker=ticker, provider=provider)
        except Exception:
            settled = 0
    samples = evidence_samples(ticker=ticker)
    result = evidence.summarize_samples(samples)
    result.update({
        "ticker": str(ticker or "").strip().upper().replace(".OL", "") or None,
        "settled_now": settled,
        "benchmark": BENCHMARK_ID,
        "method": "Point-in-time verified exchange events; after-close announcements use the next trading session; returns measured close-to-close.",
        "limitations": [
            "Historical evidence is not proof of future performance.",
            "No transaction costs, slippage or tax are included.",
            "Small samples remain explicitly marked insufficient or early.",
            "Outcomes are never used to rewrite the original event record.",
        ],
    })
    return result


def install():
    if getattr(evidence.extra_api, "_event_outcome_runtime_v1", False):
        return
    original_install = evidence.extra_api.install

    def patched_install(app):
        original_install(app)
        _ensure_schema()

        @app.get("/api/event-evidence/outcomes")
        def event_evidence_outcomes(ticker: str = "", refresh: bool = False):
            return build_event_evidence(ticker=ticker, settle=bool(refresh))

    evidence.extra_api.install = patched_install
    evidence.extra_api._event_outcome_runtime_v1 = True


install()
