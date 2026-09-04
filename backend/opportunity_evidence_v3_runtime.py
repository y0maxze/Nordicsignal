"""Risk-aware evidence measurement for NordicSignal Early Opportunity events.

Measurement only: this module does not change Opportunity thresholds, labels,
aggregate stock score, or signal eligibility. It adds path-aware maximum adverse
and favorable excursion for each settled horizon and exposes aggregate risk stats.
"""
from __future__ import annotations

from statistics import median

import opportunity_tracking_runtime as tracking
import opportunity_performance_v2_runtime as performance_v2

HORIZONS = tuple(performance_v2.HORIZONS)
_ORIGINAL_SETTLE_FORWARD_RETURNS = tracking.settle_forward_returns


def _ensure_schema():
    conn = tracking.connect()
    try:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS opportunity_path_evidence (
          event_id BIGINT NOT NULL,
          horizon_days INTEGER NOT NULL,
          max_drawdown_pct DOUBLE PRECISION,
          max_runup_pct DOUBLE PRECISION,
          settled_at TEXT NOT NULL,
          PRIMARY KEY(event_id,horizon_days)
        );
        """)
        conn.commit()
    finally:
        conn.close()


def _path_stats(rows, start_idx, horizon, entry):
    if start_idx is None or start_idx < 0 or horizon <= 0 or start_idx + horizon >= len(rows):
        return None
    try:
        entry = float(entry)
    except (TypeError, ValueError):
        return None
    if entry <= 0:
        return None
    values = []
    for row in rows[start_idx + 1:start_idx + horizon + 1]:
        try:
            close = float(row.get("close"))
        except (TypeError, ValueError, AttributeError):
            continue
        if close > 0:
            values.append(close)
    if not values:
        return None
    returns = [((value / entry) - 1.0) * 100.0 for value in values]
    return {"max_drawdown_pct": min(returns), "max_runup_pct": max(returns)}


def settle_path_evidence(ticker, rows=None):
    ticker = str(ticker or "").upper().replace(".OL", "")
    if not ticker:
        return 0
    rows = rows if rows is not None else tracking._history(tracking.YahooProvider(), ticker)
    if not rows:
        return 0
    _ensure_schema()
    conn = tracking.connect()
    try:
        events = [dict(x) for x in conn.execute(
            "SELECT * FROM opportunity_events WHERE ticker=? ORDER BY id", (ticker,)
        ).fetchall()]
        settled = 0
        for event in events:
            market_day = tracking._entry_date_from_event(event)
            if not market_day:
                continue
            start_idx = next((i for i, row in enumerate(rows) if row["date"] >= market_day), None)
            if start_idx is None:
                continue
            entry = event.get("entry_price")
            if entry is None:
                entry = rows[start_idx]["close"]
            for horizon in HORIZONS:
                exists = conn.execute(
                    "SELECT event_id FROM opportunity_path_evidence WHERE event_id=? AND horizon_days=?",
                    (event["id"], horizon),
                ).fetchone()
                if exists:
                    continue
                stats = _path_stats(rows, start_idx, horizon, entry)
                if stats is None:
                    continue
                conn.execute(
                    "INSERT INTO opportunity_path_evidence(event_id,horizon_days,max_drawdown_pct,max_runup_pct,settled_at) VALUES(?,?,?,?,?)",
                    (event["id"], horizon, stats["max_drawdown_pct"], stats["max_runup_pct"], tracking._now()),
                )
                settled += 1
        conn.commit()
        return settled
    finally:
        conn.close()


def settle_forward_returns_with_path(ticker, rows=None):
    """Preserve the existing forward-return settlement and add path evidence."""
    settled = _ORIGINAL_SETTLE_FORWARD_RETURNS(ticker, rows=rows)
    settle_path_evidence(ticker, rows=rows)
    return settled


def _risk_stats(rows):
    drawdowns = [float(row["max_drawdown_pct"]) for row in rows if row.get("max_drawdown_pct") is not None]
    runups = [float(row["max_runup_pct"]) for row in rows if row.get("max_runup_pct") is not None]
    return {
        "n": min(len(drawdowns), len(runups)),
        "median_max_drawdown_pct": round(float(median(drawdowns)), 3) if drawdowns else None,
        "worst_max_drawdown_pct": round(min(drawdowns), 3) if drawdowns else None,
        "median_max_runup_pct": round(float(median(runups)), 3) if runups else None,
        "best_max_runup_pct": round(max(runups), 3) if runups else None,
    }


def opportunity_performance(limit=100):
    result = performance_v2.opportunity_performance(limit=limit)
    _ensure_schema()
    conn = tracking.connect()
    try:
        rows = [dict(row) for row in conn.execute(
            "SELECT p.*,e.label FROM opportunity_path_evidence p JOIN opportunity_events e ON e.id=p.event_id"
        ).fetchall()]
    finally:
        conn.close()

    overall = {h: [] for h in HORIZONS}
    by_label = {}
    for row in rows:
        try:
            horizon = int(row.get("horizon_days") or 0)
        except (TypeError, ValueError):
            continue
        if horizon not in overall:
            continue
        overall[horizon].append(row)
        label = str(row.get("label") or "")
        by_label.setdefault(label, {h: [] for h in HORIZONS})[horizon].append(row)

    result["risk_path"] = {
        "horizons": {str(h): _risk_stats(overall[h]) for h in HORIZONS},
        "by_label": {
            label: {str(h): _risk_stats(grouped[h]) for h in HORIZONS}
            for label, grouped in sorted(by_label.items())
        },
        "method": "Close-to-close path from signal entry through each settled trading-day horizon.",
        "note": "Risk-path evidence is measurement only and cannot alter signal eligibility or thresholds.",
    }
    return result


def install():
    _ensure_schema()
    tracking.settle_forward_returns = settle_forward_returns_with_path
    tracking.opportunity_performance = opportunity_performance


install()
