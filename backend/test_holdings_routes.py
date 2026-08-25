import unittest

from holdings_routes import _row_with_market


class FakeProvider:
    def __init__(self, price=50.0, fail=False):
        self.price = price
        self.fail = fail

    def quote(self, ticker):
        if self.fail:
            raise RuntimeError('quote unavailable')
        return {'ticker': ticker, 'price': self.price, 'source': 'test'}


class HoldingsRouteTests(unittest.TestCase):
    def test_mark_to_market_profit(self):
        row = {'id': 1, 'ticker': 'LSG', 'shares': 100.0, 'average_cost': 40.0, 'broker': 'Nordnet', 'account_type': 'ASK'}
        item = _row_with_market(row, FakeProvider(50.0))
        self.assertEqual(item['invested'], 4000.0)
        self.assertEqual(item['market_value'], 5000.0)
        self.assertEqual(item['unrealized_pnl'], 1000.0)
        self.assertAlmostEqual(item['unrealized_pnl_pct'], 25.0)

    def test_quote_failure_keeps_cost_basis_without_inventing_market_value(self):
        row = {'id': 2, 'ticker': 'LSG', 'shares': 10.0, 'average_cost': 44.0, 'broker': 'Nordnet', 'account_type': 'ASK'}
        item = _row_with_market(row, FakeProvider(fail=True))
        self.assertEqual(item['invested'], 440.0)
        self.assertIsNone(item['current_price'])
        self.assertIsNone(item['market_value'])
        self.assertIsNone(item['unrealized_pnl'])
        self.assertIn('quote unavailable', item['quote_error'])


if __name__ == '__main__':
    unittest.main()
