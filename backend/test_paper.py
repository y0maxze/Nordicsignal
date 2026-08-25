import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from fastapi import HTTPException
from extra_api import _backtest, _buy_with_cash, _fee_for_gross, _historical_rows, _xirr


class FakeProvider:
    BASE = 'https://query1.finance.yahoo.com'

    def symbol(self, ticker):
        return ticker

    def _get(self, url, params):
        if int(params.get('period1', 0)) > 1677628800:
            return {'chart': {'result': []}}
        return {
            'chart': {
                'result': [{
                    'timestamp': [1672531200, 1675209600, 1677628800],
                    'indicators': {'quote': [{'close': [100, 110, 120]}]},
                    'events': {},
                }]
            }
        }


class PaperBacktestTests(unittest.TestCase):
    def test_xirr_one_year_doubles(self):
        flows = [(datetime(2023, 1, 1, tzinfo=timezone.utc), -100.0), (datetime(2024, 1, 1, tzinfo=timezone.utc), 200.0)]
        self.assertAlmostEqual(_xirr(flows), 1.0, delta=0.005)

    def test_fee_helpers_never_overspend_cash(self):
        shares, gross, fee = _buy_with_cash(1000, 100, 1.0, 10.0)
        self.assertGreater(shares, 0)
        self.assertAlmostEqual(gross + fee, 1000, places=8)
        self.assertAlmostEqual(fee, _fee_for_gross(gross, 1.0, 10.0), places=8)

    def test_fixed_fee_larger_than_cash_blocks_purchase(self):
        self.assertEqual(_buy_with_cash(0.5, 100, 0, 1.0), (0.0, 0.0, 0.0))

    def test_historical_rows_filters_missing_closes(self):
        class MissingCloseProvider(FakeProvider):
            def _get(self, url, params):
                return {'chart': {'result': [{'timestamp': [1, 2, 3], 'indicators': {'quote': [{'close': [10, None, 12]}]}}]}}
        rows = _historical_rows(MissingCloseProvider(), 'LSG', 1, 4)
        self.assertEqual([x['close'] for x in rows], [10, 12])

    def test_backtest_monthly_contributions(self):
        with patch('dividend_runtime.fetch_dividend_events', return_value=[]):
            result = _backtest(FakeProvider(), 'LSG', '2023-01-01', '2023-03-01', 1000, 500, False, benchmark=None)
        self.assertEqual(result['invested'], 2000)
        contributions = [x for x in result['transactions'] if x['side'] == 'contribution']
        self.assertEqual([x['date'] for x in contributions], ['2023-01-01', '2023-02-01', '2023-03-01'])
        self.assertAlmostEqual(result['shares'], 10 + 500 / 110 + 500 / 120, places=8)
        self.assertEqual(result['fees_paid'], 0)
        self.assertAlmostEqual(result['final_equity'], result['cash'] + result['shares'] * 120, places=8)
        self.assertAlmostEqual(result['return'], result['final_equity'] - result['invested'], places=8)

    def test_transaction_fee_is_applied(self):
        with patch('dividend_runtime.fetch_dividend_events', return_value=[]):
            result = _backtest(FakeProvider(), 'LSG', '2023-01-01', '2023-01-31', 1000, 0, False, fee_pct=1.0, benchmark=None)
        self.assertGreater(result['fees_paid'], 0)
        self.assertLess(result['shares'], 10)
        self.assertGreaterEqual(result['cash'], -1e-8)

    def test_lump_sum_strategy_does_not_add_monthly_money(self):
        with patch('dividend_runtime.fetch_dividend_events', return_value=[]):
            result = _backtest(FakeProvider(), 'LSG', '2023-01-01', '2023-03-01', 1000, 500, False, strategy='lump_sum', benchmark=None)
        self.assertEqual(result['invested'], 1000)
        self.assertEqual(result['strategy'], 'lump_sum')
        self.assertAlmostEqual(result['shares'], 10, places=8)

    def test_sma_strategy_is_supported_and_holds_cash_before_signal(self):
        with patch('dividend_runtime.fetch_dividend_events', return_value=[]):
            result = _backtest(FakeProvider(), 'LSG', '2023-01-01', '2023-03-01', 1000, 500, False, strategy='sma_cross', benchmark=None)
        self.assertEqual(result['strategy'], 'sma_cross')
        self.assertEqual(result['invested'], 2000)
        self.assertEqual(result['shares'], 0)
        self.assertEqual(result['cash'], 2000)
        self.assertEqual(result['final_equity'], 2000)

    def test_dividend_reinvests_into_new_shares(self):
        dividend = [{'timestamp': 1675209600, 'date': '2023-02-01', 'amount': 2.0}]
        with patch('dividend_runtime.fetch_dividend_events', return_value=dividend):
            result = _backtest(FakeProvider(), 'LSG', '2023-01-01', '2023-03-01', 1000, 0, True, benchmark=None)
        self.assertEqual(result['dividend_events'], 1)
        self.assertAlmostEqual(result['dividends'], 20.0, places=8)
        self.assertTrue(any(x['side'] == 'dividend_reinvest' for x in result['transactions']))
        self.assertGreater(result['shares'], 10)

    def test_dividend_can_remain_as_cash(self):
        dividend = [{'timestamp': 1675209600, 'date': '2023-02-01', 'amount': 2.0}]
        with patch('dividend_runtime.fetch_dividend_events', return_value=dividend):
            result = _backtest(FakeProvider(), 'LSG', '2023-01-01', '2023-03-01', 1000, 0, False, benchmark=None)
        self.assertEqual(result['dividend_events'], 1)
        self.assertAlmostEqual(result['dividends'], 20.0, places=8)
        self.assertTrue(any(x['side'] == 'dividend_cash' for x in result['transactions']))
        self.assertAlmostEqual(result['cash'], 20.0, places=8)

    def test_small_dividend_does_not_disappear_when_fixed_fee_is_larger(self):
        dividend = [{'timestamp': 1675209600, 'date': '2023-02-01', 'amount': 0.01}]
        with patch('dividend_runtime.fetch_dividend_events', return_value=dividend):
            result = _backtest(FakeProvider(), 'LSG', '2023-01-01', '2023-03-01', 1000, 0, True, fixed_fee=1.0, benchmark=None)
        self.assertAlmostEqual(result['dividends'], 0.0999, places=8)
        self.assertTrue(any(x['side'] == 'dividend_cash' for x in result['transactions']))
        self.assertAlmostEqual(result['cash'], 0.0999, places=8)

    def test_invalid_strategy_is_rejected(self):
        with self.assertRaises(HTTPException) as ctx:
            _backtest(FakeProvider(), 'LSG', '2023-01-01', '2023-03-01', 1000, 0, False, strategy='magic', benchmark=None)
        self.assertEqual(ctx.exception.status_code, 400)

    def test_reversed_date_range_is_rejected(self):
        with self.assertRaises(HTTPException) as ctx:
            _backtest(FakeProvider(), 'LSG', '2023-03-01', '2023-01-01', 1000, 0, False, benchmark=None)
        self.assertEqual(ctx.exception.status_code, 400)

    def test_no_data_period_is_rejected(self):
        with self.assertRaises(HTTPException) as ctx:
            _backtest(FakeProvider(), 'LSG', '2023-04-01', '2023-05-01', 1000, 0, False, benchmark=None)
        self.assertEqual(ctx.exception.status_code, 404)


if __name__ == '__main__':
    unittest.main()
