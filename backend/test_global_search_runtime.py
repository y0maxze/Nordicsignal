import unittest
from unittest.mock import patch

import global_search_runtime as search
import company_context


class GlobalSearchRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.research = patch.object(search, '_research_search', return_value=[])
        self.research.start()
        self.addCleanup(self.research.stop)

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


def test_research_ticker_is_found_without_scoring_or_currency_inference():
    issuer = {'TECH': {'company': 'Techstep ASA'}}
    with patch.object(company_context, 'universe', return_value=issuer), patch.object(
        search, '_local_search', return_value=[{'ticker':'CMBTO','symbol':'CMBTO','name':'CMB.TECH','tracked':True}]
    ), patch.object(search, 'search_instruments', side_effect=RuntimeError('provider down')):
        for query in ['TECH', 'tech.ol', 'Techstep']:
            result = search.search_all(object(), query)
            tech = next(x for x in result['items'] if x['ticker']=='TECH')
            assert tech['symbol']=='TECH.OL'
            assert tech['tracked'] is False and tech['has_signal'] is False
            assert 'currency' not in tech and 'score' not in tech
            assert result['warning']
            if query != 'Techstep':
                assert result['items'][0]['ticker']=='TECH'


def test_research_search_uses_only_reconciled_identity_and_preserves_tracked_result():
    with patch.object(company_context, 'universe', return_value={'TECH': {'company':'Techstep ASA'}}):
        assert search._research_search('Bio-Techne') == []
        local = {'ticker':'TECH','symbol':'TECH','name':'Techstep ASA','tracked':True,'has_signal':True}
        with patch.object(search, '_local_search', return_value=[local]), patch.object(search,'search_instruments',return_value=[{'symbol':'TECH.OL'}]):
            result = search.search_all(object(),'TECH')
            assert len(result['items'])==1 and result['items'][0]['tracked'] is True


def test_research_snapshot_failure_retains_other_results_and_exposes_partial_coverage():
    with patch.object(search,'_research_search',side_effect=RuntimeError('unavailable')), patch.object(
        search,'_local_search',return_value=[]
    ), patch.object(search,'search_instruments',return_value=[{'symbol':'DNB.OL'}]):
        result=search.search_all(object(),'DNB')
        assert len(result['items'])==1
        assert result['warning']=='Issuer snapshot search temporarily unavailable'
