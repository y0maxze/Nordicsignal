"""Quality gate for the research-only Opportunity shadow dataset.

This module never changes live scoring, labels, events, pushes or Learning readiness.
It only answers whether the all-scan shadow dataset is complete enough to be trusted
for future counterfactual threshold research.
"""
from __future__ import annotations

from collections import defaultdict

import opportunity_shadow_dataset_runtime as shadow
import opportunity_tracking_runtime as tracking
import opportunity_version_identity_runtime as identity_runtime

MIN_MARKET_DAYS = 20
DAILY_UNIVERSE_COVERAGE_PCT = 90.0
MIN_COMPLETE_DAY_SHARE_PCT = 90.0
FEATURE_COMPLETENESS_PCT = 98.0
MARKET_CONTEXT_COVERAGE_PCT = 95.0
MATURED_RETURN_COVERAGE_PCT = 95.0
REQUIRED_RETURN_HORIZONS = (5, 10, 20)

_BASE_STATUS = shadow.shadow_status


def _pct(numerator, denominator):
    return round(float(numerator) / float(denominator) * 100.0, 2) if denominator else 0.0


def _rows(model_id):
    conn = tracking.connect()
    try:
        snapshots = [dict(row) for row in conn.execute(
            "SELECT id,ticker,market_date,entry_price,opportunity_score,reversal_score,volume_state,insider_label,market_regime "
            "FROM opportunity_shadow_snapshots WHERE signal_model_id=? ORDER BY market_date,id",
            (model_id,),
        ).fetchall()]
        returns = [dict(row) for row in conn.execute(
            "SELECT r.snapshot_id,r.horizon_days FROM opportunity_shadow_returns r "
            "JOIN opportunity_shadow_snapshots s ON s.id=r.snapshot_id "
            "WHERE s.signal_model_id=? AND r.return_pct IS NOT NULL AND r.excess_return_pct IS NOT NULL",
            (model_id,),
        ).fetchall()]
        active = conn.execute("SELECT COUNT(*) AS n FROM stocks WHERE active=1").fetchone()
        duplicate = conn.execute(
            "SELECT COUNT(*) AS n FROM (SELECT ticker,market_date,COUNT(*) AS c FROM opportunity_shadow_snapshots "
            "WHERE signal_model_id=? GROUP BY ticker,market_date HAVING COUNT(*)>1) q",
            (model_id,),
        ).fetchone()
        return snapshots, returns, int(active["n"] if active else 0), int(duplicate["n"] if duplicate else 0)
    finally:
        conn.close()


def quality_gate():
    model_id = identity_runtime._current_identity().get("signal_model_id")
    snapshots, returns, active_universe, duplicate_groups = _rows(model_id)
    by_date = defaultdict(set)
    for row in snapshots:
        by_date[str(row.get("market_date") or "")].add(str(row.get("ticker") or ""))
    dates = sorted(date for date in by_date if date)

    recent_dates = dates[-MIN_MARKET_DAYS:]
    daily = []
    for date in recent_dates:
        tickers = len(by_date[date])
        coverage = _pct(tickers, active_universe)
        daily.append({"market_date": date, "tickers": tickers, "coverage_pct": coverage, "complete": coverage >= DAILY_UNIVERSE_COVERAGE_PCT})
    complete_days = sum(bool(item["complete"]) for item in daily)
    complete_day_share = _pct(complete_days, len(daily))

    required_features = ("entry_price", "opportunity_score", "reversal_score", "volume_state", "insider_label")
    complete_features = 0
    for row in snapshots:
        if all(row.get(key) is not None and str(row.get(key)) != "" for key in required_features):
            complete_features += 1
    feature_coverage = _pct(complete_features, len(snapshots))
    context_count = sum(row.get("market_regime") not in (None, "") for row in snapshots)
    context_coverage = _pct(context_count, len(snapshots))

    settled = {(int(row["snapshot_id"]), int(row["horizon_days"])) for row in returns}
    date_index = {date: index for index, date in enumerate(dates)}
    return_coverage = {}
    return_checks = []
    for horizon in REQUIRED_RETURN_HORIZONS:
        matured = [
            row for row in snapshots
            if row.get("market_date") in date_index and date_index[row["market_date"]] + horizon < len(dates)
        ]
        settled_n = sum((int(row["id"]), horizon) in settled for row in matured)
        coverage = _pct(settled_n, len(matured))
        passed = bool(matured) and coverage >= MATURED_RETURN_COVERAGE_PCT
        return_checks.append(passed)
        return_coverage[str(horizon)] = {
            "matured_snapshots": len(matured),
            "settled_with_alpha": settled_n,
            "coverage_pct": coverage,
            "pass": passed,
        }

    checks = {
        "minimum_market_days": len(dates) >= MIN_MARKET_DAYS,
        "daily_universe_coverage": len(daily) >= MIN_MARKET_DAYS and complete_day_share >= MIN_COMPLETE_DAY_SHARE_PCT,
        "no_duplicate_snapshot_groups": duplicate_groups == 0,
        "feature_completeness": bool(snapshots) and feature_coverage >= FEATURE_COMPLETENESS_PCT,
        "market_context_coverage": bool(snapshots) and context_coverage >= MARKET_CONTEXT_COVERAGE_PCT,
        "matured_forward_return_coverage": all(return_checks),
    }
    ready = all(checks.values())
    enough_history = len(dates) >= MIN_MARKET_DAYS
    status = "PASS" if ready else ("REVIEW" if enough_history else "COLLECTING_DATA")
    return {
        "status": status,
        "ready_for_counterfactual_research": ready,
        "active_signal_model_id": model_id,
        "thresholds": {
            "minimum_market_days": MIN_MARKET_DAYS,
            "daily_universe_coverage_pct": DAILY_UNIVERSE_COVERAGE_PCT,
            "minimum_complete_day_share_pct": MIN_COMPLETE_DAY_SHARE_PCT,
            "feature_completeness_pct": FEATURE_COMPLETENESS_PCT,
            "market_context_coverage_pct": MARKET_CONTEXT_COVERAGE_PCT,
            "matured_return_coverage_pct": MATURED_RETURN_COVERAGE_PCT,
            "required_return_horizons": list(REQUIRED_RETURN_HORIZONS),
        },
        "checks": checks,
        "market_days": len(dates),
        "evaluated_recent_market_days": len(daily),
        "complete_recent_market_days": complete_days,
        "complete_recent_day_share_pct": complete_day_share,
        "active_universe_tickers": active_universe,
        "daily_coverage": daily,
        "snapshots": len(snapshots),
        "feature_complete_snapshots": complete_features,
        "feature_completeness_pct": feature_coverage,
        "market_context_snapshots": context_count,
        "market_context_coverage_pct": context_coverage,
        "duplicate_snapshot_groups": duplicate_groups,
        "forward_returns": return_coverage,
        "selection_bias_guard": "all successful scans, not only emitted Opportunity events",
        "maturity_policy": "a snapshot is evaluated for Nd settlement only after at least N later shadow market dates exist",
        "automatic_threshold_changes": False,
        "meaning": (
            "Shadow data passes completeness checks and may be used for research-only counterfactual threshold analysis."
            if ready else
            "Shadow data is still collecting or has a completeness gap; do not use it to justify threshold changes yet."
        ),
    }


def shadow_status():
    result = _BASE_STATUS()
    try:
        result["quality_gate"] = quality_gate()
    except Exception as exc:
        result["quality_gate"] = {"status": "DEGRADED", "ready_for_counterfactual_research": False, "error": str(exc), "automatic_threshold_changes": False}
    return result


def install():
    shadow.shadow_status = shadow_status


install()
