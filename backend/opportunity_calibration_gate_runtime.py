"""Conservative calibration-readiness diagnostics for Early Opportunity.

This layer never changes Opportunity thresholds or the aggregate stock score.
It evaluates whether the settled forward sample is large and internally consistent
enough to justify a human calibration review.
"""

import opportunity_performance_v2_runtime as performance

MIN_POSITIVE_RATE_PCT = 55.0
MIN_POSITIVE_HORIZONS = 2
MIN_LABELS_WITH_SUPPORT = 2
MIN_LABEL_SUPPORT = 5
DIVERSITY_HORIZON = 10


def _quality_gate(report):
    calibration = report.get("calibration") or {}
    horizons = report.get("horizons") or {}
    by_label = report.get("by_label") or {}
    required = [int(x) for x in (calibration.get("required_horizons") or performance.CALIBRATION_HORIZONS)]
    minimum_sample = int(calibration.get("minimum_sample_size") or performance.MIN_CALIBRATION_SAMPLE)

    sample_counts = {str(h): int((horizons.get(str(h)) or {}).get("n") or 0) for h in required}
    sample_ready = all(sample_counts[str(h)] >= minimum_sample for h in required)

    positive_median_horizons = []
    positive_rate_horizons = []
    for horizon in required:
        stats = horizons.get(str(horizon)) or {}
        median_value = stats.get("median_return_pct")
        positive_rate = stats.get("positive_rate_pct")
        if median_value is not None and float(median_value) > 0:
            positive_median_horizons.append(horizon)
        if positive_rate is not None and float(positive_rate) >= MIN_POSITIVE_RATE_PCT:
            positive_rate_horizons.append(horizon)

    supported_labels = []
    for label, item in by_label.items():
        stats = (item.get("horizons") or {}).get(str(DIVERSITY_HORIZON)) or {}
        if int(stats.get("n") or 0) >= MIN_LABEL_SUPPORT:
            supported_labels.append(label)

    checks = {
        "sample_ready": sample_ready,
        "positive_median_consistency": len(positive_median_horizons) >= MIN_POSITIVE_HORIZONS,
        "positive_rate_consistency": len(positive_rate_horizons) >= MIN_POSITIVE_HORIZONS,
        "signal_level_diversity": len(supported_labels) >= MIN_LABELS_WITH_SUPPORT,
    }

    if not sample_ready:
        status = "COLLECTING_DATA"
    elif all(checks.values()):
        status = "PASS_CANDIDATE"
    else:
        status = "REVIEW"

    return {
        "status": status,
        "ready_for_human_review": sample_ready,
        "quality_pass_candidate": status == "PASS_CANDIDATE",
        "automatic_threshold_changes": False,
        "manual_review_required": True,
        "checks": checks,
        "sample_counts": sample_counts,
        "positive_median_horizons": positive_median_horizons,
        "positive_rate_horizons": positive_rate_horizons,
        "supported_signal_levels": sorted(supported_labels),
        "criteria": {
            "minimum_sample_per_required_horizon": minimum_sample,
            "required_horizons": required,
            "minimum_positive_rate_pct": MIN_POSITIVE_RATE_PCT,
            "minimum_horizons_passing_direction_checks": MIN_POSITIVE_HORIZONS,
            "diversity_horizon": DIVERSITY_HORIZON,
            "minimum_observations_per_supported_signal_level": MIN_LABEL_SUPPORT,
            "minimum_supported_signal_levels": MIN_LABELS_WITH_SUPPORT,
        },
        "meaning": {
            "COLLECTING_DATA": "Not enough settled forward observations for calibration review.",
            "REVIEW": "Sample size is sufficient, but one or more robustness checks are not yet satisfied.",
            "PASS_CANDIDATE": "Sample and robustness checks support a human calibration review; no thresholds change automatically.",
        }[status],
    }


def opportunity_performance(limit=100):
    report = performance.opportunity_performance(limit)
    report["quality_gate"] = _quality_gate(report)
    report["policy"] = "measurement_only_manual_calibration_review"
    return report


def install():
    # v2 remains the calculation source; this wraps report output only.
    performance.tracking.opportunity_performance = opportunity_performance


install()
