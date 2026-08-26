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
