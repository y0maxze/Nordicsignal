import unittest

from insider_fresh_fallback_runtime import discover_release_links, merge_insider_result


class FreshInsiderFallbackTests(unittest.TestCase):
    def test_discovers_leroy_release_from_mixed_fresh_feed(self):
        html = '''
        <html><body>
          <a href="/news-release/2026/08/25/1/0/en/other-company-results.html">Other Company Results</a>
          <a href="/news-release/2026/08/25/2/0/en/ler%C3%B8y-seafood-group-asa-primary-insider-transactions.html">Lerøy Seafood Group ASA: Primary Insider Transactions</a>
          <a href="/news-release/2026/08/19/3/0/en/ler%C3%B8y-seafood-group-asa-q2-2026-results.html">Lerøy Seafood Group ASA: Q2 2026 Results</a>
        </body></html>
        '''
        rows = discover_release_links(
            html,
            'https://rss.globenewswire.com/news/consumer-products-services/food-beverage/load/more',
            'LSG',
        )
        self.assertEqual(len(rows), 2)
        self.assertIn('primary-insider-transactions', rows[0][0])

    def test_fresh_rows_replace_empty_zero_counts(self):
        base = {
            'ticker': 'LSG',
            'items': [],
            'status': 'live',
            'buy_count': 0,
            'sell_count': 0,
            'verified_detail_count': 0,
            'source': 'Euronext Oslo Børs Newspoint',
        }
        fresh = [
            {
                'ticker': 'LSG', 'date': '2026-08-25', 'trade_date': '2026-08-25',
                'direction': 'buy', 'transaction_type': 'buy', 'shares': 14500,
                'person': 'Sjur Malm', 'insider': 'Sjur Malm', 'role': 'CFO',
                'verified_detail': True, 'url': 'https://example/1',
            },
            {
                'ticker': 'LSG', 'date': '2026-08-25', 'trade_date': '2026-08-25',
                'direction': 'buy', 'transaction_type': 'buy', 'shares': 11500,
                'person': 'Ivar Wulff', 'insider': 'Ivar Wulff', 'role': 'COO Market Operations',
                'verified_detail': True, 'url': 'https://example/1',
            },
            {
                'ticker': 'LSG', 'date': '2026-08-20', 'trade_date': '2026-08-20',
                'direction': 'sell', 'transaction_type': 'sell', 'shares': 1000,
                'person': 'Example Seller', 'insider': 'Example Seller', 'role': 'Board member',
                'verified_detail': True, 'url': 'https://example/2',
            },
        ]
        result = merge_insider_result(base, fresh, 'LSG')
        self.assertEqual(len(result['items']), 3)
        self.assertEqual(result['buy_count'], 2)
        self.assertEqual(result['sell_count'], 1)
        self.assertEqual(result['verified_detail_count'], 3)
        self.assertEqual(result['signal'], 'buying')
        self.assertEqual(result['fresh_fallback_count'], 3)
        self.assertIn('GlobeNewswire fresh issuer feed', result['source'])


if __name__ == '__main__':
    unittest.main()
