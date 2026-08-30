import opportunity_calibration_gate_runtime as gate
import opportunity_performance_v2_runtime as performance
import opportunity_tracking_runtime as tracking


def _report(n=20, median_5=1.0, median_10=1.2, median_20=0.8, rate_5=60.0, rate_10=58.0, rate_20=57.0, label_support=(8, 7, 5)):
    horizons = {
        "5": {"n": n, "median_return_pct": median_5, "positive_rate_pct": rate_5},
        "10": {"n": n, "median_return_pct": median_10, "positive_rate_pct": rate_10},
        "20": {"n": n, "median_return_pct": median_20, "positive_rate_pct": rate_20},
    }
    labels = ["WATCH_CONFLUENCE", "EARLY_OPPORTUNITY", "EARLY_OPPORTUNITY_HIGH"]
    by_label = {
        label: {"horizons": {"10": {"n": support}}}
        for label, support in zip(labels, label_support)
    }
    return {
        "horizons": horizons,
        "by_label": by_label,
        "calibration": {
            "minimum_sample_size": 20,
            "required_horizons": [5, 10, 20],
            "ready": n >= 20,
        },
    }


def test_quality_gate_collects_until_minimum_sample():
    result = gate._quality_gate(_report(n=19))
    assert result["status"] == "COLLECTING_DATA"
    assert result["ready_for_human_review"] is False
    assert result["automatic_threshold_changes"] is False
    assert result["manual_review_required"] is True


def test_quality_gate_pass_candidate_requires_consistency_and_diversity():
    result = gate._quality_gate(_report())
    assert result["status"] == "PASS_CANDIDATE"
    assert result["ready_for_human_review"] is True
    assert result["quality_pass_candidate"] is True
    assert result["checks"] == {
        "sample_ready": True,
        "positive_median_consistency": True,
        "positive_rate_consistency": True,
        "signal_level_diversity": True,
    }
    assert result["positive_median_horizons"] == [5, 10, 20]
    assert result["positive_rate_horizons"] == [5, 10, 20]
    assert len(result["supported_signal_levels"]) == 3


def test_quality_gate_routes_weak_or_concentrated_sample_to_review():
    result = gate._quality_gate(_report(median_5=-1.0, median_10=-0.5, rate_5=48.0, rate_10=50.0, label_support=(20, 0, 0)))
    assert result["status"] == "REVIEW"
    assert result["ready_for_human_review"] is True
    assert result["quality_pass_candidate"] is False
    assert result["checks"]["positive_median_consistency"] is False
    assert result["checks"]["positive_rate_consistency"] is False
    assert result["checks"]["signal_level_diversity"] is False


def test_install_wraps_report_only_without_touching_thresholds():
    gate.install()
    assert tracking.opportunity_performance is gate.opportunity_performance
    assert performance.MIN_CALIBRATION_SAMPLE == 20
    assert gate.MIN_POSITIVE_RATE_PCT == 55.0
    assert gate.MIN_POSITIVE_HORIZONS == 2
