import unittest

from news_cache_limits_runtime import BoundedTextCache, _MAX_ENTRIES, _MAX_ITEM_BYTES, _MAX_TOTAL_BYTES


class NewsCacheLimitTests(unittest.TestCase):
    def test_cache_evicts_to_entry_limit(self):
        cache = BoundedTextCache()
        for i in range(_MAX_ENTRIES + 3):
            cache[f'url-{i}'] = (0, 'small page')
        self.assertLessEqual(len(cache), _MAX_ENTRIES)
        self.assertNotIn('url-0', cache)

    def test_oversized_page_is_not_retained(self):
        cache = BoundedTextCache()
        cache['large'] = (0, 'x' * (_MAX_ITEM_BYTES + 1))
        self.assertNotIn('large', cache)
        self.assertEqual(cache.total_bytes, 0)

    def test_total_byte_budget_is_enforced(self):
        cache = BoundedTextCache()
        payload = 'x' * min(500_000, _MAX_ITEM_BYTES)
        for i in range(20):
            cache[f'url-{i}'] = (0, payload)
        self.assertLessEqual(cache.total_bytes, _MAX_TOTAL_BYTES)


if __name__ == '__main__':
    unittest.main()
