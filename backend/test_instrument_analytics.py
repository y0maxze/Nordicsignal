import math
import unittest
from datetime import datetime, timezone

from instrument_analytics_runtime import calculate_analytics


class InstrumentAnalyticsTests(unittest.TestCase):
    def test_rising_history_produces_positive_returns_and_trend(self):
        start = int(datetime(2021, 1, 1, tzinfo=timezone.utc).timestamp())
        rows = []
        price = 100.0
        for day in range(365 * 5 + 10):
            rows.append((start + day * 86400, price))
            price *= 1.0002
        out = calculate_analytics(rows)
        self.assertGreater(out['return_1m_pct'], 0)
        self.assertGreater(out['return_1y_pct'], 0)
        self.assertGreater(out['cagr_3y_pct'], 0)
        self.assertGreater(out['cagr_5y_pct'], 0)
        self.assertTrue(out['above_sma_200'])
        self.assertAlmostEqual(out['max_drawdown_1y_pct'], 0.0, places=8)
        self.assertGreater(out['high_52w'], out['low_52w'])

    def test_drawdown_is_negative_and_never_presented_as_gain(self):
        start = int(datetime(2025, 1, 1, tzinfo=timezone.utc).timestamp())
        prices = [100 + i for i in range(40)] + [139 - i * 2 for i in range(25)] + [90 + i * 0.2 for i in range(40)]
        rows = [(start + i * 86400, p) for i, p in enumerate(prices)]
        out = calculate_analytics(rows)
        self.assertLess(out['max_drawdown_1y_pct'], 0)
        self.assertTrue(math.isfinite(out['max_drawdown_1y_pct']))
        self.assertGreater(out['volatility_1y_pct'], 0)


if __name__ == '__main__':
    unittest.main()
