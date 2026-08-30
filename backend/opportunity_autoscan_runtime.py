"""Automatic Early Opportunity scanning while NordicSignal is available.

The in-process loop remains a best-effort fallback. A protected POST endpoint lets
Cloudflare Cron wake the Render service and trigger the same guarded scan path every
10 minutes, so detection no longer depends on an always-awake Python process.
"""

from datetime import datetime, timezone
import logging
import threading
import time

import extra_api
import opportunity_tracking_runtime as tracking

log = logging.getLogger("nordicsignal.opportunity_autoscan")

AUTO_SCAN_INTERVAL_SECONDS = 10 * 60
INITIAL_SCAN_DELAY_SECONDS = 75
_LOOP_STARTED = False
_LOOP_LOCK = threading.Lock()


def _now():
    return datetime.now(timezone.utc).isoformat()


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
    return {
        "status": "ok",
        "external_scheduler_ready": True,
        "scan_interval_seconds": AUTO_SCAN_INTERVAL_SECONDS,
        "in_process_fallback": True,
        "generated_at": _now(),
    }


def install():
    if getattr(extra_api, "_opportunity_autoscan_runtime", False):
        return

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
            return {
                "status": "ok",
                "scan": state,
                "scan_interval_seconds": AUTO_SCAN_INTERVAL_SECONDS,
                "triggered_at": _now(),
            }

    extra_api.install = patched_install
    extra_api._opportunity_autoscan_runtime = True


install()
