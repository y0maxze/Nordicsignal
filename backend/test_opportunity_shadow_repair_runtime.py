import opportunity_shadow_repair_runtime as repair


def test_successful_result_never_recalculates(monkeypatch):
    calls = {"capture": 0}
    monkeypatch.setattr(repair.audit, "_market_date", lambda result: "2026-08-30")
    monkeypatch.setattr(repair.audit, "_snapshot_present", lambda model, ticker, day: True)
    monkeypatch.setattr(repair.audit, "_record_result", lambda *args, **kwargs: None)
    monkeypatch.setattr(repair, "_record_repair", lambda *args, **kwargs: None)
    monkeypatch.setattr(repair.shadow, "capture_snapshot", lambda result: calls.__setitem__("capture", calls["capture"] + 1))
    repair._finalize_success("run", "model", "AAA", {"status": "ok"})
    assert calls["capture"] == 0


def test_missing_snapshot_gets_one_direct_capture(monkeypatch):
    states = iter([False, True])
    captures = []
    repairs = []
    monkeypatch.setattr(repair.audit, "_market_date", lambda result: "2026-08-30")
    monkeypatch.setattr(repair.audit, "_snapshot_present", lambda model, ticker, day: next(states))
    monkeypatch.setattr(repair.shadow, "capture_snapshot", lambda result: captures.append(result) or {"captured": True})
    monkeypatch.setattr(repair, "_record_repair", lambda *args: repairs.append(args))
    monkeypatch.setattr(repair.audit, "_record_result", lambda *args, **kwargs: None)
    result = {"status": "ok", "ticker": "AAA"}
    repair._finalize_success("run", "model", "AAA", result)
    assert captures == [result]
    assert len(repairs) == 1
    assert repairs[0][2:] == ("SNAPSHOT_CAPTURE", "SUCCESS")


def test_failed_scan_retries_only_once(monkeypatch):
    calls = []
    recorded = []
    monkeypatch.setattr(repair.tracking, "_scan_one", lambda row: calls.append(row) or {"status": "error"})
    monkeypatch.setattr(repair, "_record_repair", lambda *args: recorded.append(args))
    monkeypatch.setattr(repair.audit, "_record_result", lambda *args, **kwargs: None)
    monkeypatch.setattr(repair.audit, "_market_date", lambda result: None)
    repair._retry_failed_scan("run", "model", {"ticker": "AAA"}, "SCAN_ERROR_RETRY")
    assert len(calls) == 1
    assert len(recorded) == 1
    assert recorded[0][3] == "FAILED"


def test_retry_success_finishes_with_snapshot(monkeypatch):
    repairs = []
    finalized = []
    monkeypatch.setattr(repair.tracking, "_scan_one", lambda row: {"status": "ok", "ticker": row["ticker"]})
    monkeypatch.setattr(repair, "_record_repair", lambda *args: repairs.append(args))
    monkeypatch.setattr(repair, "_finalize_success", lambda *args: finalized.append(args))
    repair._retry_failed_scan("run", "model", {"ticker": "AAA"}, "SCAN_ERROR_RETRY")
    assert len(repairs) == 1
    assert repairs[0][3] == "SUCCESS"
    assert len(finalized) == 1


def test_status_reports_bounded_policy(monkeypatch):
    monkeypatch.setattr(repair, "_BASE_STATUS", lambda: {"latest_run": {"run_id": "run"}})
    monkeypatch.setattr(repair, "_repair_rows", lambda run_id: [
        {"ticker": "AAA", "repair_reason": "SCAN_ERROR_RETRY", "repair_status": "SUCCESS"},
        {"ticker": "BBB", "repair_reason": "SNAPSHOT_CAPTURE", "repair_status": "FAILED"},
    ])
    report = repair.scan_audit_status_with_repairs()
    assert report["bounded_repair"]["maximum_live_retry_per_failed_ticker"] == 1
    assert report["bounded_repair"]["successful_tickers_are_recalculated"] is False
    assert report["bounded_repair"]["attempts"] == 2
    assert report["bounded_repair"]["successes"] == 1
    assert report["bounded_repair"]["failures"] == 1
