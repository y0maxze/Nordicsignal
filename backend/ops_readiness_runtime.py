"""Operational readiness status for NordicSignal.

Keeps product maturity gaps visible. A missing external service is reported as a
blocker instead of being disguised by a client-side feature flag.
"""
import os
from datetime import datetime, timezone

import extra_api
from database import USING_POSTGRES


def _now():
    return datetime.now(timezone.utc).isoformat()


def _env_true(name):
    return os.getenv(name, "").strip().lower() in {"1","true","yes","on"}


def readiness_snapshot():
    from security_runtime import WRITE_TOKEN
    from push_runtime import push_status
    from data_quality_runtime import data_quality_snapshot

    quality = data_quality_snapshot()
    push = push_status()
    external_auth = _env_true("NORDICSIGNAL_EXTERNAL_AUTH_CONFIGURED")
    backup = _env_true("NORDICSIGNAL_BACKUP_VERIFIED")
    legal = _env_true("NORDICSIGNAL_LEGAL_REVIEW_CONFIRMED")

    controls = [
        {"id":"persistent_storage","label":"Persistent database","ready":bool(USING_POSTGRES),"required_for":"internal"},
        {"id":"data_quality","label":"Core data-quality checks","ready":quality.get("status") != "error","required_for":"internal"},
        {"id":"write_secret","label":"Worker ↔ backend write secret","ready":bool(WRITE_TOKEN),"required_for":"private"},
        {"id":"external_auth","label":"Real user authentication / Cloudflare Access","ready":external_auth,"required_for":"private"},
        {"id":"web_push","label":"VAPID Web Push delivery","ready":bool(push.get("delivery_ready")),"required_for":"optional"},
        {"id":"backup","label":"External backup + restore verified","ready":backup,"required_for":"commercial"},
        {"id":"legal_review","label":"External financial/legal review confirmed","ready":legal,"required_for":"commercial"},
        {"id":"multi_user_isolation","label":"Per-user holdings isolation","ready":False,"required_for":"commercial"},
    ]
    private_blockers = [x for x in controls if x["required_for"] in {"private","internal"} and not x["ready"]]
    commercial_blockers = [x for x in controls if x["required_for"] in {"private","internal","commercial"} and not x["ready"]]
    stage = "commercial_ready" if not commercial_blockers else "private_ready" if not private_blockers else "internal_single_user"
    return {
        "status":"ok",
        "stage":stage,
        "controls":controls,
        "private_blockers":[x["id"] for x in private_blockers],
        "commercial_blockers":[x["id"] for x in commercial_blockers],
        "data_quality":{"status":quality.get("status"),"errors":quality.get("error_count"),"warnings":quality.get("warning_count")},
        "push":{"delivery_ready":push.get("delivery_ready"),"active_subscriptions":push.get("active_subscriptions")},
        "note":"Environment flags only mark external controls complete after they are actually configured/verified. NordicSignal does not self-certify legal or backup readiness.",
        "generated_at":_now(),
    }


def install():
    if getattr(extra_api, "_ops_readiness_runtime_installed", False):
        return
    original_install = extra_api.install

    def patched_install(app):
        original_install(app)

        @app.get("/api/ops-readiness")
        def ops_readiness_route():
            return readiness_snapshot()

    extra_api.install = patched_install
    extra_api._ops_readiness_runtime_installed = True


install()
