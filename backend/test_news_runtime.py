import unittest

from news_runtime import _dedupe, parse_euronext_html, parse_ir_html


class MultiSourceNewsTests(unittest.TestCase):
    def test_euronext_parser_keeps_selected_issuer_and_original_link(self):
        html = '''
        <table>
          <tr><td>22 Aug 2026 06:30 CEST</td><td>Lerøy Seafood Group ASA</td>
              <td><a href="/en/products/equities/company-news/2026-08-22-leroy-primary-insider">Lerøy Seafood Group ASA: Primary insider transaction</a></td>
              <td>Mandatory notification of trade primary insiders</td></tr>
          <tr><td>22 Aug 2026 07:00 CEST</td><td>Skanska AB</td>
              <td><a href="/en/products/equities/company-news/2026-08-22-skanska">Skanska wins contract</a></td>
              <td>Contracts</td></tr>
        </table>'''
        items = parse_euronext_html(html, 'LSG', 'Lerøy Seafood', 10)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]['category'], 'Insider')
        self.assertTrue(items[0]['official'])
        self.assertIn('live.euronext.com/en/products/equities/company-news/', items[0]['url'])
        self.assertIsNotNone(items[0]['published_at'])

    def test_ir_parser_keeps_report_links_and_drops_navigation(self):
        html = '''
          <a href="/about">About us</a>
          <a href="/investor/q2-2026-report.pdf">Q2 2026 report</a>
          <a href="/investor/q2-webcast">Q2 2026 results webcast</a>
        '''
        items = parse_ir_html(html, 'https://www.leroyseafood.com/en/investor/', 'LSG', 'Lerøy Seafood', 10)
        self.assertEqual(len(items), 2)
        self.assertTrue(all(x['official'] for x in items))
        self.assertTrue(all(x['source_type'] == 'issuer_ir' for x in items))
        self.assertEqual(items[0]['category'], 'Rapport')

    def test_dedupe_prefers_exchange_copy_of_same_headline(self):
        items = [
            {'title': 'Lerøy Seafood Group ASA: Q2 2026 results', 'url': 'https://media.example/a', 'source_type': 'media', 'published_at': '2026-08-19T05:00:00+00:00'},
            {'title': 'Lerøy Seafood Group ASA: Q2 2026 results', 'url': 'https://live.euronext.com/a', 'source_type': 'exchange', 'published_at': '2026-08-19T04:00:00+00:00', 'official': True},
        ]
        result = _dedupe(items, 10)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['source_type'], 'exchange')

    def test_short_generic_ticker_is_not_enough_for_issuer_match(self):
        html = '''<table><tr><td>22 Aug 2026 06:30 CEST</td><td>Some Company</td>
        <td><a href="/en/products/equities/company-news/2026-08-22-other">LSG market note for another issuer</a></td></tr></table>'''
        self.assertEqual(parse_euronext_html(html, 'LSG', 'Lerøy Seafood', 10), [])


if __name__ == '__main__':
    unittest.main()
