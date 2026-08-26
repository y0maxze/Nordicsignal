import unittest
from unittest.mock import patch

from issuer_reports_runtime import _is_financial_report, _merge_report_items, issuer_report_items


class IssuerReportsRuntimeTests(unittest.TestCase):
    def test_q2_results_is_a_report_but_invitation_is_not(self):
        self.assertTrue(_is_financial_report('MPC Container Ships Reports Q2 2026 Results'))
        self.assertTrue(_is_financial_report('Financial Report Q2 2026'))
        self.assertFalse(_is_financial_report('MPCC: Invitation to Q2 2026 Earnings Call'))

    def test_mpcc_official_news_page_can_supply_fresh_report(self):
        html = '''
          <a href="/news/2026/mpc-container-ships-reports-q2-2026-results/">MPC Container Ships Reports Q2 2026 Results</a>
          <a href="/news/2026/mpcc-invitation-to-q2-2026-earnings-call/">MPCC: Invitation to Q2 2026 Earnings Call</a>
        '''
        with patch('issuer_reports_runtime.news_runtime._fetch_text', return_value=html):
            items, source = issuer_report_items('MPCC', 'MPC Container Ships ASA', 12)
        self.assertEqual(source, 'https://www.mpc-container.com/news/')
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]['category'], 'Rapport')
        self.assertIn('Q2 2026 Results', items[0]['title'])
        self.assertTrue(items[0]['official'])

    def test_official_issuer_copy_deduplicates_same_report(self):
        official = [{'title': 'MPC Container Ships Reports Q2 2026 Results', 'url': 'https://www.mpc-container.com/q2', 'official': True}]
        base = [{'title': 'MPC Container Ships Reports Q2 2026 Results', 'url': 'https://media.example/q2'}]
        merged = _merge_report_items(base, official, 12)
        self.assertEqual(len(merged), 1)
        self.assertTrue(merged[0]['official'])


if __name__ == '__main__':
    unittest.main()
