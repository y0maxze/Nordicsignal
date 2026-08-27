import unittest

import general_news_runtime
import insider_company_cleanup_runtime as cleanup


class InsiderCompanyCleanupTests(unittest.TestCase):
    def test_xplora_title_resolves_to_tracked_ticker(self):
        ticker, company = cleanup.canonical_issuer(
            'XPLORA TECHNOLOGIES',
            'Xplora Technologies AS: Mandatory notification of purchase by primary insiders',
            None,
        )
        self.assertEqual(ticker, 'XPLRA')
        self.assertEqual(company, 'Xplora Technologies')

    def test_correction_title_still_resolves_xplora(self):
        ticker, company = cleanup.canonical_issuer(
            'XPLORA TECHNOLOGIES',
            'Correction: Xplora Technologies AS: Mandatory notification of purchase by primary insiders',
            None,
        )
        self.assertEqual(ticker, 'XPLRA')
        self.assertEqual(company, 'Xplora Technologies')

    def test_related_security_noise_is_removed_from_company_column(self):
        ticker, company = cleanup.canonical_issuer(
            'YARA INTERNATIONAL, Yara International ASA 17/27 2,90%, Yara International ASA 21/26 FRN',
            'Mandatory notification of trade',
            None,
        )
        self.assertEqual(ticker, 'YAR')
        self.assertEqual(company, 'Yara International')

    def test_current_euronext_row_is_cleaned_before_market_feed_uses_it(self):
        html = '''
        <table><tr>
          <td>19 Aug 2026 16:25 CEST</td>
          <td>XPLORA TECHNOLOGIES</td>
          <td><a class="standardRightCompanyPressRelease" data-node-nid="12345">Xplora Technologies AS: Mandatory notification of purchase by primary insiders</a></td>
          <td>Consumer Electronics</td>
          <td>Mandatory notification of trade primary insiders</td>
        </tr></table>
        '''
        rows = general_news_runtime.parse_general_euronext_html(html, 10)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['ticker'], 'XPLRA')
        self.assertEqual(rows[0]['company'], 'Xplora Technologies')
        self.assertEqual(rows[0]['category'], 'Insider')


if __name__ == '__main__':
    unittest.main()
