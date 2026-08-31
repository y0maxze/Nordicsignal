"""Bridge locally displayed PWA notifications into persistent alert history.

Some mobile insider alerts are produced with ServiceWorkerRegistration.showNotification
while the app is running rather than by VAPID Web Push. The client calls this route
only after showNotification succeeds. The shared alert-history event key keeps the
record idempotent across repeated polling.
"""
import extra_api
import alert_history_runtime as history


def install():
    if getattr(extra_api, "_alert_local_record_runtime", False):
        return
    original_install = extra_api.install

    def patched_install(app):
        original_install(app)

        @app.post("/api/alerts/record")
        def alerts_record(payload: dict):
            data = dict(payload or {})
            data["tag"] = str(data.get("tag") or data.get("event_key") or "")[:300]
            if not data["tag"].startswith("local:"):
                data["tag"] = "local:" + data["tag"]
            recorded = history._record_successful_payload(data)
            return {"status": "ok", "recorded": bool(recorded)}

    extra_api.install = patched_install
    extra_api._alert_local_record_runtime = True


install()
