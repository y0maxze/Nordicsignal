"""Require chronological out-of-sample stability before Opportunity calibration review."""
from __future__ import annotations

import opportunity_statistical_gate_runtime as statistical_gate
import opportunity_tracking_runtime as tracking
import opportunity_version_identity_runtime as identity_runtime
import opportunity_versioned_learning_runtime as versioned
import opportunity_walkforward_runtime as walkforward

LEARNING_POLICY_VERSION = "learning-policy-v6-walk-forward"

_BASE_REPORT = tracking.opportunity_performance
_BASE_IDENTITY = identity_runtime._current_identity


def _current_identity():
    base = dict(_BASE_IDENTITY())
    policy_fingerprint = versioned._fingerprint([
        base.get("learning_policy_fingerprint"),
        LEARNING_POLICY_VERSION,
        versioned._source_text(walkforward._ordered_horizon_rows),
        versioned._source_text(walkforward._folds),
        versioned._source_text(walkforward._fold_report),
        versioned._source_text(walkforward._horizon_report),
        versioned._source_text(walkforward.walkforward_gate),
        walkforward.INITIAL_TRAIN_EVENTS,
        walkforward.HOLDOUT_EVENTS,
        walkforward.MIN_ELIGIBLE_FOLDS,
        walkforward.MIN_REQUIRED_HORIZONS,
        walkforward.MIN_HOLDOUT_POSITIVE_RATE_PCT,
        walkforward.MIN_FOLD_PASS_RATE,
    ])
    base["learning_policy_version"] = LEARNING_POLICY_VERSION
    base["learning_policy_fingerprint"] = policy_fingerprint
    base["learning_policy_id"] = f"{LEARNING_POLICY_VERSION}:{policy_fingerprint}"
    scope = str(base.get("identity_scope") or "signal_rules")
    base["identity_scope"] = f"{scope}+chronological_walk_forward_policy"
    return base


def _active_rows(model_id):
    conn = tracking.connect()
    try:
        return [dict(row) for row in conn.execute(
            "SELECT r.event_id,r.horizon_days,r.return_pct,e.observed_at,m.excess_return_pct "
            "FROM opportunity_forward_returns r "
            "JOIN opportunity_events e ON e.id=r.event_id "
            "JOIN opportunity_event_versions v ON v.event_id=e.id "
            "LEFT JOIN opportunity_market_returns m ON m.event_id=r.event_id AND m.horizon_days=r.horizon_days "
            "WHERE v.signal_model_id=? AND r.return_pct IS NOT NULL "
            "ORDER BY e.observed_at,e.id,r.horizon_days",
            (model_id,),
        ).fetchall()]
    finally:
        conn.close()


def opportunity_performance(limit=100):
    report = _BASE_REPORT(limit)
    identity = _current_identity()
    calibration = report.setdefault("calibration", {})
    required = [int(value) for value in (calibration.get("required_horizons") or versioned.REQUIRED_HORIZONS)]

    rows = _active_rows(identity["signal_model_id"])
    gate = walkforward.walkforward_gate(rows, required)
    report["walk_forward_gate"] = gate

    pre_walkforward_ready = bool(calibration.get("ready"))
    final_ready = bool(pre_walkforward_ready and gate.get("ready"))
    calibration["pre_walk_forward_ready"] = pre_walkforward_ready
    calibration["walk_forward_ready"] = bool(gate.get("ready"))
    calibration["ready"] = final_ready
    calibration["rule"] = (
        "Only the active verified signal-model cohort counts. Sample, independence, market-regime, 95% statistical "
        "confidence and chronological walk-forward holdout gates must all pass before human threshold review."
    )

    quality = report.setdefault("quality_gate", {})
    checks = quality.setdefault("checks", {})
    checks["walk_forward_stability"] = bool(gate.get("ready"))
    quality["ready_for_human_review"] = final_ready
    if not gate.get("ready"):
        if quality.get("status") == "PASS_CANDIDATE":
            quality["status"] = "REVIEW" if pre_walkforward_ready else "COLLECTING_DATA"
        quality["quality_pass_candidate"] = False
    quality["meaning"] = (
        "The active model passes all current evidence gates including chronological out-of-sample holdouts; no thresholds change automatically."
        if final_ready else
        "The active model still lacks sufficient chronological out-of-sample stability, or an earlier evidence gate still fails."
    )

    versioning = report.get("versioning") or {}
    if versioning.get("active_model") is not None:
        versioning["active_model"] = identity
    report["versioning"] = versioning
    report["policy"] = "version_isolated_statistical_walkforward_manual_calibration_review"
    return report


def install():
    identity_runtime._current_identity = _current_identity
    versioned._current_identity = _current_identity
    tracking.opportunity_performance = opportunity_performance


install()
