import unittest
from pydantic import ValidationError

from holdings_routes import _ask_tax_summary, _row_with_market, HoldingTransactionIn
from holdings_tax_runtime import fifo_realized_analysis


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

    def test_ask_withdrawal_within_contributions_is_not_taxable(self):
        tax = _ask_tax_summary(10000, 2500, 0)
        self.assertEqual(tax['remaining_tax_free_capital'], 7500)
        self.assertEqual(tax['taxable_withdrawal'], 0)
        self.assertEqual(tax['estimated_tax'], 0)

    def test_ask_withdrawal_above_contributions_uses_shielding_first(self):
        tax = _ask_tax_summary(10000, 13000, 1000)
        self.assertEqual(tax['withdrawal_above_contributions'], 3000)
        self.assertEqual(tax['shielding_used'], 1000)
        self.assertEqual(tax['taxable_withdrawal'], 2000)
        self.assertAlmostEqual(tax['estimated_tax'], 756.8)

    def test_buy_transaction_can_derive_amount_from_shares_and_price(self):
        tx = HoldingTransactionIn(transaction_type='buy', ticker='LSG', shares=100, price=45)
        self.assertIsNone(tx.amount)
        self.assertEqual(tx.shares * tx.price, 4500)

    def test_buy_transaction_requires_ticker(self):
        with self.assertRaises(ValidationError):
            HoldingTransactionIn(transaction_type='buy', shares=100, price=45)

    def test_fifo_uses_oldest_lot_first_on_taxable_account(self):
        tx = [
            {'id': 1, 'transaction_date': '2026-01-01', 'broker': 'Nordnet', 'account_type': 'Aksje- og fondskonto', 'transaction_type': 'buy', 'ticker': 'LSG', 'shares': 100, 'price': 40, 'amount': 4000},
            {'id': 2, 'transaction_date': '2026-02-01', 'broker': 'Nordnet', 'account_type': 'Aksje- og fondskonto', 'transaction_type': 'buy', 'ticker': 'LSG', 'shares': 100, 'price': 60, 'amount': 6000},
            {'id': 3, 'transaction_date': '2026-03-01', 'broker': 'Nordnet', 'account_type': 'Aksje- og fondskonto', 'transaction_type': 'sell', 'ticker': 'LSG', 'shares': 150, 'price': 70, 'amount': 10500},
        ]
        result = fifo_realized_analysis(tx, 2026)
        self.assertEqual(result['year_realized_trades'][0]['cost_basis'], 7000)
        self.assertEqual(result['net_realized_gain_loss'], 3500)
        self.assertAlmostEqual(result['estimated_tax_payable'], 1324.4)
        self.assertEqual(result['remaining_fifo_lots'][0]['shares'], 50)
        self.assertEqual(result['remaining_fifo_lots'][0]['average_fifo_cost'], 60)

    def test_fifo_does_not_tax_internal_ask_sale(self):
        tx = [
            {'id': 1, 'transaction_date': '2026-01-01', 'broker': 'Nordnet', 'account_type': 'ASK', 'transaction_type': 'buy', 'ticker': 'LSG', 'shares': 100, 'price': 40, 'amount': 4000},
            {'id': 2, 'transaction_date': '2026-02-01', 'broker': 'Nordnet', 'account_type': 'ASK', 'transaction_type': 'sell', 'ticker': 'LSG', 'shares': 100, 'price': 70, 'amount': 7000},
        ]
        result = fifo_realized_analysis(tx, 2026)
        self.assertEqual(result['year_realized_trades'], [])
        self.assertEqual(result['estimated_tax_payable'], 0)


if __name__ == '__main__':
    unittest.main()
