import unittest

from portfolio_events_runtime import (
    _canonical_event_ticker,
    _dedupe_and_sort,
    _enrich_market_reaction,
    _events_for_one,
)


class _FakeProvider:
    BASE = 'https://example.test'

    def symbol(self, ticker):
        return ticker if '.' in ticker else ticker + '.OL'

    def _get(self, url, params=None):
        return {
            'chart': {
                'result': [{
                    'timestamp': [
                        1787616000,  # 2026-08-25 UTC
                        1787702400,  # 2026-08-26 UTC
                    ],
                    'indicators': {'quote': [{'close': [20.0, 22.0]}]},
                }]
            }
        }


class PortfolioEventRuntimeTests(unittest.TestCase):
    def test_oslo_market_symbol_is_normalized_for_event_routes(self):
        self.assertEqual(_canonical_event_ticker('MPCC.OL'), 'MPCC')
        self.assertEqual(_canonical_event_ticker('lsg.ol'), 'LSG')
        self.assertEqual(_canonical_event_ticker('EQNR'), 'EQNR')

        seen = []

        def reports(ticker, limit):
            seen.append(ticker)
            return {'items': []}

        _events_for_one(
            {'ticker': 'MPCC.OL', 'company_name': 'MPC Container Ships'},
            lambda ticker, limit: {'items': []},
            reports,
            lambda ticker: {'items': []},
        )
        self.assertEqual(seen, ['MPCC'])

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

        report = next(x for x in events if x['kind'] == 'report')
        self.assertIn('guiding', report['brief'].lower())
        self.assertEqual(report['brief_tone'], 'watch')

        buy = next(x for x in events if x['kind'] == 'insider')
        self.assertEqual(buy['direction'], 'buy')
        self.assertIn('Example Insider', buy['title'])
        self.assertIn('1 000', buy['brief'])
        self.assertIn('positivt interesse-signal', buy['brief'])
        self.assertEqual(buy['brief_tone'], 'positive')

        contract = next(x for x in events if x['kind'] == 'announcement')
        self.assertIn('kontrakt', contract['brief'].lower())

    def test_report_brief_includes_actual_event_day_market_reaction(self):
        event = {
            'ticker': 'MPCC',
            'company': 'MPC Container Ships',
            'kind': 'report',
            'title': 'MPC Container Ships Reports Q2 2026 Results',
            'occurred_at': '2026-08-26T05:00:00+00:00',
            'importance': 'high',
        }
        events = _enrich_market_reaction([event], _FakeProvider(), 'MPCC')
        self.assertEqual(len(events), 1)
        reaction = events[0]['market_reaction']
        self.assertEqual(reaction['basis'], 'event_day')
        self.assertAlmostEqual(reaction['change_pct'], 10.0)
        self.assertIn('Q2-rapporten', events[0]['brief'])
        self.assertIn('steg', events[0]['brief'])
        self.assertIn('10,00 %', events[0]['brief'])
        self.assertIn('positiv', events[0]['brief'])
        self.assertEqual(events[0]['brief_tone'], 'positive')

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
