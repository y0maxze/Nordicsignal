"""Temporal-independence gate for Opportunity learning.

A large number of observations emitted during the same market episode must not be
mistaken for equally many independent validation samples. This layer keeps every raw
event and return, but blocks calibration readiness when observations are concentrated
on too few dates or inside one short calendar window.

Measurement only: no live score, signal threshold, push or event-generation effect.
"""
from __future__ import annotations

from collections import Counter
from datetime import date, datetime, timedelta

import opportunity_tracking_runtime as tracking
import opportunity_versioned_learning_runtime as versioned

REQUIRED_HORIZONS = (5, 10, 20)
MIN_UNIQUE_EVENT_DAYS = 8
MIN_CALENDAR_SPAN_DAYS = 30
MAX_SINGLE_DAY_SHARE_PCT = 25.0
CLUSTER_WINDOW_DAYS = 7
MAX_CLUSTER_WINDOW_SHARE_PCT = 50.0
POLICY_VERSION = "temporal-independence-v1"

_BASE_REPORT = tracking.opportunity_performance


def _day(value):
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date()
    except ValueError:
        try:
            return datetime.strptime(text[:10], "%Y-%m-%d").date()
        except ValueError:
            return None


def _largest_window_count(days, window_days=CLUSTER_WINDOW_DAYS):
    ordered = sorted(day for day in days if day is not None)
    if not ordered:
        return 0, None, None
    best_count = 0
    best_start = None
    best_end = None
    right = 0
    for left, start in enumerate(ordered):
        if right < left:
            right = left
        limit = start + timedelta(days=max(1, int(window_days)) - 1)
        while right < len(ordered) and ordered[right] <= limit:
            right += 1
        count = right - left
        if count > best_count:
            best_count = count
            best_start = start
            best_end = limit
    return best_count, best_start, best_end


def _temporal_stats(rows, minimum_sample=20):
    rows = [dict(row) for row in (rows or [])]
    days = [_day(row.get("event_date") or row.get("observed_at") or row.get("created_at")) for row in rows]
    days = [item for item in days if item is not None]
    n = len(rows)
    dated_n = len(days)
    counts = Counter(days)
    unique_days = len(counts)
    largest_day_count = max(counts.values(), default=0)
    largest_day_share = (largest_day_count / n * 100.0) if n else 0.0
    span_days = ((max(days) - min(days)).days + 1) if days else 0
    cluster_count, cluster_start, cluster_end = _largest_window_count(days)
    cluster_share = (cluster_count / n * 100.0) if n else 0.0

    checks = {
        "minimum_sample": n >= int(minimum_sample),
        "dated_observations_complete": dated_n == n and n > 0,
        "unique_event_days": unique_days >= MIN_UNIQUE_EVENT_DAYS,
        "calendar_span": span_days >= MIN_CALENDAR_SPAN_DAYS,
        "single_day_concentration": largest_day_share <= MAX_SINGLE_DAY_SHARE_PCT if n else False,
        "seven_day_cluster_concentration": cluster_share <= MAX_CLUSTER_WINDOW_SHARE_PCT if n else False,
    }
    if not checks["minimum_sample"]:
        status = "COLLECTING_DATA"
    elif all(checks.values()):
        status = "PASS"
    else:
        status = "REVIEW"

    return {
        "status": status,
        "observations": n,
        "dated_observations": dated_n,
        "unique_event_days": unique_days,
        "calendar_span_days": span_days,
        "largest_single_day": str(counts.most_common(1)[0][0]) if counts else None,
        "largest_single_day_count": largest_day_count,
        "largest_single_day_share_pct": round(largest_day_share, 2),
        "largest_cluster_window_start": str(cluster_start) if cluster_start else None,
        "largest_cluster_window_end": str(cluster_end) if cluster_end else None,
        "largest_cluster_window_count": cluster_count,
        "largest_cluster_window_share_pct": round(cluster_share, 2),
        "checks": checks,
    }


def _active_rows():
    identity = versioned._current_identity()
    model_id = identity["signal_model_id"]
    conn = tracking.connect()
    try:
        rows = conn.execute(
            "SELECT r.horizon_days,e.ticker,e.observed_at,e.created_at,"
            "substr(COALESCE(NULLIF(e.observed_at,''),e.created_at),1,10) AS event_date "
            "FROM opportunity_forward_returns r "
            "JOIN opportunity_events e ON e.id=r.event_id "
            "JOIN opportunity_event_versions v ON v.event_id=e.id "
            "WHERE v.signal_model_id=? AND r.horizon_days IN (5,10,20) AND r.return_pct IS NOT NULL",
            (model_id,),
        ).fetchall()
        return identity, [dict(row) for row in rows]
    finally:
        conn.close()


def opportunity_performance(limit=100):
    report = _BASE_REPORT(limit)
    calibration = report.setdefault("calibration", {})
    minimum_sample = int(calibration.get("minimum_sample_size") or 20)
    prior_ready = bool(calibration.get("ready"))

    try:
        identity, rows = _active_rows()
        query_error = None
    except Exception as exc:
        identity = versioned._current_identity()
        rows = []
        query_error = type(exc).__name__

    grouped = {h: [] for h in REQUIRED_HORIZONS}
    for row in rows:
        try:
            horizon = int(row.get("horizon_days") or 0)
        except (TypeError, ValueError):
            continue
        if horizon in grouped:
            grouped[horizon].append(row)

    horizons = {
        str(h): _temporal_stats(grouped[h], minimum_sample)
        for h in REQUIRED_HORIZONS
    }
    temporal_ready = all(horizons[str(h)]["status"] == "PASS" for h in REQUIRED_HORIZONS)
    if query_error:
        status = "REVIEW" if prior_ready else "COLLECTING_DATA"
    else:
        status = "PASS" if temporal_ready else ("REVIEW" if prior_ready else "COLLECTING_DATA")

    report["temporal_independence_gate"] = {
        "status": status,
        "ready": temporal_ready,
        "active_signal_model_id": identity.get("signal_model_id"),
        "horizons": horizons,
        "criteria": {
            "required_horizons": list(REQUIRED_HORIZONS),
            "minimum_unique_event_days": MIN_UNIQUE_EVENT_DAYS,
            "minimum_calendar_span_days": MIN_CALENDAR_SPAN_DAYS,
            "maximum_single_event_day_share_pct": MAX_SINGLE_DAY_SHARE_PCT,
            "cluster_window_calendar_days": CLUSTER_WINDOW_DAYS,
            "maximum_cluster_window_share_pct": MAX_CLUSTER_WINDOW_SHARE_PCT,
            "date_basis": "first-observed Opportunity event date for active signal model only",
        },
        "query_error": query_error,
        "meaning": (
            "Validation observations are sufficiently distributed through time."
            if temporal_ready
            else "Do not treat clustered observations from the same market episode as independent evidence."
        ),
        "automatic_threshold_changes": False,
        "score_effect": 0,
        "policy_version": POLICY_VERSION,
    }

    calibration["pre_temporal_ready"] = prior_ready
    calibration["temporal_independence_ready"] = temporal_ready
    calibration["ready"] = prior_ready and temporal_ready
    calibration["rule"] = (
        str(calibration.get("rule") or "").rstrip() +
        " Temporal independence must also pass across 5d, 10d and 20d before calibration review."
    ).strip()

    quality = report.get("quality_gate") or {}
    if quality:
        checks = quality.setdefault("checks", {})
        checks["temporal_independence"] = temporal_ready
        if not temporal_ready and str(quality.get("status") or "") == "PASS_CANDIDATE":
            quality["status"] = "REVIEW" if prior_ready else "COLLECTING_DATA"
            quality["quality_pass_candidate"] = False
            quality["meaning"] = "Statistical checks may pass, but observations remain too concentrated in time."
        report["quality_gate"] = quality

    report["policy"] = "measurement_only_manual_calibration_review_with_temporal_independence"
    return report


def install():
    tracking.opportunity_performance = opportunity_performance


install()
