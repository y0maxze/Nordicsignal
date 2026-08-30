"""Wire statistical confidence into version-isolated Opportunity Learning.

The signal cohort stays unchanged; this is a new learning-policy layer. It wraps the
versioned report, computes confidence only from the active signal-model cohort and
requires statistical support before calibration.ready can become true.
"""
from __future__ import annotations

import opportunity_statistical_confidence_runtime as confidence
import opportunity_tracking_runtime as tracking
import opportunity_version_identity_runtime as identity_runtime
import opportunity_versioned_learning_runtime as versioned

LEARNING_POLICY_VERSION = "learning-policy-v5-statistical-confidence"

_BASE_REPORT = tracking.opportunity_performance
_BASE_IDENTITY = identity_runtime._current_identity


def _current_identity():
    base = dict(_BASE_IDENTITY())
    policy_fingerprint = versioned._fingerprint([
        base.get("learning_policy_fingerprint"),
        LEARNING_POLICY_VERSION,
        versioned._source_text(confidence._wilson_interval),
        versioned._source_text(confidence._median_interval),
        versioned._source_text(confidence._series_confidence),
        versioned._source_text(confidence.confidence_gate),
        confidence.CONFIDENCE_LEVEL,
        confidence.MIN_REQUIRED_HORIZONS,
        confidence.NULL_POSITIVE_RATE_PCT,
    ])
    base["learning_policy_version"] = LEARNING_POLICY_VERSION
    base["learning_policy_fingerprint"] = policy_fingerprint
    base["learning_policy_id"] = f"{LEARNING_POLICY_VERSION}:{policy_fingerprint}"
    scope = str(base.get("identity_scope") or "signal_rules")
    base["identity_scope"] = f"{scope}+statistical_confidence_policy"
    return base


def _active_rows(model_id):
    conn = tracking.connect()
    try:
        return [dict(row) for row in conn.execute(
            "SELECT r.horizon_days,r.return_pct,m.excess_return_pct "
            "FROM opportunity_forward_returns r "
            "JOIN opportunity_events e ON e.id=r.event_id "
            "JOIN opportunity_event_versions v ON v.event_id=e.id "
            "LEFT JOIN opportunity_market_returns m ON m.event_id=r.event_id AND m.horizon_days=r.horizon_days "
            "WHERE v.signal_model_id=? AND r.return_pct IS NOT NULL",
            (model_id,),
        ).fetchall()]
    finally:
        conn.close()


def opportunity_performance(limit=100):
    report = _BASE_REPORT(limit)
    identity = _current_identity()
    calibration = report.setdefault("calibration", {})
    required = [int(value) for value in (calibration.get("required_horizons") or versioned.REQUIRED_HORIZONS)]
    minimum_sample = int(calibration.get("minimum_sample_size") or versioned.MIN_SAMPLE)

    rows = _active_rows(identity["signal_model_id"])
    gate = confidence.confidence_gate(rows, required, minimum_sample)
    report["statistical_confidence_gate"] = gate

    pre_statistical_ready = bool(calibration.get("ready"))
    final_ready = bool(pre_statistical_ready and gate.get("ready"))
    calibration["pre_statistical_ready"] = pre_statistical_ready
    calibration["statistical_confidence_ready"] = bool(gate.get("ready"))
    calibration["ready"] = final_ready
    calibration["rule"] = (
        "Only the active verified signal-model cohort counts. Sample size, ticker/sector independence, "
        "market-regime diversity and the 95% statistical confidence gate must all pass before human threshold review."
    )

    quality = report.setdefault("quality_gate", {})
    checks = quality.setdefault("checks", {})
    checks["statistical_confidence"] = bool(gate.get("ready"))
    quality["ready_for_human_review"] = final_ready
    if not gate.get("ready") and quality.get("status") == "PASS_CANDIDATE":
        quality["status"] = "REVIEW" if pre_statistical_ready else "COLLECTING_DATA"
        quality["quality_pass_candidate"] = False
    if final_ready and quality.get("status") == "PASS_CANDIDATE":
        quality["quality_pass_candidate"] = True
    quality["meaning"] = (
        "The active model passes sample, independence, market-regime and 95% statistical-confidence gates for human review; no thresholds change automatically."
        if final_ready else
        "The active model is not yet statistically robust enough for threshold review, or an earlier evidence gate still fails."
    )

    versioning = report.get("versioning") or {}
    if versioning.get("active_model") is not None:
        versioning["active_model"] = identity
    report["versioning"] = versioning
    report["policy"] = "version_isolated_statistical_confidence_manual_calibration_review"
    return report


def install():
    identity_runtime._current_identity = _current_identity
    versioned._current_identity = _current_identity
    tracking.opportunity_performance = opportunity_performance


install()
