"""Automatic Early Opportunity scanning while NordicSignal is available.

The in-process loop remains a best-effort fallback. A protected POST endpoint lets
Cloudflare Cron wake the Render service and trigger the same guarded scan path every
10 minutes, so detection no longer depends on an always-awake Python process.

External scheduler heartbeats are persisted in Postgres so production can prove the
Cron path is actually reaching the backend across Render sleeps and restarts.
"""

from datetime import datetime, timezone
import logging
import threading
import time

import extra_api
from database import connect
import opportunity_tracking_runtime as tracking

log = logging.getLogger("nordicsignal.opportunity_autoscan")

AUTO_SCAN_INTERVAL_SECONDS = 10 * 60
INITIAL_SCAN_DELAY_SECONDS = 75
_LOOP_STARTED = False
_LOOP_LOCK = threading.Lock()


def _now():
    return datetime.now(timezone.utc).isoformat()


def _ensure_scheduler_schema():
    conn = connect()
    try:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS opportunity_scheduler_state (
          id INTEGER PRIMARY KEY,
          last_external_trigger_at TEXT,
          last_scan_state TEXT,
          external_trigger_count INTEGER NOT NULL DEFAULT 0,
          updated_at TEXT NOT NULL
        );
        """)
        conn.commit()
    finally:
        conn.close()


def _persistent_status():
    try:
        conn = connect()
        try:
            row = conn.execute(
                "SELECT last_external_trigger_at,last_scan_state,external_trigger_count,updated_at "
                "FROM opportunity_scheduler_state WHERE id=1"
            ).fetchone()
        finally:
            conn.close()
        if not row:
            return {
                "last_external_trigger_at": None,
                "last_scan_state": None,
                "external_trigger_count": 0,
                "scheduler_state_updated_at": None,
            }
        item = dict(row)
        return {
            "last_external_trigger_at": item.get("last_external_trigger_at"),
            "last_scan_state": item.get("last_scan_state"),
            "external_trigger_count": int(item.get("external_trigger_count") or 0),
            "scheduler_state_updated_at": item.get("updated_at"),
        }
    except Exception:
        log.exception("Could not read opportunity scheduler heartbeat")
        return {
            "last_external_trigger_at": None,
            "last_scan_state": None,
            "external_trigger_count": 0,
            "scheduler_state_updated_at": None,
        }


def _record_external_trigger(scan_state):
    triggered_at = _now()
    conn = connect()
    try:
        row = conn.execute(
            "SELECT external_trigger_count FROM opportunity_scheduler_state WHERE id=1"
        ).fetchone()
        if row:
            item = dict(row)
            count = int(item.get("external_trigger_count") or 0) + 1
            conn.execute(
                "UPDATE opportunity_scheduler_state SET last_external_trigger_at=?,last_scan_state=?,"
                "external_trigger_count=?,updated_at=? WHERE id=1",
                (triggered_at, str(scan_state), count, triggered_at),
            )
        else:
            count = 1
            conn.execute(
                "INSERT INTO opportunity_scheduler_state(id,last_external_trigger_at,last_scan_state,"
                "external_trigger_count,updated_at) VALUES(1,?,?,?,?)",
                (triggered_at, str(scan_state), count, triggered_at),
            )
        conn.commit()
        return triggered_at, count
    finally:
        conn.close()


def _loop():
    time.sleep(INITIAL_SCAN_DELAY_SECONDS)
    while True:
        try:
            state = tracking._maybe_schedule_scan()
            log.info("Automatic Early Opportunity scan: %s", state)
        except Exception:
            log.exception("Automatic Early Opportunity scan scheduling failed")
        time.sleep(AUTO_SCAN_INTERVAL_SECONDS)


def _start():
    global _LOOP_STARTED
    with _LOOP_LOCK:
        if _LOOP_STARTED:
            return
        _LOOP_STARTED = True
        tracking.SCAN_INTERVAL_SECONDS = AUTO_SCAN_INTERVAL_SECONDS
        threading.Thread(
            target=_loop,
            daemon=True,
            name="nordicsignal-opportunity-autoscan",
        ).start()


def scheduler_status():
    status = {
        "status": "ok",
        "external_scheduler_ready": True,
        "scan_interval_seconds": AUTO_SCAN_INTERVAL_SECONDS,
        "in_process_fallback": True,
        "generated_at": _now(),
    }
    status.update(_persistent_status())
    return status


def install():
    if getattr(extra_api, "_opportunity_autoscan_runtime", False):
        return

    _ensure_scheduler_schema()
    _start()
    original_install = extra_api.install

    def patched_install(app):
        original_install(app)

        @app.get("/api/opportunity-scan/status")
        def opportunity_scan_status_route():
            return scheduler_status()

        @app.post("/api/opportunity-scan/run")
        def opportunity_scan_run_route():
            # security_runtime protects API writes with NORDICSIGNAL_WRITE_TOKEN.
            state = tracking._maybe_schedule_scan()
            triggered_at, trigger_count = _record_external_trigger(state)
            return {
                "status": "ok",
                "scan": state,
                "scan_interval_seconds": AUTO_SCAN_INTERVAL_SECONDS,
                "triggered_at": triggered_at,
                "external_trigger_count": trigger_count,
            }

    extra_api.install = patched_install
    extra_api._opportunity_autoscan_runtime = True


install()
