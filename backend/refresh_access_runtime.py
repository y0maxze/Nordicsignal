"""Lock expensive market refreshes behind the Worker-to-Render shared secret.

NordicSignal is currently a private tool, so there is no reason for the direct
Render hostname to expose a provider-wide refresh trigger. Browser traffic can
still reach the route through the Cloudflare Worker, which attaches the same
NORDICSIGNAL_WRITE_TOKEN used by the existing security layer.
"""
from __future__ import annotations

import hmac
import os

from fastapi import Request
from starlette.responses import JSONResponse

import extra_api


def _configured_token():
    return os.getenv("NORDICSIGNAL_WRITE_TOKEN", "").strip()


def _supplied_token(request):
    supplied = request.headers.get("x-nordicsignal-internal-token", "")
    if not supplied:
        auth = request.headers.get("authorization", "")
        supplied = auth[7:].strip() if auth.lower().startswith("bearer ") else ""
    return str(supplied)


def refresh_authorized(request, token=None):
    expected = _configured_token() if token is None else str(token or "")
    if not expected:
        return False, "secret_missing"
    supplied = _supplied_token(request)
    if not supplied or not hmac.compare_digest(supplied, expected):
        return False, "unauthorized"
    return True, "ok"


def install():
    if getattr(extra_api, "_refresh_access_runtime_installed", False):
        return
    original_install = extra_api.install

    def patched_install(app):
        original_install(app)
        if getattr(app.state, "nordicsignal_refresh_access", False):
            return
        app.state.nordicsignal_refresh_access = True

        @app.middleware("http")
        async def nordicsignal_refresh_access(request: Request, call_next):
            if request.url.path != "/api/refresh":
                return await call_next(request)

            allowed, reason = refresh_authorized(request)
            request_id = request.headers.get("x-request-id") or ""
            if not allowed and reason == "secret_missing":
                return JSONResponse(
                    {
                        "status": "error",
                        "code": "REFRESH_SECRET_NOT_CONFIGURED",
                        "message": "Market refresh is disabled until the internal refresh secret is configured",
                        "request_id": request_id or None,
                    },
                    status_code=503,
                )
            if not allowed:
                return JSONResponse(
                    {
                        "status": "error",
                        "code": "REFRESH_AUTH_REQUIRED",
                        "message": "Market refresh requires the internal Worker-to-Render secret",
                        "request_id": request_id or None,
                    },
                    status_code=401,
                )
            return await call_next(request)

    extra_api.install = patched_install
    extra_api._refresh_access_runtime_installed = True


install()
