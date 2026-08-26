import unittest

from general_news_runtime import _clean_company_news, _is_generic_ir_navigation, parse_general_euronext_html


class GeneralNewsRuntimeTests(unittest.TestCase):
    def test_generic_ir_navigation_is_not_news(self):
        generic = {
            'title': 'Annual reports',
            'source_type': 'issuer_ir',
            'published_at': None,
            'official': True,
        }
        real = {
            'title': 'Annual report 2025',
            'source_type': 'issuer_ir',
            'published_at': None,
            'official': True,
        }
        self.assertTrue(_is_generic_ir_navigation(generic))
        self.assertFalse(_is_generic_ir_navigation(real))

    def test_company_feed_removes_ir_menu_links(self):
        data = {
            'items': [
                {'title': 'Financial calendar', 'source_type': 'issuer_ir', 'official': True},
                {'title': 'Reports and webcast', 'source_type': 'issuer_ir', 'official': True},
                {'title': 'MPC Container Ships Reports Q2 2026 Results', 'source_type': 'issuer_ir', 'official': True},
                {'title': 'Broker raises target price', 'source_type': 'media', 'official': False},
            ]
        }
        result = _clean_company_news(data)
        titles = [x['title'] for x in result['items']]
        self.assertNotIn('Financial calendar', titles)
        self.assertNotIn('Reports and webcast', titles)
        self.assertIn('MPC Container Ships Reports Q2 2026 Results', titles)
        self.assertIn('Broker raises target price', titles)
        self.assertEqual(result['official_count'], 1)
        self.assertEqual(result['media_count'], 1)

    def test_general_euronext_parser_keeps_latest_announcement(self):
        html = '''
        <table><tr>
          <td>26 Aug 2026 12:34 CEST</td>
          <td><a href="/en/products/equities/company-news/2026-08-26-mpcc-q2">MPCC: Q2 2026 results</a></td>
        </tr></table>
        '''
        items = parse_general_euronext_html(html, 10)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]['ticker'], 'MPCC')
        self.assertEqual(items[0]['category'], 'Rapport')
        self.assertTrue(items[0]['official'])
        self.assertIsNotNone(items[0]['published_at'])


if __name__ == '__main__':
    unittest.main()
