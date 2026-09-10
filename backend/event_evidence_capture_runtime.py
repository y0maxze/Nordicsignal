"""Bridge Event Radar observations into the point-in-time evidence archive."""
import logging

import event_evidence_runtime
import event_radar_runtime

log = logging.getLogger("nordicsignal.event_evidence_capture")


def install():
    if getattr(event_radar_runtime, "_event_evidence_capture_v1", False):
        return
    original = event_radar_runtime.build_event_radar

    def captured(*args, **kwargs):
        result = original(*args, **kwargs)
        try:
            event_evidence_runtime.record_events(result.get("items") or [])
        except Exception:
            # Evidence persistence is additive. A DB/archive failure must not make
            # the live Event Radar endpoint fail for the user.
            log.exception("Event Evidence capture failed")
        return result

    event_radar_runtime.build_event_radar = captured
    event_radar_runtime._event_evidence_capture_v1 = True


install()
