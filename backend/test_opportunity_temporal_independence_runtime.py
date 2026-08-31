from datetime import date, timedelta

import opportunity_temporal_independence_runtime as temporal


def rows_from_days(days):
    return [{"event_date": str(day)} for day in days]


def test_collecting_until_minimum_sample():
    start = date(2026, 1, 1)
    stats = temporal._temporal_stats(rows_from_days([start + timedelta(days=i * 5) for i in range(10)]), 20)
    assert stats["status"] == "COLLECTING_DATA"
    assert stats["checks"]["minimum_sample"] is False


def test_same_day_concentration_fails_review():
    start = date(2026, 1, 1)
    days = [start] * 8 + [start + timedelta(days=5 * i) for i in range(1, 13)]
    stats = temporal._temporal_stats(rows_from_days(days), 20)
    assert stats["status"] == "REVIEW"
    assert stats["largest_single_day_share_pct"] == 40.0
    assert stats["checks"]["single_day_concentration"] is False


def test_seven_day_cluster_concentration_fails_even_with_many_dates():
    start = date(2026, 1, 1)
    clustered = [start + timedelta(days=i % 7) for i in range(12)]
    spread = [start + timedelta(days=14 + i * 7) for i in range(8)]
    stats = temporal._temporal_stats(rows_from_days(clustered + spread), 20)
    assert stats["status"] == "REVIEW"
    assert stats["unique_event_days"] >= 8
    assert stats["largest_cluster_window_share_pct"] == 60.0
    assert stats["checks"]["seven_day_cluster_concentration"] is False


def test_short_calendar_span_fails_review():
    start = date(2026, 1, 1)
    days = [start + timedelta(days=i) for i in range(20)]
    stats = temporal._temporal_stats(rows_from_days(days), 20)
    assert stats["status"] == "REVIEW"
    assert stats["calendar_span_days"] == 20
    assert stats["checks"]["calendar_span"] is False


def test_distributed_sample_passes():
    start = date(2026, 1, 1)
    days = [start + timedelta(days=i * 4) for i in range(20)]
    stats = temporal._temporal_stats(rows_from_days(days), 20)
    assert stats["status"] == "PASS"
    assert stats["unique_event_days"] == 20
    assert stats["calendar_span_days"] >= 30
    assert stats["largest_single_day_share_pct"] == 5.0
    assert stats["largest_cluster_window_share_pct"] <= 50.0
    assert all(stats["checks"].values())


def test_missing_event_dates_fail_completeness_after_sample_threshold():
    rows = [{"event_date": None} for _ in range(20)]
    stats = temporal._temporal_stats(rows, 20)
    assert stats["status"] == "REVIEW"
    assert stats["checks"]["dated_observations_complete"] is False


def test_runtime_policy_never_changes_score_or_thresholds():
    assert temporal.POLICY_VERSION == "temporal-independence-v1"
    assert temporal.REQUIRED_HORIZONS == (5, 10, 20)
    assert temporal.MAX_SINGLE_DAY_SHARE_PCT == 25.0
    assert temporal.MAX_CLUSTER_WINDOW_SHARE_PCT == 50.0
