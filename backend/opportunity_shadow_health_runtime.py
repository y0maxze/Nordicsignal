"""Operational health checks for the Opportunity shadow collection pipeline.

Research readiness can legitimately stay COLLECTING_DATA for weeks. These checks ask
a different question: is today's shadow collection complete and did each expected
ticker actually run? They are read-only and have no signal, score or calibration
effect.
"""
from __future__ import annotations

import opportunity_learning_health_runtime as health
import opportunity_shadow_dataset_runtime as shadow
import opportunity_shadow_scan_audit_runtime as scan_audit

_BASE_HEALTH = health.learning_health


def shadow_collection_check():
    status = shadow.shadow_status()
    gate = dict(status.get("quality_gate") or {})
    smart = dict(status.get("smart_money") or {})
    snapshots = int(status.get("active_model_snapshots") or 0)
    duplicate_groups = int(gate.get("duplicate_snapshot_groups") or 0)
    feature_pct = float(gate.get("feature_completeness_pct") or 0.0)
    context_pct = float(gate.get("market_context_coverage_pct") or 0.0)
    smart_missing = int(smart.get("missing_sidecar") or 0) if not smart.get("error") else snapshots
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
        "smart_money_sidecar_complete": snapshots == 0 or smart_missing == 0,
    }
    if duplicate_groups:
        state = "FAIL"
    elif not snapshots or not checks["latest_universe_coverage"]:
        state = "WARN"
    elif not checks["feature_completeness"] or not checks["market_context_coverage"] or not checks["smart_money_sidecar_complete"]:
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
        "smart_money_missing_sidecar": smart_missing,
        "smart_money_quality_counts": dict(smart.get("quality_counts") or {}),
        "duplicate_snapshot_groups": duplicate_groups,
        "research_quality_status": gate.get("status") or "COLLECTING_DATA",
        "research_ready": bool(gate.get("ready_for_counterfactual_research")),
        "rule": "operational shadow health checks current collection completeness including Smart Money sidecar; 40-day research maturity is reported but does not itself cause WARN",
    }


def shadow_scan_audit_check():
    report = scan_audit.scan_audit_status()
    latest = dict(report.get("latest_run") or {})
    state = str(report.get("operational_status") or "FAIL")
    if state == "COLLECTING_DATA":
        state = "NOT_APPLICABLE"
    return {
        "status": state,
        "run_status": latest.get("run_status"),
        "started_at": latest.get("started_at"),
        "completed_at": latest.get("completed_at"),
        "expected_tickers": int(latest.get("expected_tickers") or 0),
        "result_rows": int(latest.get("result_rows") or 0),
        "snapshot_present": int(latest.get("snapshot_present") or 0),
        "snapshot_coverage_pct": float(latest.get("snapshot_coverage_pct") or 0.0),
        "not_scanned_tickers": list(report.get("missing_tickers") or []),
        "failed_tickers": list(report.get("failed_tickers") or []),
        "snapshot_missing_tickers": list(report.get("snapshot_missing_tickers") or []),
        "outcome_counts": dict(report.get("outcome_counts") or {}),
        "failures": list(report.get("failures") or [])[:10],
        "rule": "every active ticker should produce one audited result; not-scanned is FAIL, per-ticker scan/result/snapshot failures are WARN",
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
    try:
        checks["shadow_scan_audit"] = shadow_scan_audit_check()
    except Exception as exc:
        checks["shadow_scan_audit"] = {"status": "FAIL", "error": str(exc)}
        errors.append("shadow_scan_audit")
    report["learning_pipeline_status"] = health._overall_status(checks)
    return report


def install():
    health.learning_health = learning_health


install()
