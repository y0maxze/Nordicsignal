import opportunity_shadow_scan_audit_runtime as audit


def _run(expected=3, status="COMPLETED"):
    return {
        "run_id": "run-1",
        "signal_model_id": "model-1",
        "expected_tickers": expected,
        "started_at": "2026-08-30T10:00:00+00:00",
        "completed_at": "2026-08-30T10:01:00+00:00",
        "run_status": status,
    }


def test_complete_run_passes(monkeypatch):
    rows = [
        {"ticker": "AAA", "outcome": "SNAPSHOT_PRESENT"},
        {"ticker": "BBB", "outcome": "SNAPSHOT_PRESENT"},
        {"ticker": "CCC", "outcome": "SNAPSHOT_PRESENT"},
    ]
    monkeypatch.setattr(audit, "_latest_run", lambda: (_run(), rows))
    monkeypatch.setattr(audit, "_expected_tickers", lambda: ["AAA", "BBB", "CCC"])
    report = audit.scan_audit_status()
    assert report["operational_status"] == "PASS"
    assert report["latest_run"]["snapshot_coverage_pct"] == 100.0
    assert report["missing_tickers"] == []


def test_unattempted_ticker_fails(monkeypatch):
    rows = [
        {"ticker": "AAA", "outcome": "SNAPSHOT_PRESENT"},
        {"ticker": "BBB", "outcome": "SNAPSHOT_PRESENT"},
    ]
    monkeypatch.setattr(audit, "_latest_run", lambda: (_run(), rows))
    monkeypatch.setattr(audit, "_expected_tickers", lambda: ["AAA", "BBB", "CCC"])
    report = audit.scan_audit_status()
    assert report["operational_status"] == "FAIL"
    assert report["missing_tickers"] == ["CCC"]


def test_scan_error_warns(monkeypatch):
    rows = [
        {"ticker": "AAA", "outcome": "SNAPSHOT_PRESENT"},
        {"ticker": "BBB", "outcome": "SCAN_ERROR", "error_class": "RuntimeError", "error_message": "feed failed"},
        {"ticker": "CCC", "outcome": "SNAPSHOT_PRESENT"},
    ]
    monkeypatch.setattr(audit, "_latest_run", lambda: (_run(), rows))
    monkeypatch.setattr(audit, "_expected_tickers", lambda: ["AAA", "BBB", "CCC"])
    report = audit.scan_audit_status()
    assert report["operational_status"] == "WARN"
    assert report["failed_tickers"] == ["BBB"]


def test_snapshot_missing_warns(monkeypatch):
    rows = [
        {"ticker": "AAA", "outcome": "SNAPSHOT_PRESENT"},
        {"ticker": "BBB", "outcome": "SNAPSHOT_MISSING"},
        {"ticker": "CCC", "outcome": "SNAPSHOT_PRESENT"},
    ]
    monkeypatch.setattr(audit, "_latest_run", lambda: (_run(), rows))
    monkeypatch.setattr(audit, "_expected_tickers", lambda: ["AAA", "BBB", "CCC"])
    report = audit.scan_audit_status()
    assert report["operational_status"] == "WARN"
    assert report["snapshot_missing_tickers"] == ["BBB"]


def test_failed_run_fails(monkeypatch):
    monkeypatch.setattr(audit, "_latest_run", lambda: (_run(status="FAILED"), []))
    monkeypatch.setattr(audit, "_expected_tickers", lambda: ["AAA", "BBB", "CCC"])
    assert audit.scan_audit_status()["operational_status"] == "FAIL"
