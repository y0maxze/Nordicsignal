"""Automatic Early Opportunity scanning while the NordicSignal backend is awake.

The core opportunity tracker already owns persistence, transition detection and
forward-return tracking. This runtime only schedules that existing scan loop on a
fixed cadence so push alerts do not depend on a user opening Latest Signals first.

Render Free instances can sleep when idle; this module deliberately does not try to
circumvent hosting sleep. It resumes automatically whenever the backend process is
running again.
"""

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
        # The tracker uses this same interval as its anti-overlap/cooldown guard.
        tracking.SCAN_INTERVAL_SECONDS = AUTO_SCAN_INTERVAL_SECONDS
        threading.Thread(
            target=_loop,
            daemon=True,
            name="nordicsignal-opportunity-autoscan",
        ).start()


def install():
    if getattr(extra_api, "_opportunity_autoscan_runtime", False):
        return
    _start()
    extra_api._opportunity_autoscan_runtime = True


install()
