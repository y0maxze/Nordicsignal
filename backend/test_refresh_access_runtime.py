from starlette.requests import Request

import refresh_access_runtime as refresh_access


def _request(headers=None):
    pairs = []
    for key, value in (headers or {}).items():
        pairs.append((key.lower().encode(), value.encode()))
    return Request({"type": "http", "method": "GET", "path": "/api/refresh", "headers": pairs})


def test_refresh_rejects_when_secret_is_missing():
    allowed, reason = refresh_access.refresh_authorized(_request(), token="")
    assert allowed is False
    assert reason == "secret_missing"


def test_refresh_rejects_wrong_secret():
    request = _request({"x-nordicsignal-internal-token": "wrong"})
    allowed, reason = refresh_access.refresh_authorized(request, token="expected")
    assert allowed is False
    assert reason == "unauthorized"


def test_refresh_accepts_internal_header_secret():
    request = _request({"x-nordicsignal-internal-token": "expected"})
    allowed, reason = refresh_access.refresh_authorized(request, token="expected")
    assert allowed is True
    assert reason == "ok"


def test_refresh_accepts_bearer_secret():
    request = _request({"authorization": "Bearer expected"})
    allowed, reason = refresh_access.refresh_authorized(request, token="expected")
    assert allowed is True
    assert reason == "ok"
