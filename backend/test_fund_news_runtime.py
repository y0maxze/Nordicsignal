import unittest

from fund_news_runtime import _normalize_item, _query_variants


class FundNewsRuntimeTests(unittest.TestCase):
    def test_fund_name_and_symbol_are_used_as_news_queries(self):
        queries = _query_variants('OP0001OPBLIR', 'KLP AksjeGlobal Indeks N')
        self.assertEqual(queries[0], 'KLP AksjeGlobal Indeks N')
        self.assertIn('OP0001OPBLIR', queries)
        self.assertLessEqual(len(queries), 3)

    def test_direct_name_match_is_labeled_as_fund_news(self):
        item = _normalize_item(
            {'title': 'KLP updates global equity fund offering', 'publisher': 'Example', 'link': 'https://example.com'},
            'KLP AksjeGlobal Indeks N',
            'KLP AksjeGlobal Indeks N',
            'Fond',
        )
        self.assertEqual(item['category'], 'Fond')
        self.assertEqual(item['news_scope'], 'direct')

    def test_unmatched_context_is_explicitly_labeled_market_news(self):
        item = _normalize_item(
            {'title': 'Global markets rise after rate decision', 'publisher': 'Example', 'link': 'https://example.com'},
            'KLP AksjeGlobal',
            'KLP AksjeGlobal Indeks N',
            'Fond',
        )
        self.assertEqual(item['category'], 'Markedsnyhet')
        self.assertEqual(item['news_scope'], 'context')


if __name__ == '__main__':
    unittest.main()
