import unittest
from pathlib import Path

import http_cache_runtime
from insider_fresh_fallback_runtime import normalize_items


ROOT = Path(__file__).resolve().parents[1]


class InsiderEndToEndRegressionTests(unittest.TestCase):
    def test_insider_http_response_is_not_body_cached(self):
        self.assertEqual(http_cache_runtime._ttl_for('/api/insider/LSG'), 0)
        self.assertEqual(http_cache_runtime._ttl_for('/api/insider/MPCC'), 0)

    def test_stock_enhancement_receives_canonical_lexical_data_object(self):
        bridge = (ROOT / 'frontend' / 'stock_data_bridge.js').read_text(encoding='utf-8')
        worker = (ROOT / 'worker.js').read_text(encoding='utf-8')
        self.assertIn('window.data = data', bridge)
        self.assertIn('/stock_data_bridge.js', worker)
        self.assertLess(worker.index('/stock_data_bridge.js'), worker.index('/stock_extras.js'))

    def test_leroy_recommended_reading_duplicates_collapse_to_real_trades(self):
        rows = [
            {
                'date': '2026-08-25', 'trade_date': '2026-08-25', 'direction': 'buy',
                'transaction_type': 'buy', 'shares': 14500,
                'person': 'Lerøy Seafood Group ASA Lerøy Seafood Group ASA Sjur Malm',
                'insider': 'Lerøy Seafood Group ASA Lerøy Seafood Group ASA Sjur Malm',
                'role': 'CFO', 'verified_detail': True,
                'summary': 'Sjur Malm, CFO, purchased 14,500 shares.',
                'url': 'https://www.globenewswire.com/news-release/2026/08/25/1/0/en/leroy.html',
            },
            # Same economic trade repeated as Recommended Reading on an older page.
            # This row is impossible because its trade date is after that page date.
            {
                'date': '2026-08-25', 'trade_date': '2026-08-25', 'direction': 'buy',
                'transaction_type': 'buy', 'shares': 14500,
                'person': 'Primary Insider Transactions Sjur Malm',
                'insider': 'Primary Insider Transactions Sjur Malm',
                'role': 'CFO', 'verified_detail': True,
                'summary': 'Recommended Reading Sjur Malm purchased 14,500 shares.',
                'url': 'https://www.globenewswire.com/news-release/2026/08/22/2/0/en/other-release.html',
            },
            {
                'date': '2026-08-25', 'trade_date': '2026-08-25', 'direction': 'buy',
                'transaction_type': 'buy', 'shares': 11500,
                'person': 'Ivar Wulff', 'insider': 'Ivar Wulff',
                'role': 'COO Market Operations', 'verified_detail': True,
                'url': 'https://www.globenewswire.com/news-release/2026/08/25/1/0/en/leroy.html',
            },
            {
                'date': '2026-08-21', 'trade_date': '2026-08-21', 'direction': 'buy',
                'transaction_type': 'buy', 'shares': 357542,
                'entity': 'Primary Insider Transaction FERD AS',
                'insider': 'Primary Insider Transaction FERD AS',
                'role': 'Representert ved Are Dragesund', 'verified_detail': True,
                'url': 'https://www.globenewswire.com/news-release/2026/08/22/3/0/en/leroy.html',
            },
            # Same FERD transaction appearing in a later page's recommendations.
            {
                'date': '2026-08-21', 'trade_date': '2026-08-21', 'direction': 'buy',
                'transaction_type': 'buy', 'shares': 357542,
                'entity': 'Lerøy Seafood Group ASA Lerøy Seafood Group ASA FERD AS',
                'insider': 'Lerøy Seafood Group ASA Lerøy Seafood Group ASA FERD AS',
                'role': 'Representert ved Are Dragesund', 'verified_detail': True,
                'summary': 'Recommended Reading',
                'url': 'https://www.globenewswire.com/news-release/2026/08/25/1/0/en/leroy.html',
            },
            {
                'date': '2026-08-21', 'trade_date': '2026-08-21', 'direction': 'buy',
                'transaction_type': 'buy', 'shares': 12000,
                'person': 'Primary Insider Transaction Henning Beltestad',
                'insider': 'Primary Insider Transaction Henning Beltestad',
                'role': 'CEO', 'verified_detail': True,
                'url': 'https://www.globenewswire.com/news-release/2026/08/21/4/0/en/leroy.html',
            },
        ]
        cleaned = normalize_items(rows, 'LSG')
        self.assertEqual(len(cleaned), 4)
        actors = {x.get('person') or x.get('entity') or x.get('insider') for x in cleaned}
        self.assertEqual(actors, {'Sjur Malm', 'Ivar Wulff', 'FERD AS', 'Henning Beltestad'})
        self.assertEqual(sum(x.get('direction') == 'buy' for x in cleaned), 4)


if __name__ == '__main__':
    unittest.main()
