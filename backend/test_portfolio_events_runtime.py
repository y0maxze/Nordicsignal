import unittest

from portfolio_events_runtime import _dedupe_and_sort, _events_for_one


class PortfolioEventRuntimeTests(unittest.TestCase):
    def test_holdings_events_surface_reports_insider_and_material_news(self):
        def reports(ticker, limit):
            self.assertEqual(ticker, 'MPCC')
            return {'items': [{'title': 'MPC Container Ships Reports Q2 2026 Results', 'url': 'https://issuer/q2', 'published_at': '2026-08-26T05:00:00+00:00', 'publisher': 'MPCC'}]}

        def insider(ticker):
            return {'items': [{'transaction_type': 'buy', 'person': 'Example Insider', 'role': 'CEO', 'trade_date': '2026-08-25', 'shares': 1000, 'price': 15.0, 'url': 'https://exchange/insider'}]}

        def news(ticker, limit):
            return {'items': [
                {'title': 'Major contract signed', 'category': 'Selskap', 'official': True, 'url': 'https://exchange/contract', 'published_at': '2026-08-24T08:00:00+00:00'},
                {'title': 'Broker opinion', 'category': 'Nyhet', 'official': False, 'url': 'https://media/opinion', 'published_at': '2026-08-24T09:00:00+00:00'},
                {'title': 'Duplicate Q2', 'category': 'Rapport', 'official': True, 'url': 'https://issuer/q2', 'published_at': '2026-08-26T05:00:00+00:00'},
            ]}

        events = _events_for_one({'ticker': 'MPCC', 'company_name': 'MPC Container Ships'}, news, reports, insider)
        kinds = [x['kind'] for x in events]
        self.assertIn('report', kinds)
        self.assertIn('insider', kinds)
        self.assertIn('announcement', kinds)
        self.assertFalse(any(x['title'] == 'Broker opinion' for x in events))
        buy = next(x for x in events if x['kind'] == 'insider')
        self.assertEqual(buy['direction'], 'buy')
        self.assertIn('Example Insider', buy['title'])

    def test_dedupe_keeps_one_event_per_canonical_url_and_sorts_newest_first(self):
        items = [
            {'ticker': 'MPCC', 'title': 'Q2 results', 'url': 'https://issuer/q2?utm_source=x', 'occurred_at': '2026-08-26T05:00:00+00:00', 'importance': 'high'},
            {'ticker': 'MPCC', 'title': 'Q2 results copy', 'url': 'https://issuer/q2', 'occurred_at': '2026-08-26T04:00:00+00:00', 'importance': 'high'},
            {'ticker': 'MPCC', 'title': 'Older event', 'url': 'https://issuer/old', 'occurred_at': '2026-08-20T05:00:00+00:00', 'importance': 'normal'},
        ]
        result = _dedupe_and_sort(items, 10)
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]['title'], 'Q2 results')


if __name__ == '__main__':
    unittest.main()
