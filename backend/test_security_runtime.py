import unittest

import security_runtime as sec


class _Request:
    def __init__(self, headers=None):
        self.headers = headers or {}


class SecurityRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.private_mode = sec.PRIVATE_MODE
        self.write_token = sec.WRITE_TOKEN

    def tearDown(self):
        sec.PRIVATE_MODE = self.private_mode
        sec.WRITE_TOKEN = self.write_token

    def test_expected_worker_origin_is_allowed(self):
        self.assertTrue(sec._origin_allowed('https://nordicsignal.8pnwk5r8f4.workers.dev'))
        self.assertFalse(sec._origin_allowed('https://evil.example'))

    def test_rate_limit_is_bounded(self):
        key = 'unit-test-client-rate-limit'
        self.assertEqual(sec._rate_allowed(key, 2)[0], True)
        self.assertEqual(sec._rate_allowed(key, 2)[0], True)
        allowed, retry = sec._rate_allowed(key, 2)
        self.assertFalse(allowed)
        self.assertGreaterEqual(retry, 1)

    def test_security_status_never_exposes_secret_value(self):
        status = sec.security_status()
        self.assertIn('shared_secret_configured', status)
        self.assertNotIn('write_token', status)
        self.assertNotIn('secret', {k for k in status if k == 'secret'})

    def test_public_mode_does_not_require_proxy_secret(self):
        sec.PRIVATE_MODE = False
        sec.WRITE_TOKEN = ''
        self.assertTrue(sec._backend_proxy_auth_ok(_Request()))

    def test_private_mode_fails_closed_without_server_secret(self):
        sec.PRIVATE_MODE = True
        sec.WRITE_TOKEN = ''
        self.assertFalse(sec._backend_proxy_auth_ok(_Request()))

    def test_private_mode_requires_matching_internal_header(self):
        sec.PRIVATE_MODE = True
        sec.WRITE_TOKEN = 'secret-value'
        self.assertFalse(sec._backend_proxy_auth_ok(_Request()))
        self.assertFalse(sec._backend_proxy_auth_ok(_Request({'x-nordicsignal-internal-token':'wrong'})))
        self.assertTrue(sec._backend_proxy_auth_ok(_Request({'x-nordicsignal-internal-token':'secret-value'})))

    def test_private_mode_accepts_bearer_fallback(self):
        sec.PRIVATE_MODE = True
        sec.WRITE_TOKEN = 'secret-value'
        self.assertTrue(sec._backend_proxy_auth_ok(_Request({'authorization':'Bearer secret-value'})))


if __name__ == '__main__':
    unittest.main()
