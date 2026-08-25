import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from extra_api import _backtest, _xirr


class FakeProvider:
    def historical(self, ticker, period='max'):
        return [
            {'timestamp': 1672531200, 'date': '2023-01-01T00:00:00+00:00', 'close': 100},
            {'timestamp': 1675209600, 'date': '2023-02-01T00:00:00+00:00', 'close': 110},
            {'timestamp': 1677628800, 'date': '2023-03-01T00:00:00+00:00', 'close': 120},
        ]


class PaperBacktestTests(unittest.TestCase):
    def test_xirr_one_year_doubles(self):
        flows = [
            (datetime(2023, 1, 1, tzinfo=timezone.utc), -100.0),
            (datetime(2024, 1, 1, tzinfo=timezone.utc), 200.0),
        ]
        self.assertAlmostEqual(_xirr(flows), 1.0, delta=0.005)

    def test_backtest_monthly_contributions(self):
        provider = FakeProvider()
        with patch('extra_api._dividends', return_value=[]):
            result = _backtest(provider, 'LSG', '2023-01-01', '2023-03-01', 1000, 500, False)
        self.assertEqual(result['invested'], 2000)
        self.assertEqual([x['date'] for x in result['transactions']], ['2023-01-01', '2023-02-01', '2023-03-01'])
        self.assertAlmostEqual(result['shares'], 10 + 500 / 110 + 500 / 120, places=8)

    def test_no_data_period_is_rejected(self):
        provider = FakeProvider()
        with self.assertRaises(Exception):
            _backtest(provider, 'LSG', '2023-04-01', '2023-05-01', 1000, 0, False)


if __name__ == '__main__':
    unittest.main()
