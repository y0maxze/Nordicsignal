import unittest

from http_cache_runtime import _ttl_for


class PublicHttpCacheRuntimeTests(unittest.TestCase):
    def test_public_market_reads_have_short_ttls(self):
        self.assertEqual(_ttl_for('/api/quote/LSG'), 10)
        self.assertGreater(_ttl_for('/api/search'), 0)
        self.assertGreater(_ttl_for('/api/instrument/VOO/analytics'), 0)
        self.assertGreater(_ttl_for('/api/short/LSG'), 0)
        self.assertGreater(_ttl_for('/api/signal-events'), 0)

    def test_user_state_and_refresh_are_never_cached(self):
        for path in (
            '/api/holdings',
            '/api/holdings/transactions',
            '/api/paper/dashboard',
            '/api/paper/trades',
            '/api/watchlist',
            '/api/refresh',
        ):
            self.assertEqual(_ttl_for(path), 0, path)

    def test_unknown_api_route_defaults_to_no_cache(self):
        self.assertEqual(_ttl_for('/api/private-future-feature'), 0)
        self.assertEqual(_ttl_for('/not-api'), 0)


if __name__ == '__main__':
    unittest.main()


def test_private_backend_auth_cannot_be_bypassed_by_cached_response(monkeypatch):
    import asyncio
    import main
    import security_runtime as security
    import http_cache_runtime as cache
    from starlette.requests import Request
    from starlette.responses import Response
    monkeypatch.setattr(security,'PRIVATE_MODE',True)
    monkeypatch.setattr(security,'WRITE_TOKEN','test-only-private-secret')
    monkeypatch.setattr(cache,'_get',lambda key:(200,{'content-type':'application/json'},b'{"cached":true}'))
    middleware={m.kwargs['dispatch'].__name__:m.kwargs['dispatch'] for m in main.app.user_middleware if 'dispatch' in m.kwargs}
    async def endpoint(request):return Response('not cached')
    async def secured(request):return await middleware['nordicsignal_security'](request,endpoint)
    async def run(token=None):
        headers=[] if token is None else [(b'x-nordicsignal-internal-token',token.encode())]
        request=Request({'type':'http','method':'GET','path':'/api/stocks','query_string':b'','headers':headers})
        return await middleware['public_market_cache'](request,secured)
    assert asyncio.run(run()).status_code==401
    response=asyncio.run(run('test-only-private-secret'))
    assert response.status_code==200
    assert response.body==b'{"cached":true}'
