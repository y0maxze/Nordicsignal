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

    def test_failed_news_refresh_does_not_overwrite_expired_success(self):
        previous = {'items': [{'title': 'Earlier announcement'}], 'status': 'live_general_news'}
        failed = {'items': [], 'status': 'unavailable', 'sources': {'euronext': {'status': 'unavailable'}}}
        with patch.object(cache, '_read_cache', return_value=(previous, time.time() - cache._MAX_STALE_SECONDS - 1)), \
             patch.object(cache, '_write_cache') as write_cache:
            result = cache._cached('market_news:v1', lambda: failed, 40)
        write_cache.assert_not_called()
        self.assertEqual(result['persistent_cache']['state'], 'unavailable')
        self.assertEqual(result['status'], 'unavailable')
        self.assertEqual(result['items'], [])

    def test_legacy_failure_cached_as_empty_is_retried_instead_of_served_as_fresh(self):
        legacy_failure = {'items': [], 'status': 'no_market_news', 'sources': {'euronext': {'status': 'unavailable'}}}
        recovered = {'items': [{'title': 'Recovered announcement'}], 'status': 'live_general_news'}
        with patch.object(cache, '_read_cache', return_value=(legacy_failure, time.time())), \
             patch.object(cache, '_write_cache') as write_cache:
            result = cache._cached('market_news:v1', lambda: recovered, 40)
        write_cache.assert_called_once_with('market_news:v1', recovered)
        self.assertEqual(result['items'], recovered['items'])

    def test_failed_background_news_refresh_keeps_last_good_cache(self):
        failure = {'items': [], 'status': 'unavailable'}
        def run_immediately(**kwargs):
            class InlineThread:
                def start(self):
                    kwargs['target']()
            return InlineThread()
        with patch.object(cache.threading, 'Thread', side_effect=run_immediately), \
             patch.object(cache, '_write_cache') as write_cache:
            cache._background_refresh('market_news:v1', lambda: failure)
        write_cache.assert_not_called()
        self.assertNotIn('market_news:v1', cache._REFRESHING)

    def test_successful_empty_news_is_still_cacheable(self):
        empty = {'items': [], 'status': 'no_market_news', 'sources': {'euronext': {'status': 'no_matches'}}}
        with patch.object(cache, '_read_cache', return_value=None), patch.object(cache, '_write_cache') as write_cache:
            result = cache._cached('market_news:v1', lambda: empty, 40)
        write_cache.assert_called_once_with('market_news:v1', empty)
        self.assertEqual(result['persistent_cache']['state'], 'refreshed')


if __name__ == '__main__':
    unittest.main()
