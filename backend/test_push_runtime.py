import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import push_runtime as push


def _db_factory(path):
    def connect():
        conn = sqlite3.connect(path, timeout=30)
        conn.row_factory = sqlite3.Row
        return conn
    return connect


class PushRuntimeTests(unittest.TestCase):
    def test_endpoint_hash_is_stable_and_non_reversible_shape(self):
        endpoint='https://push.example/subscription/abc'
        self.assertEqual(push._hash(endpoint), push._hash(endpoint))
        self.assertEqual(len(push._hash(endpoint)), 64)
        self.assertNotIn('subscription', push._hash(endpoint))

    def test_push_status_is_explicit_about_configuration(self):
        status=push.push_status()
        self.assertTrue(status['supported'])
        self.assertIn('delivery_ready', status)
        self.assertIn('public_key_configured', status)
        self.assertIn('private_key_configured', status)
        self.assertIn('backend_awake_required', status)
        self.assertIn('delivery_retry_policy', status)

    def test_only_transient_delivery_failures_are_retryable(self):
        for status in ('delivery_error', 'http_408', 'http_425', 'http_429', 'http_500', 'http_503', 'http_599'):
            with self.subTest(status=status):
                self.assertTrue(push._retryable_delivery_status(status))
        for status in ('sent', 'not_configured', 'http_400', 'http_401', 'http_403', 'http_404', 'http_410'):
            with self.subTest(status=status):
                self.assertFalse(push._retryable_delivery_status(status))

    def test_retry_budget_is_bounded(self):
        with tempfile.TemporaryDirectory() as tmp:
            connect = _db_factory(Path(tmp) / 'push.sqlite')
            with patch.object(push, 'connect', connect), patch.object(push, 'USING_POSTGRES', False), patch.object(push, '_RETRY_DELAY_SECONDS', 0):
                push._ensure_schema()
                self.assertTrue(push._retry_allowed('trend:1', 'endpoint-a'))
                for attempt in range(1, push._MAX_DELIVERY_ATTEMPTS + 1):
                    push._record_attempt('trend:1', 'endpoint-a', 'http_503')
                    self.assertEqual(
                        push._retry_allowed('trend:1', 'endpoint-a'),
                        attempt < push._MAX_DELIVERY_ATTEMPTS,
                    )

    def test_legacy_transient_delivery_can_be_replaced_by_success(self):
        with tempfile.TemporaryDirectory() as tmp:
            connect = _db_factory(Path(tmp) / 'push.sqlite')
            with patch.object(push, 'connect', connect), patch.object(push, 'USING_POSTGRES', False):
                push._ensure_schema()
                push._record_delivery('trend:2', 'endpoint-b', 'http_503')
                self.assertFalse(push._delivered('trend:2', 'endpoint-b'))
                push._record_delivery('trend:2', 'endpoint-b', 'sent')
                self.assertTrue(push._delivered('trend:2', 'endpoint-b'))


if __name__=='__main__':
    unittest.main()
