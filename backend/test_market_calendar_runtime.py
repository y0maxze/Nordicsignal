import unittest
from unittest.mock import patch
from datetime import date

import market_calendar_runtime as calendar


HTML = '''
<table>
  <thead><tr><th>Date</th><th>Company / Issuer</th><th>Event</th></tr></thead>
  <tbody>
    <tr><td>26/08/2026</td><td>MPC Container Ships ASA</td><td><a href="https://newsweb.oslobors.no/message/1">Half-yearly Report</a></td></tr>
    <tr><td>05/11/2026</td><td>MPC Container Ships ASA</td><td><a href="https://newsweb.oslobors.no/message/2">Quarterly Report - Q3</a></td></tr>
    <tr><td>12/11/2026</td><td>Lerøy Seafood Group ASA</td><td><a href="https://newsweb.oslobors.no/message/3">Annual General Meeting</a></td></tr>
    <tr><td>09/01/2027</td><td>Other Company ASA</td><td><a href="https://newsweb.oslobors.no/message/4">Capital Markets Day</a></td></tr>
  </tbody>
</table>
'''


class MarketCalendarRuntimeTests(unittest.TestCase):
    def test_parser_classifies_reports_and_meetings(self):
        items = calendar.parse_calendar_html(HTML)
        self.assertEqual(len(items), 4)
        self.assertEqual(items[0]['event_type'], 'report')
        self.assertEqual(items[0]['event_label'], 'Halvårsrapport')
        self.assertEqual(items[1]['event_label'], 'Q3-rapport')
        self.assertEqual(items[2]['event_type'], 'meeting')
        self.assertEqual(items[2]['event_label'], 'Generalforsamling')
        self.assertTrue(items[0]['official'])

    def test_holdings_calendar_matches_issuer_name_and_future_window(self):
        raw = calendar.parse_calendar_html(HTML)
        stocks = [
            {'ticker': 'MPCC', 'name': 'MPC Container Ships'},
            {'ticker': 'LSG', 'name': 'Lerøy Seafood'},
        ]
        holdings = {'MPCC'}
        with patch.object(calendar, '_fetch_calendar_pages', return_value=(raw, [])), patch.object(
            calendar, '_load_reference_companies', return_value=(stocks, holdings)
        ):
            result = calendar.build_calendar(days=90, limit=20, holdings_only=True, today=date(2026, 8, 26))
        self.assertEqual(result['scope'], 'holdings')
        self.assertEqual([x['ticker'] for x in result['items']], ['MPCC', 'MPCC'])
        self.assertEqual([x['days_until'] for x in result['items']], [0, 71])
        self.assertTrue(all(x['in_holdings'] for x in result['items']))

    def test_market_calendar_excludes_past_and_outside_horizon(self):
        raw = calendar.parse_calendar_html(HTML)
        stocks = [{'ticker': 'MPCC', 'name': 'MPC Container Ships'}]
        with patch.object(calendar, '_fetch_calendar_pages', return_value=(raw, [])), patch.object(
            calendar, '_load_reference_companies', return_value=(stocks, set())
        ):
            result = calendar.build_calendar(days=10, limit=20, holdings_only=False, today=date(2026, 8, 27))
        self.assertEqual(result['items'], [])

    def test_oslo_suffix_is_canonicalized(self):
        self.assertEqual(calendar._ticker('MPCC.OL'), 'MPCC')
        self.assertEqual(calendar._ticker('LSG'), 'LSG')


if __name__ == '__main__':
    unittest.main()
