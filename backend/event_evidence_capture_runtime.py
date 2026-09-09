"""Bridge Event Radar observations into the point-in-time evidence archive."""
import event_evidence_runtime
import event_radar_runtime


def install():
    if getattr(event_radar_runtime, "_event_evidence_capture_v1", False):
        return
    original = event_radar_runtime.build_event_radar

    def captured(*args, **kwargs):
        result = original(*args, **kwargs)
        event_evidence_runtime.record_events(result.get("items") or [])
        return result

    event_radar_runtime.build_event_radar = captured
    event_radar_runtime._event_evidence_capture_v1 = True


install()
