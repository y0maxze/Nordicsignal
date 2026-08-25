import unittest
from unittest.mock import patch

import global_search_runtime as search


class GlobalSearchRuntimeTests(unittest.TestCase):
    def test_local_stock_survives_global_provider_failure(self):
        local = [{
            'ticker': 'DNB', 'symbol': 'DNB', 'market_symbol': 'DNB.OL',
            'name': 'DNB Bank ASA', 'asset_class': 'Aksjer', 'tracked': True,
        }]
        with patch.object(search, '_local_search', return_value=local), patch.object(
            search, 'search_instruments', side_effect=RuntimeError('provider down')
        ):
            out = search.search_all(object(), 'dnb', 20)
        self.assertEqual(out['items'][0]['ticker'], 'DNB')
        self.assertTrue(out['items'][0]['tracked'])
        self.assertIn('temporarily unavailable', out['warning'])

    def test_global_fund_and_etf_are_classified_and_merged(self):
        global_rows = [
            {'symbol': 'ABC', 'ticker': 'ABC', 'name': 'ABC Global Fund', 'asset_class': 'Fond'},
            {'symbol': 'XYZ', 'ticker': 'XYZ', 'name': 'XYZ ETF', 'asset_class': 'ETF'},
        ]
        with patch.object(search, '_local_search', return_value=[]), patch.object(
            search, 'search_instruments', return_value=global_rows
        ):
            out = search.search_all(object(), 'global', 20)
        self.assertEqual([x['asset_class'] for x in out['items']], ['Fond', 'ETF'])
        self.assertFalse(any(x['tracked'] for x in out['items']))


if __name__ == '__main__':
    unittest.main()
