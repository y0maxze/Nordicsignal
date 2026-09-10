"""Expand the research-only High Conviction shadow with measured context.

This layer remains descriptive. It assembles trend state, recent verified event risk,
benchmark-relative Opportunity outcomes, path risk and market-regime coverage. It
cannot activate a trade signal, alter NordicSignal scores, tune thresholds or emit
position sizing.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from statistics import median

import high_conviction_shadow_runtime as shadow
from database import connect

MODEL_VERSION = "high_conviction_shadow_v2"
HORIZON_DAYS = 20
MIN_EARLY_SAMPLE = 20
MIN_USEFUL_SAMPLE = 50
RECENT_EVENT_DAYS = 7
_BASE_BUILD = shadow.build_shadow


def _num(value):
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _maturity(n):
    n = int(n or 0)
    if n < MIN_EARLY_SAMPLE:
        return "insufficient"
    if n < MIN_USEFUL_SAMPLE:
        return "early"
    return "useful_history"


def _trend_dimension(opportunity):
    payload = (opportunity or {}).get("payload") or {}
    reversal = payload.get("reversal") or {}
    metrics = reversal.get("metrics") or {}
    return {
        "available": bool(reversal),
        "regime": reversal.get("regime"),
        "reversal_score": reversal.get("score"),
        "confidence": reversal.get("confidence"),
        "close_date": metrics.get("close_date"),
        "close": metrics.get("close"),
        "ema8": metrics.get("ema8"),
        "ema21": metrics.get("ema21"),
        "rsi14": metrics.get("rsi14"),
        "macd_histogram": metrics.get("macd_histogram"),
        "volume_ratio": metrics.get("volume_ratio"),
        "volume_confirmation": metrics.get("volume_confirmation"),
        "drawdown_pct": metrics.get("drawdown_pct"),
        "higher_low": metrics.get("higher_low"),
        "higher_high": metrics.get("higher_high"),
    }


def _recent_event_risk(ticker):
    cutoff = (datetime.now(timezone.utc) - timedelta(days=RECENT_EVENT_DAYS)).isoformat()
    conn = connect()
    try:
        rows = conn.execute(
            "SELECT event_id,event_type,event_label,materiality_label,materiality_ratio_pct,published_at,title,source_url,raw_payload "
            "FROM event_evidence_events WHERE ticker=? AND published_at>=? ORDER BY published_at DESC LIMIT 20",
            (ticker, cutoff),
        ).fetchall()
    except Exception:
        return {"available": False, "lookback_days": RECENT_EVENT_DAYS, "count": 0, "critical_count": 0, "has_critical_event_risk": False, "items": []}
    finally:
        conn.close()

    items = []
    critical = 0
    for row in rows:
        d = dict(row)
        raw = {}
        try:
            raw = json.loads(d.get("raw_payload") or "{}")
        except Exception:
            raw = {}
        priority = str(raw.get("priority") or "").lower() or None
        if priority == "high":
            critical += 1
        items.append({
            "event_id": d.get("event_id"),
            "event_type": d.get("event_type"),
            "event_label": d.get("event_label"),
            "priority": priority,
            "materiality_label": d.get("materiality_label"),
            "materiality_ratio_pct": d.get("materiality_ratio_pct"),
            "published_at": d.get("published_at"),
            "title": d.get("title"),
            "source_url": d.get("source_url"),
        })
    return {
        "available": True,
        "lookback_days": RECENT_EVENT_DAYS,
        "count": len(items),
        "critical_count": critical,
        "has_critical_event_risk": critical > 0,
        "items": items[:5],
    }


def _opportunity_evidence(ticker):
    conn = connect()
    try:
        rows = [dict(row) for row in conn.execute(
            "SELECT e.id,e.label,c.regime,r.return_pct,m.benchmark_return_pct,m.excess_return_pct,"
            "p.max_drawdown_pct,p.max_runup_pct "
            "FROM opportunity_events e "
            "JOIN opportunity_forward_returns r ON r.event_id=e.id AND r.horizon_days=? "
            "LEFT JOIN opportunity_market_returns m ON m.event_id=e.id AND m.horizon_days=r.horizon_days "
            "LEFT JOIN opportunity_market_context c ON c.event_id=e.id "
            "LEFT JOIN opportunity_path_evidence p ON p.event_id=e.id AND p.horizon_days=r.horizon_days "
            "WHERE e.ticker=? AND r.return_pct IS NOT NULL ORDER BY e.id",
            (HORIZON_DAYS, ticker),
        ).fetchall()]
    except Exception:
        return {
            "available": False,
            "benchmark": "OSEBX",
            "horizon_days": HORIZON_DAYS,
            "sample_n": 0,
            "benchmark_sample_n": 0,
            "maturity": "insufficient",
            "regime_counts": {},
            "regime_coverage_pct": 0.0,
        }
    finally:
        conn.close()

    excess = [_num(r.get("excess_return_pct")) for r in rows]
    excess = [x for x in excess if x is not None]
    returns = [_num(r.get("return_pct")) for r in rows]
    returns = [x for x in returns if x is not None]
    drawdowns = [_num(r.get("max_drawdown_pct")) for r in rows]
    drawdowns = [x for x in drawdowns if x is not None]
    runups = [_num(r.get("max_runup_pct")) for r in rows]
    runups = [x for x in runups if x is not None]
    regimes = {}
    for r in rows:
        regime = str(r.get("regime") or "").strip()
        if regime:
            regimes[regime] = regimes.get(regime, 0) + 1

    n = len(rows)
    return {
        "available": bool(rows),
        "benchmark": "OSEBX",
        "horizon_days": HORIZON_DAYS,
        "sample_n": n,
        "benchmark_sample_n": len(excess),
        "maturity": _maturity(n),
        "mean_return_pct": round(sum(returns) / len(returns), 3) if returns else None,
        "median_return_pct": round(float(median(returns)), 3) if returns else None,
        "mean_excess_return_pct": round(sum(excess) / len(excess), 3) if excess else None,
        "median_excess_return_pct": round(float(median(excess)), 3) if excess else None,
        "positive_excess_rate_pct": round(sum(x > 0 for x in excess) / len(excess) * 100.0, 2) if excess else None,
        "median_max_drawdown_pct": round(float(median(drawdowns)), 3) if drawdowns else None,
        "worst_max_drawdown_pct": round(min(drawdowns), 3) if drawdowns else None,
        "median_max_runup_pct": round(float(median(runups)), 3) if runups else None,
        "best_max_runup_pct": round(max(runups), 3) if runups else None,
        "regime_counts": dict(sorted(regimes.items())),
        "regime_coverage_pct": round(sum(regimes.values()) / n * 100.0, 2) if n else 0.0,
    }


def build_shadow(ticker):
    result = _BASE_BUILD(ticker)
    if result.get("status") == "invalid":
        return result

    ticker = result["ticker"]
    opportunity = shadow._opportunity(ticker)
    trend = _trend_dimension(opportunity)
    event_risk = _recent_event_risk(ticker)
    evidence = _opportunity_evidence(ticker)

    dimensions = dict(result.get("dimensions") or {})
    dimensions["trend"] = trend
    dimensions["recent_event_risk"] = event_risk
    dimensions["opportunity_evidence"] = evidence
    dimensions["market_regime_evidence"] = {
        "available": bool(evidence.get("regime_counts")),
        "regime_counts": evidence.get("regime_counts") or {},
        "coverage_pct": evidence.get("regime_coverage_pct", 0.0),
        "note": "Regime labels are captured point-in-time from OSEBX context; missing regimes remain missing.",
    }

    blockers = list(result.get("blockers") or [])
    if not trend.get("available"):
        blockers.append("missing_trend_context")
    if evidence.get("sample_n", 0) < MIN_USEFUL_SAMPLE:
        blockers.append("insufficient_20d_opportunity_evidence")
    if evidence.get("benchmark_sample_n", 0) < MIN_USEFUL_SAMPLE:
        blockers.append("insufficient_20d_benchmark_evidence")
    if event_risk.get("has_critical_event_risk"):
        blockers.append("current_critical_event_risk")
    blockers = list(dict.fromkeys(blockers))

    result = dict(result)
    result["model"] = MODEL_VERSION
    result["dimensions"] = dimensions
    result["blockers"] = blockers
    result["activation"] = {
        "enabled": False,
        "reason": "Shadow-only. Activation requires pre-registered rules, adequate forward sample size, benchmark-relative edge, regime diversity and acceptable path risk.",
    }
    result["policy"] = (
        "Research-only evidence assembly. Trend, event risk, OSEBX excess return, MAE/MFE-style path evidence and regime coverage are descriptive only; "
        "no buy/sell signal, stock-score change, threshold tuning or position sizing."
    )
    result["generated_at"] = datetime.now(timezone.utc).isoformat()
    return result


def install():
    if getattr(shadow, "_high_conviction_evidence_v2", False):
        return
    shadow.build_shadow = build_shadow
    shadow.MODEL_VERSION = MODEL_VERSION
    shadow._high_conviction_evidence_v2 = True


install()
