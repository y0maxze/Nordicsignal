"""Operational health watchdog for the Early Opportunity learning pipeline.

This endpoint answers a different question from Signal Performance: is the data
collection/validation machinery itself alive and internally complete? It checks the
external scheduler heartbeat, discovery cache, model-version stamping, OSEBX market
context and market-adjusted settlement coverage.

It is read-only and never changes scores, signal thresholds, events or calibration.
"""
from __future__ import annotations

from datetime import datetime, timezone

import extra_api
import opportunity_autoscan_runtime as autoscan
import opportunity_data_coverage_runtime as coverage
import opportunity_tracking_runtime as tracking
import opportunity_version_identity_runtime as identity_runtime

SCHEDULER_WARN_MINUTES = 30.0
SCHEDULER_FAIL_MINUTES = 60.0
DISCOVERY_WARN_HOURS = 8.0
DISCOVERY_FAIL_HOURS = 12.0
MARKET_CONTEXT_GRACE_MINUTES = 20.0
MARKET_RETURN_GRACE_MINUTES = 60.0


def _now_dt():
    return datetime.now(timezone.utc)


def _now():
    return _now_dt().isoformat()


def _parse_dt(value):
    if not value:
        return None
    text = str(value).strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _age_minutes(value, now=None):
    parsed = _parse_dt(value)
    if parsed is None:
        return None
    reference = now or _now_dt()
    return max(0.0, (reference - parsed).total_seconds() / 60.0)


def _freshness_status(age_minutes, warn_minutes, fail_minutes):
    if age_minutes is None:
        return "FAIL"
    if age_minutes > fail_minutes:
        return "FAIL"
    if age_minutes > warn_minutes:
        return "WARN"
    return "PASS"


def _overall_status(checks):
    states = {str((item or {}).get("status") or "FAIL") for item in (checks or {}).values()}
    if "FAIL" in states:
        return "DEGRADED"
    if "WARN" in states:
        return "WARN"
    return "HEALTHY"


def _scheduler_check():
    status = autoscan.scheduler_status()
    age = _age_minutes(status.get("last_external_trigger_at"))
    state = _freshness_status(age, SCHEDULER_WARN_MINUTES, SCHEDULER_FAIL_MINUTES)
    return {
        "status": state,
        "last_external_trigger_at": status.get("last_external_trigger_at"),
        "heartbeat_age_minutes": round(age, 2) if age is not None else None,
        "last_scan_state": status.get("last_scan_state"),
        "external_trigger_count": int(status.get("external_trigger_count") or 0),
        "expected_interval_minutes": round(float(status.get("scan_interval_seconds") or 600) / 60.0, 2),
        "rule": f"warn after {SCHEDULER_WARN_MINUTES:.0f}m; fail after {SCHEDULER_FAIL_MINUTES:.0f}m without external heartbeat",
    }


def _discovery_check():
    status = coverage.discovery_status()
    discovery = dict(status.get("discovery") or {})
    meta = dict(discovery.get("meta") or {})
    age_seconds = discovery.get("cache_age_seconds")
    try:
        age_minutes = float(age_seconds) / 60.0 if age_seconds is not None else None
    except (TypeError, ValueError):
        age_minutes = None
    feed_ok = str(meta.get("status") or "").lower() == "ok"
    refreshing = bool(discovery.get("refreshing"))
    freshness = _freshness_status(
        age_minutes,
        DISCOVERY_WARN_HOURS * 60.0,
        DISCOVERY_FAIL_HOURS * 60.0,
    )
    if not feed_ok:
        state = "WARN" if refreshing else "FAIL"
    elif freshness == "FAIL" and refreshing:
        state = "WARN"
    else:
        state = freshness
    return {
        "status": state,
        "feed_status": meta.get("status"),
        "cached_candidates": int(discovery.get("cached_candidates") or 0),
        "cache_age_minutes": round(age_minutes, 2) if age_minutes is not None else None,
        "refreshing": refreshing,
        "refresh_mode": discovery.get("refresh_mode"),
        "announcements_seen": int(meta.get("announcements_seen") or 0),
        "qualified": int(meta.get("qualified") or 0),
        "rule": f"warn after {DISCOVERY_WARN_HOURS:.0f}h; fail after {DISCOVERY_FAIL_HOURS:.0f}h stale unless refresh is running",
    }


def _older_than(rows, field, minutes, now=None):
    reference = now or _now_dt()
    overdue = []
    for row in rows or []:
        age = _age_minutes((row or {}).get(field), reference)
        if age is not None and age > minutes:
            item = dict(row)
            item["age_minutes"] = round(age, 2)
            overdue.append(item)
    return overdue


def _database_checks():
    identity = identity_runtime._current_identity()
    active_model_id = identity["signal_model_id"]
    conn = tracking.connect()
    try:
        total_events = int(conn.execute("SELECT COUNT(*) AS n FROM opportunity_events").fetchone()["n"])
        versioned_events = int(conn.execute("SELECT COUNT(*) AS n FROM opportunity_event_versions").fetchone()["n"])
        unversioned_events = int(conn.execute(
            "SELECT COUNT(*) AS n FROM opportunity_events e LEFT JOIN opportunity_event_versions v ON v.event_id=e.id WHERE v.event_id IS NULL"
        ).fetchone()["n"])
        active_events = int(conn.execute(
            "SELECT COUNT(*) AS n FROM opportunity_event_versions WHERE signal_model_id=?",
            (active_model_id,),
        ).fetchone()["n"])
        legacy_events = int(conn.execute(
            "SELECT COUNT(*) AS n FROM opportunity_event_versions WHERE signal_model_id LIKE 'legacy:%'"
        ).fetchone()["n"])

        missing_context = [dict(row) for row in conn.execute(
            "SELECT e.id,e.ticker,e.created_at FROM opportunity_events e "
            "LEFT JOIN opportunity_market_context c ON c.event_id=e.id WHERE c.event_id IS NULL"
        ).fetchall()]
        settled_total = int(conn.execute(
            "SELECT COUNT(*) AS n FROM opportunity_forward_returns WHERE return_pct IS NOT NULL"
        ).fetchone()["n"])
        missing_market_returns = [dict(row) for row in conn.execute(
            "SELECT r.event_id,r.horizon_days,r.settled_at,e.ticker FROM opportunity_forward_returns r "
            "JOIN opportunity_events e ON e.id=r.event_id "
            "LEFT JOIN opportunity_market_returns m ON m.event_id=r.event_id AND m.horizon_days=r.horizon_days "
            "WHERE r.return_pct IS NOT NULL AND m.event_id IS NULL"
        ).fetchall()]
    finally:
        conn.close()

    overdue_context = _older_than(missing_context, "created_at", MARKET_CONTEXT_GRACE_MINUTES)
    overdue_market_returns = _older_than(missing_market_returns, "settled_at", MARKET_RETURN_GRACE_MINUTES)

    version_state = "PASS" if unversioned_events == 0 else "FAIL"
    context_state = "NOT_APPLICABLE" if total_events == 0 else ("PASS" if not overdue_context else "WARN")
    market_return_state = "NOT_APPLICABLE" if settled_total == 0 else ("PASS" if not overdue_market_returns else "WARN")

    return {
        "model_versioning": {
            "status": version_state,
            "active_model_id": active_model_id,
            "active_model_events": active_events,
            "legacy_unverified_events": legacy_events,
            "total_events": total_events,
            "version_rows": versioned_events,
            "unversioned_events": unversioned_events,
            "rule": "every Opportunity event must have exactly one model-version record; legacy is allowed but unversioned is not",
        },
        "market_context": {
            "status": context_state,
            "total_events": total_events,
            "missing_context": len(missing_context),
            "overdue_missing_context": len(overdue_context),
            "grace_minutes": MARKET_CONTEXT_GRACE_MINUTES,
            "examples": overdue_context[:5],
        },
        "market_adjustment": {
            "status": market_return_state,
            "settled_stock_returns": settled_total,
            "missing_market_adjustments": len(missing_market_returns),
            "overdue_missing_market_adjustments": len(overdue_market_returns),
            "grace_minutes": MARKET_RETURN_GRACE_MINUTES,
            "examples": overdue_market_returns[:5],
        },
    }


def learning_health():
    checks = {}
    errors = []
    try:
        checks["scheduler"] = _scheduler_check()
    except Exception as exc:
        checks["scheduler"] = {"status": "FAIL", "error": str(exc)}
        errors.append("scheduler")
    try:
        checks["discovery"] = _discovery_check()
    except Exception as exc:
        checks["discovery"] = {"status": "FAIL", "error": str(exc)}
        errors.append("discovery")
    try:
        checks.update(_database_checks())
    except Exception as exc:
        for key in ("model_versioning", "market_context", "market_adjustment"):
            checks[key] = {"status": "FAIL", "error": str(exc)}
        errors.append("database_validation")

    return {
        "status": "ok",
        "learning_pipeline_status": _overall_status(checks),
        "checks": checks,
        "generated_at": _now(),
        "errors": errors,
        "policy": "read_only_operational_health_no_signal_or_threshold_effect",
    }


def install():
    if getattr(extra_api, "_opportunity_learning_health_runtime", False):
        return
    original_install = extra_api.install

    def patched_install(app):
        original_install(app)

        @app.get("/api/opportunity-learning-health")
        def opportunity_learning_health_route():
            return learning_health()

    extra_api.install = patched_install
    extra_api._opportunity_learning_health_runtime = True


install()
