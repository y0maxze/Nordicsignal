from datetime import datetime, timedelta, timezone

import opportunity_learning_health_runtime as health
import opportunity_shadow_health_runtime as shadow_health


def test_freshness_thresholds():
    assert health._freshness_status(5, 30, 60) == "PASS"
    assert health._freshness_status(45, 30, 60) == "WARN"
    assert health._freshness_status(61, 30, 60) == "FAIL"
    assert health._freshness_status(None, 30, 60) == "FAIL"


def test_overall_status_prioritizes_fail_then_warn():
    assert health._overall_status({"a": {"status": "PASS"}, "b": {"status": "NOT_APPLICABLE"}}) == "HEALTHY"
    assert health._overall_status({"a": {"status": "PASS"}, "b": {"status": "WARN"}}) == "WARN"
    assert health._overall_status({"a": {"status": "WARN"}, "b": {"status": "FAIL"}}) == "DEGRADED"


def test_age_and_overdue_rows_are_timezone_safe():
    now = datetime(2026, 8, 30, 5, 0, tzinfo=timezone.utc)
    assert round(health._age_minutes("2026-08-30T04:30:00+00:00", now), 2) == 30.0
    assert round(health._age_minutes("2026-08-30T04:30:00Z", now), 2) == 30.0
    rows = [
        {"id": 1, "created_at": "2026-08-30T04:00:00+00:00"},
        {"id": 2, "created_at": "2026-08-30T04:50:00+00:00"},
    ]
    overdue = health._older_than(rows, "created_at", 20, now)
    assert [row["id"] for row in overdue] == [1]
    assert overdue[0]["age_minutes"] == 60.0


def test_learning_health_combines_checks(monkeypatch):
    monkeypatch.setattr(health, "_scheduler_check", lambda: {"status": "PASS"})
    monkeypatch.setattr(health, "_discovery_check", lambda: {"status": "PASS"})
    monkeypatch.setattr(health, "_database_checks", lambda: {
        "model_versioning": {"status": "PASS"},
        "market_context": {"status": "NOT_APPLICABLE"},
        "market_adjustment": {"status": "NOT_APPLICABLE"},
    })
    # sitecustomize intentionally wraps health.learning_health with Shadow checks.
    # This test targets the base watchdog in isolation, so call the preserved base.
    result = shadow_health._BASE_HEALTH()
    assert result["learning_pipeline_status"] == "HEALTHY"
    assert result["errors"] == []
    assert result["policy"] == "read_only_operational_health_no_signal_or_threshold_effect"


def test_learning_health_surfaces_component_failure(monkeypatch):
    def broken():
        raise RuntimeError("database unavailable")

    monkeypatch.setattr(health, "_scheduler_check", lambda: {"status": "PASS"})
    monkeypatch.setattr(health, "_discovery_check", lambda: {"status": "WARN"})
    monkeypatch.setattr(health, "_database_checks", broken)
    result = shadow_health._BASE_HEALTH()
    assert result["learning_pipeline_status"] == "DEGRADED"
    assert "database_validation" in result["errors"]
    assert result["checks"]["model_versioning"]["status"] == "FAIL"
