import unittest

import security_runtime as sec


class SecurityRuntimeTests(unittest.TestCase):
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


if __name__ == '__main__':
    unittest.main()
