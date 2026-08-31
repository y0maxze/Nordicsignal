"""Persistent per-ticker failure streaks for Opportunity shadow collection.

A single provider glitch is common and should not disable an instrument. Repeated
failures across completed audited scans are different: they indicate a persistent
collection problem. This layer is diagnostic only and never changes active stocks,
signal thresholds, labels, scores or retry limits.
"""
from __future__ import annotations

from datetime import datetime, timezone

import extra_api
import opportunity_learning_health_runtime as health
import opportunity_shadow_scan_audit_runtime as audit
import opportunity_tracking_runtime as tracking

WARN_STREAK = 2
FAIL_STREAK = 3
MAX_RUNS = 12
FAILURE_OUTCOMES = {"SCAN_ERROR", "RESULT_ERROR", "SNAPSHOT_MISSING"}
SUCCESS_OUTCOME = "SNAPSHOT_PRESENT"

_BASE_HEALTH = health.learning_health


def _now():
    return datetime.now(timezone.utc).isoformat()


def _completed_runs(limit=MAX_RUNS):
    conn = tracking.connect()
    try:
        runs = [dict(row) for row in conn.execute(
            "SELECT * FROM opportunity_shadow_scan_runs WHERE run_status='COMPLETED' "
            "ORDER BY started_at DESC LIMIT ?",
            (max(1, int(limit)),),
        ).fetchall()]
        output = []
        for run in runs:
            results = [dict(row) for row in conn.execute(
                "SELECT ticker,outcome,error_class,error_message FROM opportunity_shadow_scan_results "
                "WHERE run_id=? ORDER BY ticker",
                (run["run_id"],),
            ).fetchall()]
            output.append((run, results))
        return output
    finally:
        conn.close()


def _ticker_streaks(runs):
    tickers = set()
    by_run = []
    for run, rows in runs or []:
        mapping = {str(row.get("ticker") or ""): row for row in rows if row.get("ticker")}
        tickers.update(mapping)
        by_run.append((run, mapping))

    items = []
    for ticker in sorted(tickers):
        streak = 0
        latest_outcome = None
        latest_error_class = None
        latest_error_message = None
        latest_run_id = None
        latest_started_at = None
        for run, mapping in by_run:
            row = mapping.get(ticker)
            if row is None:
                # No result row is itself a collection miss for this completed run.
                outcome = "NOT_ATTEMPTED"
                is_failure = True
                error_class = None
                error_message = None
            else:
                outcome = str(row.get("outcome") or "UNKNOWN")
                is_failure = outcome in FAILURE_OUTCOMES
                error_class = row.get("error_class")
                error_message = row.get("error_message")

            if latest_outcome is None:
                latest_outcome = outcome
                latest_error_class = error_class
                latest_error_message = error_message
                latest_run_id = run.get("run_id")
                latest_started_at = run.get("started_at")

            if is_failure:
                streak += 1
                continue
            # Any successful/non-failure result breaks the consecutive streak.
            break

        if streak <= 0:
            continue
        state = "FAIL" if streak >= FAIL_STREAK else "WARN" if streak >= WARN_STREAK else "TRANSIENT"
        items.append({
            "ticker": ticker,
            "consecutive_failures": streak,
            "status": state,
            "latest_outcome": latest_outcome,
            "latest_error_class": latest_error_class,
            "latest_error_message": latest_error_message,
            "latest_run_id": latest_run_id,
            "latest_started_at": latest_started_at,
        })
    return items


def failure_streak_report():
    runs = _completed_runs()
    streaks = _ticker_streaks(runs)
    persistent = [item for item in streaks if item["consecutive_failures"] >= WARN_STREAK]
    failing = [item for item in streaks if item["consecutive_failures"] >= FAIL_STREAK]
    transient = [item for item in streaks if item["consecutive_failures"] == 1]
    operational = "FAIL" if failing else "WARN" if persistent else "PASS"
    return {
        "status": "ok",
        "operational_status": operational,
        "completed_runs_evaluated": len(runs),
        "warn_streak": WARN_STREAK,
        "fail_streak": FAIL_STREAK,
        "persistent_tickers": persistent,
        "fail_tickers": [item["ticker"] for item in failing],
        "warn_tickers": [item["ticker"] for item in persistent if item["consecutive_failures"] < FAIL_STREAK],
        "transient_tickers": [item["ticker"] for item in transient],
        "automatic_deactivation": False,
        "automatic_threshold_changes": False,
        "meaning": "Repeated per-ticker shadow collection failures are escalated diagnostically; success resets the streak.",
        "generated_at": _now(),
    }


def learning_health():
    report = _BASE_HEALTH()
    checks = report.setdefault("checks", {})
    errors = report.setdefault("errors", [])
    try:
        streak = failure_streak_report()
        checks["shadow_failure_streaks"] = {
            "status": streak["operational_status"],
            "completed_runs_evaluated": streak["completed_runs_evaluated"],
            "warn_tickers": streak["warn_tickers"],
            "fail_tickers": streak["fail_tickers"],
            "persistent_tickers": streak["persistent_tickers"],
            "rule": f"WARN after {WARN_STREAK} consecutive failures; FAIL after {FAIL_STREAK}; success resets streak; no automatic deactivation",
        }
    except Exception as exc:
        checks["shadow_failure_streaks"] = {"status": "FAIL", "error": str(exc)}
        errors.append("shadow_failure_streaks")
    report["learning_pipeline_status"] = health._overall_status(checks)
    return report


def install():
    if getattr(extra_api, "_opportunity_scan_failure_streak_runtime", False):
        return
    health.learning_health = learning_health
    original_install = extra_api.install

    def patched_install(app):
        original_install(app)

        @app.get("/api/opportunity-shadow/failure-streaks")
        def opportunity_shadow_failure_streaks_route():
            return failure_streak_report()

    extra_api.install = patched_install
    extra_api._opportunity_scan_failure_streak_runtime = True


install()
