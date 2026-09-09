"""Persistent evidence archive for verified NordicSignal event-radar observations.

This module separates point-in-time event capture from later outcome evaluation. It
stores only information available when a verified exchange event was observed so the
future evidence layer can avoid look-ahead bias.
"""
from datetime import datetime, timezone
import hashlib
import json
from statistics import mean, median

import extra_api
from database import connect

HORIZONS = (1, 5, 20, 60)
MODEL_VERSION = "event_evidence_v1"


def _now():
    return datetime.now(timezone.utc).isoformat()


def _event_id(item):
    identity = "|".join([
        str(item.get("node_id") or ""), str(item.get("url") or ""),
        str(item.get("ticker") or "").upper(), str(item.get("published_at") or ""),
        str(item.get("title") or ""),
    ])
    return hashlib.sha256(identity.encode("utf-8")).hexdigest()[:32]


def _ensure_schema():
    conn = connect()
    try:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS event_evidence_events (
          event_id TEXT PRIMARY KEY,
          ticker TEXT,
          event_type TEXT,
          event_label TEXT,
          materiality_label TEXT,
          materiality_ratio_pct REAL,
          amount_nok REAL,
          published_at TEXT,
          title TEXT,
          source_url TEXT,
          observed_at TEXT NOT NULL,
          raw_payload TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_event_evidence_ticker_time
          ON event_evidence_events(ticker,published_at);
        CREATE INDEX IF NOT EXISTS idx_event_evidence_type_time
          ON event_evidence_events(event_type,published_at);
        """)
        conn.commit()
    finally:
        conn.close()


def record_events(items):
    """Persist verified exchange events idempotently using point-in-time fields only."""
    _ensure_schema()
    conn = connect(); inserted = 0
    try:
        for raw in items or []:
            if not raw.get("official") or raw.get("source_type") != "exchange":
                continue
            event_type = str(raw.get("event_type") or "").strip()
            if not event_type:
                continue
            event_id = _event_id(raw)
            if conn.execute("SELECT event_id FROM event_evidence_events WHERE event_id=?", (event_id,)).fetchone():
                continue
            materiality = raw.get("materiality") if isinstance(raw.get("materiality"), dict) else {}
            conn.execute(
                "INSERT INTO event_evidence_events(event_id,ticker,event_type,event_label,materiality_label,materiality_ratio_pct,amount_nok,published_at,title,source_url,observed_at,raw_payload) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                (event_id, str(raw.get("ticker") or "").upper() or None, event_type,
                 raw.get("event_label"), materiality.get("label"), materiality.get("revenue_ratio_pct"),
                 materiality.get("announced_value_nok"), raw.get("published_at"), raw.get("title"),
                 raw.get("url"), _now(), json.dumps(raw, ensure_ascii=False, separators=(",", ":"), default=str)),
            )
            inserted += 1
        conn.commit()
    finally:
        conn.close()
    return inserted


def _maturity(n):
    return "insufficient" if n < 20 else "early" if n < 50 else "useful_history"


def _horizon_stats(samples, horizon):
    key = str(horizon)
    usable = [x for x in samples or [] if isinstance((x.get("forward_return_pct") or {}).get(key), (int, float))]
    values = [float(x["forward_return_pct"][key]) for x in usable]
    excess = [float((x.get("excess_return_pct") or {}).get(key)) for x in usable if isinstance((x.get("excess_return_pct") or {}).get(key), (int, float))]
    return {
        "n": len(values),
        "mean_return_pct": round(mean(values), 3) if values else None,
        "median_return_pct": round(median(values), 3) if values else None,
        "positive_rate_pct": round(sum(1 for v in values if v > 0) / len(values) * 100.0, 1) if values else None,
        "mean_excess_return_pct": round(mean(excess), 3) if excess else None,
        "median_excess_return_pct": round(median(excess), 3) if excess else None,
        "benchmark_n": len(excess),
    }


def summarize_samples(samples):
    """Summarize matured event observations. This function never predicts direction."""
    samples = list(samples or []); groups = {}
    for item in samples:
        key = (str(item.get("event_type") or "unknown"), str(item.get("materiality_label") or "unknown"))
        groups.setdefault(key, []).append(item)

    def summarize(group):
        drawdowns = [float(x["max_drawdown_pct"]) for x in group if isinstance(x.get("max_drawdown_pct"), (int, float))]
        runups = [float(x["max_runup_pct"]) for x in group if isinstance(x.get("max_runup_pct"), (int, float))]
        return {
            "sample_count": len(group), "maturity": _maturity(len(group)),
            "horizons": {str(h): _horizon_stats(group, h) for h in HORIZONS},
            "median_max_drawdown_pct": round(median(drawdowns), 3) if drawdowns else None,
            "median_max_runup_pct": round(median(runups), 3) if runups else None,
        }

    return {
        "model": MODEL_VERSION, "sample_count": len(samples), "maturity": _maturity(len(samples)),
        "overall": summarize(samples),
        "by_event_materiality": [
            {"event_type": event_type, "materiality_label": label, **summarize(group)}
            for (event_type, label), group in sorted(groups.items(), key=lambda pair: (-len(pair[1]), pair[0]))
        ],
        "policy": "Measurement only. Historical evidence does not change NordicSignal scores, signals or thresholds.",
    }


def archive_status(ticker=""):
    _ensure_schema(); wanted = str(ticker or "").strip().upper(); conn = connect()
    try:
        if wanted:
            rows = conn.execute("SELECT event_type,materiality_label,COUNT(*) AS n FROM event_evidence_events WHERE ticker=? GROUP BY event_type,materiality_label ORDER BY n DESC", (wanted,)).fetchall()
            total_row = conn.execute("SELECT COUNT(*) AS n FROM event_evidence_events WHERE ticker=?", (wanted,)).fetchone()
        else:
            rows = conn.execute("SELECT event_type,materiality_label,COUNT(*) AS n FROM event_evidence_events GROUP BY event_type,materiality_label ORDER BY n DESC").fetchall()
            total_row = conn.execute("SELECT COUNT(*) AS n FROM event_evidence_events").fetchone()
    finally:
        conn.close()
    total = int(total_row["n"] if total_row else 0)
    return {
        "status": "collecting" if total < 20 else "evidence_building", "ticker": wanted or None,
        "event_count": total, "maturity": _maturity(total), "groups": [dict(x) for x in rows],
        "model": MODEL_VERSION,
        "policy": "Point-in-time archive only. No predictive claim and no score/threshold changes.",
        "generated_at": _now(),
    }


def install():
    if getattr(extra_api, "_event_evidence_runtime_v1", False): return
    original_install = extra_api.install
    def patched_install(app):
        original_install(app); _ensure_schema()
        @app.get("/api/event-evidence")
        def event_evidence_status(ticker: str = ""):
            return archive_status(ticker)
    extra_api.install = patched_install; extra_api._event_evidence_runtime_v1 = True

install()
