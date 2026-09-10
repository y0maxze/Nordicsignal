"""Research-only High Conviction foundation.

This endpoint exposes independent dimensions already measured by NordicSignal but
never emits a buy/sell signal and never changes the canonical stock score. Its only
purpose is to show whether the evidence required for a future High Conviction layer
is actually present.
"""
from datetime import datetime, timezone
import json

import extra_api
from database import connect

MODEL_VERSION = "high_conviction_shadow_v1"
_QUALIFYING_OPPORTUNITY = {"EARLY_OPPORTUNITY", "EARLY_OPPORTUNITY_HIGH", "WATCH_CONFLUENCE"}


def _now():
    return datetime.now(timezone.utc).isoformat()


def _ticker(value):
    return str(value or "").strip().upper().replace(".OL", "")


def _latest_score(ticker):
    conn = connect()
    try:
        row = conn.execute(
            "SELECT ticker,fundamentals,insider,valuation,sentiment,total,created_at,source "
            "FROM scores WHERE ticker=? ORDER BY id DESC LIMIT 1",
            (ticker,),
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def _opportunity(ticker):
    conn = connect()
    try:
        row = conn.execute(
            "SELECT ticker,label,score,payload,observed_at,updated_at FROM opportunity_state WHERE ticker=? LIMIT 1",
            (ticker,),
        ).fetchone()
        if not row:
            return None
        out = dict(row)
        try:
            out["payload"] = json.loads(out.get("payload") or "{}")
        except Exception:
            out["payload"] = {}
        return out
    finally:
        conn.close()


def _event_evidence_count(ticker, horizon=20):
    conn = connect()
    try:
        row = conn.execute(
            "SELECT COUNT(DISTINCT e.event_id) AS n "
            "FROM event_evidence_events e JOIN event_evidence_outcomes o ON o.event_id=e.event_id "
            "WHERE e.ticker=? AND o.horizon_days=? AND o.benchmark_id='OSEBX'",
            (ticker, int(horizon)),
        ).fetchone()
        return int(row["n"] or 0) if row else 0
    except Exception:
        return 0
    finally:
        conn.close()


def build_shadow(ticker):
    ticker = _ticker(ticker)
    if not ticker:
        return {"status": "invalid", "policy": "Research only; no score changes."}
    score = _latest_score(ticker)
    opp = _opportunity(ticker)
    event_n20 = _event_evidence_count(ticker, 20)

    dimensions = {
        "base_score": {
            "available": bool(score),
            "total": (score or {}).get("total"),
            "fundamentals": (score or {}).get("fundamentals"),
            "valuation": (score or {}).get("valuation"),
            "sentiment": (score or {}).get("sentiment"),
            "insider": (score or {}).get("insider"),
            "coverage_source": (score or {}).get("source"),
        },
        "opportunity": {
            "available": bool(opp),
            "label": (opp or {}).get("label"),
            "score": (opp or {}).get("score"),
            "qualifying_state": str((opp or {}).get("label") or "").upper() in _QUALIFYING_OPPORTUNITY,
            "observed_at": (opp or {}).get("observed_at"),
        },
        "event_evidence": {
            "benchmark": "OSEBX",
            "horizon_days": 20,
            "sample_n": event_n20,
            "maturity": "insufficient" if event_n20 < 20 else "early" if event_n20 < 50 else "useful_history",
        },
    }

    available = sum(1 for key in ("base_score", "opportunity") if dimensions[key]["available"])
    evidence_ready = event_n20 >= 50
    if not score or not opp:
        status = "missing_inputs"
    elif not evidence_ready:
        status = "collecting_evidence"
    else:
        status = "research_ready"

    blockers = []
    if not score:
        blockers.append("missing_base_score")
    if not opp:
        blockers.append("missing_opportunity_state")
    if event_n20 < 50:
        blockers.append("insufficient_20d_event_evidence")

    return {
        "status": status,
        "model": MODEL_VERSION,
        "ticker": ticker,
        "dimensions": dimensions,
        "dimension_coverage": {"available": available, "required": 2},
        "blockers": blockers,
        "activation": {
            "enabled": False,
            "reason": "High Conviction remains shadow-only until forward evidence supports a pre-registered rule set.",
        },
        "policy": "Research-only evidence assembly. No buy/sell signal, no stock-score change, no threshold tuning and no position-sizing output.",
        "generated_at": _now(),
    }


def install():
    if getattr(extra_api, "_high_conviction_shadow_runtime_v1", False):
        return
    original_install = extra_api.install

    def patched_install(app):
        original_install(app)

        @app.get("/api/high-conviction-shadow/{ticker}")
        def high_conviction_shadow(ticker: str):
            return build_shadow(ticker)

    extra_api.install = patched_install
    extra_api._high_conviction_shadow_runtime_v1 = True


install()
