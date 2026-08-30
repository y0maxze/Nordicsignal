"""Per-run audit trail for Opportunity shadow collection.

The historical scanner previously tolerated per-ticker exceptions without retaining
which ticker failed. This runtime replaces only the scan orchestration function. It
keeps the existing live Opportunity calculation unchanged while persisting one audit
run and one outcome per attempted ticker, then verifies whether a shadow snapshot is
present for the result's market day.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import threading
import uuid

import extra_api
import opportunity_tracking_runtime as tracking
import opportunity_version_identity_runtime as identity_runtime


def _now():
    return datetime.now(timezone.utc).isoformat()


def _market_date(result):
    try:
        value = tracking._entry_date_from_result(result or {})
    except Exception:
        value = None
    if value:
        return str(value)[:10]
    generated = str((result or {}).get("generated_at") or "")[:10]
    return generated if len(generated) == 10 else None


def _ensure_schema():
    conn = tracking.connect()
    try:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS opportunity_shadow_scan_runs (
          run_id TEXT PRIMARY KEY,
          signal_model_id TEXT NOT NULL,
          expected_tickers INTEGER NOT NULL,
          started_at TEXT NOT NULL,
          completed_at TEXT,
          run_status TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS opportunity_shadow_scan_results (
          run_id TEXT NOT NULL,
          ticker TEXT NOT NULL,
          market_date TEXT,
          outcome TEXT NOT NULL,
          result_status TEXT,
          snapshot_present INTEGER NOT NULL DEFAULT 0,
          error_class TEXT,
          error_message TEXT,
          completed_at TEXT NOT NULL,
          PRIMARY KEY(run_id,ticker)
        );
        """)
        conn.commit()
    finally:
        conn.close()


def _active_rows():
    conn = tracking.connect()
    try:
        return [dict(row) for row in conn.execute(
            "SELECT ticker,name FROM stocks WHERE active=1 ORDER BY ticker"
        ).fetchall()]
    finally:
        conn.close()


def _snapshot_present(model_id, ticker, market_date):
    if not market_date:
        return False
    conn = tracking.connect()
    try:
        row = conn.execute(
            "SELECT id FROM opportunity_shadow_snapshots WHERE signal_model_id=? AND ticker=? AND market_date=?",
            (model_id, ticker, market_date),
        ).fetchone()
        return bool(row)
    except Exception:
        return False
    finally:
        conn.close()


def _create_run(run_id, model_id, expected):
    conn = tracking.connect()
    try:
        conn.execute(
            "INSERT INTO opportunity_shadow_scan_runs(run_id,signal_model_id,expected_tickers,started_at,run_status) VALUES(?,?,?,?,?)",
            (run_id, model_id, expected, _now(), "RUNNING"),
        )
        conn.commit()
    finally:
        conn.close()


def _record_result(run_id, ticker, market_date, outcome, result_status=None, snapshot_present=False, error=None):
    error_class = error.__class__.__name__ if error is not None else None
    error_message = str(error)[:500] if error is not None else None
    conn = tracking.connect()
    try:
        conn.execute(
            "INSERT INTO opportunity_shadow_scan_results(run_id,ticker,market_date,outcome,result_status,snapshot_present,error_class,error_message,completed_at) "
            "VALUES(?,?,?,?,?,?,?,?,?) ON CONFLICT(run_id,ticker) DO UPDATE SET market_date=excluded.market_date,outcome=excluded.outcome,result_status=excluded.result_status,snapshot_present=excluded.snapshot_present,error_class=excluded.error_class,error_message=excluded.error_message,completed_at=excluded.completed_at",
            (run_id, ticker, market_date, outcome, result_status, 1 if snapshot_present else 0, error_class, error_message, _now()),
        )
        conn.commit()
    finally:
        conn.close()


def _finish_run(run_id, status="COMPLETED"):
    conn = tracking.connect()
    try:
        conn.execute(
            "UPDATE opportunity_shadow_scan_runs SET completed_at=?,run_status=? WHERE run_id=?",
            (_now(), status, run_id),
        )
        conn.commit()
    finally:
        conn.close()


def _run_scan_audited():
    rows = []
    run_id = uuid.uuid4().hex
    model_id = str(identity_runtime._current_identity().get("signal_model_id") or "unknown")
    try:
        rows = _active_rows()
        _create_run(run_id, model_id, len(rows))
        with ThreadPoolExecutor(max_workers=tracking.SCAN_WORKERS) as pool:
            futures = {pool.submit(tracking._scan_one, row): row for row in rows}
            for future in as_completed(futures):
                row = futures[future]
                ticker = str(row.get("ticker") or "").upper().replace(".OL", "")
                try:
                    result = future.result()
                except Exception as exc:
                    _record_result(run_id, ticker, None, "SCAN_ERROR", error=exc)
                    continue

                result_status = str((result or {}).get("status") or "missing") if isinstance(result, dict) else "invalid"
                market_date = _market_date(result) if isinstance(result, dict) else None
                if not isinstance(result, dict) or result_status != "ok":
                    _record_result(run_id, ticker, market_date, "RESULT_ERROR", result_status=result_status)
                    continue

                present = _snapshot_present(model_id, ticker, market_date)
                outcome = "SNAPSHOT_PRESENT" if present else "SNAPSHOT_MISSING"
                _record_result(run_id, ticker, market_date, outcome, result_status=result_status, snapshot_present=present)
        _finish_run(run_id, "COMPLETED")
    except Exception:
        try:
            _finish_run(run_id, "FAILED")
        except Exception:
            pass
    finally:
        with tracking._SCAN_LOCK:
            tracking._SCAN_RUNNING = False


def _latest_run():
    conn = tracking.connect()
    try:
        run = conn.execute(
            "SELECT * FROM opportunity_shadow_scan_runs ORDER BY started_at DESC LIMIT 1"
        ).fetchone()
        if not run:
            return None, []
        run = dict(run)
        results = [dict(row) for row in conn.execute(
            "SELECT * FROM opportunity_shadow_scan_results WHERE run_id=? ORDER BY ticker",
            (run["run_id"],),
        ).fetchall()]
        return run, results
    finally:
        conn.close()


def _expected_tickers():
    try:
        return [str(row.get("ticker") or "").upper().replace(".OL", "") for row in _active_rows()]
    except Exception:
        return []


def scan_audit_status():
    run, results = _latest_run()
    if not run:
        return {
            "status": "NO_RUNS",
            "operational_status": "COLLECTING_DATA",
            "latest_run": None,
            "missing_tickers": [],
            "failed_tickers": [],
            "snapshot_missing_tickers": [],
            "meaning": "No audited shadow scan has completed yet.",
            "generated_at": _now(),
        }

    expected = set(_expected_tickers())
    seen = {str(row.get("ticker") or "") for row in results}
    not_scanned = sorted(t for t in expected - seen if t)
    failed = sorted(str(row.get("ticker")) for row in results if row.get("outcome") in {"SCAN_ERROR", "RESULT_ERROR"})
    snapshot_missing = sorted(str(row.get("ticker")) for row in results if row.get("outcome") == "SNAPSHOT_MISSING")
    present = sum(1 for row in results if row.get("outcome") == "SNAPSHOT_PRESENT")
    expected_count = max(int(run.get("expected_tickers") or 0), len(expected))
    coverage = (present / expected_count * 100.0) if expected_count else 0.0

    if str(run.get("run_status")) == "FAILED" or not_scanned:
        operational = "FAIL"
    elif failed or snapshot_missing:
        operational = "WARN"
    else:
        operational = "PASS"

    return {
        "status": "ok",
        "operational_status": operational,
        "latest_run": {
            "run_id": run.get("run_id"),
            "signal_model_id": run.get("signal_model_id"),
            "run_status": run.get("run_status"),
            "started_at": run.get("started_at"),
            "completed_at": run.get("completed_at"),
            "expected_tickers": expected_count,
            "result_rows": len(results),
            "snapshot_present": present,
            "snapshot_coverage_pct": round(coverage, 2),
        },
        "missing_tickers": not_scanned,
        "failed_tickers": failed,
        "snapshot_missing_tickers": snapshot_missing,
        "outcome_counts": {
            key: sum(1 for row in results if row.get("outcome") == key)
            for key in ("SNAPSHOT_PRESENT", "SNAPSHOT_MISSING", "RESULT_ERROR", "SCAN_ERROR")
        },
        "failures": [
            {"ticker": row.get("ticker"), "outcome": row.get("outcome"), "error_class": row.get("error_class"), "error_message": row.get("error_message")}
            for row in results if row.get("outcome") in {"SCAN_ERROR", "RESULT_ERROR", "SNAPSHOT_MISSING"}
        ][:20],
        "automatic_threshold_changes": False,
        "meaning": "Per-ticker audit of the latest shadow collection scan; it does not affect live signals.",
        "generated_at": _now(),
    }


def install():
    if getattr(extra_api, "_opportunity_shadow_scan_audit_runtime", False):
        return
    _ensure_schema()
    tracking._run_scan = _run_scan_audited
    original_install = extra_api.install

    def patched_install(app):
        original_install(app)

        @app.get("/api/opportunity-shadow/scan-audit")
        def opportunity_shadow_scan_audit_route():
            return scan_audit_status()

    extra_api.install = patched_install
    extra_api._opportunity_shadow_scan_audit_runtime = True


install()
