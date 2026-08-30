"""Operational health check for the Opportunity shadow collection pipeline.

Research readiness can legitimately stay COLLECTING_DATA for weeks. This check asks a
different question: is today's shadow collection complete and internally healthy?
It is read-only and has no signal, score or calibration effect.
"""
from __future__ import annotations

import opportunity_learning_health_runtime as health
import opportunity_shadow_dataset_runtime as shadow

_BASE_HEALTH = health.learning_health


def shadow_collection_check():
    status = shadow.shadow_status()
    gate = dict(status.get("quality_gate") or {})
    snapshots = int(status.get("active_model_snapshots") or 0)
    duplicate_groups = int(gate.get("duplicate_snapshot_groups") or 0)
    feature_pct = float(gate.get("feature_completeness_pct") or 0.0)
    context_pct = float(gate.get("market_context_coverage_pct") or 0.0)
    daily = list(gate.get("daily_coverage") or [])
    latest = dict(daily[-1]) if daily else {}
    latest_coverage = float(latest.get("coverage_pct") or 0.0)
    universe_target = float((gate.get("thresholds") or {}).get("daily_universe_coverage_pct") or 90.0)
    feature_target = float((gate.get("thresholds") or {}).get("feature_completeness_pct") or 98.0)
    context_target = float((gate.get("thresholds") or {}).get("market_context_coverage_pct") or 95.0)

    checks = {
        "has_snapshots": snapshots > 0,
        "latest_universe_coverage": bool(latest) and latest_coverage >= universe_target,
        "no_duplicate_groups": duplicate_groups == 0,
        "feature_completeness": snapshots > 0 and feature_pct >= feature_target,
        "market_context_coverage": snapshots > 0 and context_pct >= context_target,
    }
    if duplicate_groups:
        state = "FAIL"
    elif not snapshots or not checks["latest_universe_coverage"]:
        state = "WARN"
    elif not checks["feature_completeness"] or not checks["market_context_coverage"]:
        state = "WARN"
    else:
        state = "PASS"

    return {
        "status": state,
        "checks": checks,
        "active_model_snapshots": snapshots,
        "active_model_tickers": int(status.get("active_model_tickers") or 0),
        "first_market_date": status.get("first_market_date"),
        "last_market_date": status.get("last_market_date"),
        "latest_market_date": latest.get("market_date"),
        "latest_tickers": int(latest.get("tickers") or 0),
        "latest_universe_coverage_pct": latest_coverage,
        "required_latest_universe_coverage_pct": universe_target,
        "feature_completeness_pct": feature_pct,
        "required_feature_completeness_pct": feature_target,
        "market_context_coverage_pct": context_pct,
        "required_market_context_coverage_pct": context_target,
        "duplicate_snapshot_groups": duplicate_groups,
        "research_quality_status": gate.get("status") or "COLLECTING_DATA",
        "research_ready": bool(gate.get("ready_for_counterfactual_research")),
        "rule": "operational shadow health checks current collection completeness; 40-day research maturity is reported but does not itself cause WARN",
    }


def learning_health():
    report = _BASE_HEALTH()
    checks = report.setdefault("checks", {})
    errors = report.setdefault("errors", [])
    try:
        checks["shadow_collection"] = shadow_collection_check()
    except Exception as exc:
        checks["shadow_collection"] = {"status": "FAIL", "error": str(exc)}
        errors.append("shadow_collection")
    report["learning_pipeline_status"] = health._overall_status(checks)
    return report


def install():
    health.learning_health = learning_health


install()
