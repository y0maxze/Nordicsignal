import time
import unittest
from unittest.mock import patch

import persistent_feed_cache_runtime as cache


class PersistentFeedCacheTests(unittest.TestCase):
    def test_fresh_persistent_cache_skips_builder(self):
        payload = {'items': [{'id': 1}, {'id': 2}], 'status': 'live'}
        with patch.object(cache, '_read_cache', return_value=(payload, time.time())):
            called = []
            result = cache._cached('x', lambda: called.append(True), 1, False)
        self.assertFalse(called)
        self.assertEqual(len(result['items']), 1)
        self.assertEqual(result['persistent_cache']['state'], 'fresh')

    def test_stale_cache_returns_immediately_and_schedules_refresh(self):
        payload = {'items': [{'id': 1}], 'status': 'live'}
        scheduled = []
        with patch.object(cache, '_read_cache', return_value=(payload, time.time() - cache._FRESH_SECONDS - 1)), \
             patch.object(cache, '_background_refresh', side_effect=lambda key, builder: scheduled.append(key)):
            result = cache._cached('x', lambda: {'items': []}, 10, False)
        self.assertEqual(result['persistent_cache']['state'], 'stale_while_revalidate')
        self.assertEqual(scheduled, ['x'])

    def test_force_refresh_uses_builder(self):
        built = {'items': [{'id': 3}], 'status': 'live'}
        with patch.object(cache, '_read_cache') as read_cache, patch.object(cache, '_write_cache') as write_cache:
            result = cache._cached('x', lambda: built, 10, True)
        read_cache.assert_not_called()
        write_cache.assert_called_once()
        self.assertEqual(result['items'][0]['id'], 3)
        self.assertEqual(result['persistent_cache']['state'], 'refreshed')


if __name__ == '__main__':
    unittest.main()
