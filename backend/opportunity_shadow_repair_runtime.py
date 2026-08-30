"""Bounded repair pass for per-ticker Opportunity shadow collection failures.

Only failed/missing work is retried. Successful tickers are never recalculated. A
scan/result failure receives at most one additional live scan attempt. A successful
calculation whose shadow snapshot is missing receives only one direct snapshot
capture attempt, avoiding a second signal calculation.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
import uuid

import opportunity_shadow_dataset_runtime as shadow
import opportunity_shadow_scan_audit_runtime as audit
import opportunity_tracking_runtime as tracking
import opportunity_version_identity_runtime as identity_runtime

_BASE_STATUS = audit.scan_audit_status


def _ensure_schema():
    conn = tracking.connect()
    try:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS opportunity_shadow_scan_repairs (
          run_id TEXT NOT NULL,
          ticker TEXT NOT NULL,
          repair_reason TEXT NOT NULL,
          repair_status TEXT NOT NULL,
          created_at TEXT NOT NULL,
          PRIMARY KEY(run_id,ticker,repair_reason)
        );
        """)
        conn.commit()
    finally:
        conn.close()


def _record_repair(run_id, ticker, reason, status):
    conn = tracking.connect()
    try:
        conn.execute(
            "INSERT INTO opportunity_shadow_scan_repairs(run_id,ticker,repair_reason,repair_status,created_at) VALUES(?,?,?,?,?) "
            "ON CONFLICT(run_id,ticker,repair_reason) DO UPDATE SET repair_status=excluded.repair_status,created_at=excluded.created_at",
            (run_id, ticker, reason, status, audit._now()),
        )
        conn.commit()
    finally:
        conn.close()


def _valid_result(result):
    return isinstance(result, dict) and str(result.get("status") or "") == "ok"


def _finalize_success(run_id, model_id, ticker, result):
    market_date = audit._market_date(result)
    present = audit._snapshot_present(model_id, ticker, market_date)
    if not present:
        repaired = False
        try:
            capture = shadow.capture_snapshot(result)
            repaired = bool(capture.get("captured") or capture.get("reason") == "already_captured")
        except Exception:
            repaired = False
        present = audit._snapshot_present(model_id, ticker, market_date)
        _record_repair(run_id, ticker, "SNAPSHOT_CAPTURE", "SUCCESS" if present else "FAILED")
    audit._record_result(
        run_id,
        ticker,
        market_date,
        "SNAPSHOT_PRESENT" if present else "SNAPSHOT_MISSING",
        result_status="ok",
        snapshot_present=present,
    )


def _retry_failed_scan(run_id, model_id, row, reason):
    ticker = str(row.get("ticker") or "").upper().replace(".OL", "")
    try:
        result = tracking._scan_one(row)
    except Exception as exc:
        _record_repair(run_id, ticker, reason, "FAILED")
        audit._record_result(run_id, ticker, None, "SCAN_ERROR", error=exc)
        return
    if not _valid_result(result):
        _record_repair(run_id, ticker, reason, "FAILED")
        status = str((result or {}).get("status") or "invalid") if isinstance(result, dict) else "invalid"
        audit._record_result(run_id, ticker, audit._market_date(result) if isinstance(result, dict) else None, "RESULT_ERROR", result_status=status)
        return
    _record_repair(run_id, ticker, reason, "SUCCESS")
    _finalize_success(run_id, model_id, ticker, result)


def _run_scan_with_bounded_repair():
    run_id = uuid.uuid4().hex
    model_id = str(identity_runtime._current_identity().get("signal_model_id") or "unknown")
    try:
        rows = audit._active_rows()
        audit._create_run(run_id, model_id, len(rows))
        with ThreadPoolExecutor(max_workers=tracking.SCAN_WORKERS) as pool:
            futures = {pool.submit(tracking._scan_one, row): row for row in rows}
            for future in as_completed(futures):
                row = futures[future]
                ticker = str(row.get("ticker") or "").upper().replace(".OL", "")
                try:
                    result = future.result()
                except Exception:
                    _retry_failed_scan(run_id, model_id, row, "SCAN_ERROR_RETRY")
                    continue
                if not _valid_result(result):
                    _retry_failed_scan(run_id, model_id, row, "RESULT_ERROR_RETRY")
                    continue
                _finalize_success(run_id, model_id, ticker, result)
        audit._finish_run(run_id, "COMPLETED")
    except Exception:
        try:
            audit._finish_run(run_id, "FAILED")
        except Exception:
            pass
    finally:
        with tracking._SCAN_LOCK:
            tracking._SCAN_RUNNING = False


def _repair_rows(run_id):
    if not run_id:
        return []
    conn = tracking.connect()
    try:
        return [dict(row) for row in conn.execute(
            "SELECT ticker,repair_reason,repair_status,created_at FROM opportunity_shadow_scan_repairs WHERE run_id=? ORDER BY ticker,repair_reason",
            (run_id,),
        ).fetchall()]
    finally:
        conn.close()


def scan_audit_status_with_repairs():
    report = _BASE_STATUS()
    run_id = ((report.get("latest_run") or {}).get("run_id"))
    rows = _repair_rows(run_id)
    report["bounded_repair"] = {
        "enabled": True,
        "maximum_live_retry_per_failed_ticker": 1,
        "maximum_snapshot_capture_retry": 1,
        "successful_tickers_are_recalculated": False,
        "attempts": len(rows),
        "successes": sum(1 for row in rows if row.get("repair_status") == "SUCCESS"),
        "failures": sum(1 for row in rows if row.get("repair_status") == "FAILED"),
        "items": rows[:20],
    }
    return report


def install():
    if getattr(audit, "_opportunity_shadow_repair_runtime", False):
        return
    _ensure_schema()
    tracking._run_scan = _run_scan_with_bounded_repair
    audit.scan_audit_status = scan_audit_status_with_repairs
    audit._opportunity_shadow_repair_runtime = True


install()
