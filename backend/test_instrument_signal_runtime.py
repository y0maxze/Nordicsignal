import unittest

from instrument_signal_runtime import score_analytics


class InstrumentSignalModelTests(unittest.TestCase):
    def test_strong_fund_trend_gets_strong_signal(self):
        result = score_analytics({
            'return_1m_pct': 6,
            'return_3m_pct': 18,
            'return_ytd_pct': 25,
            'return_1y_pct': 30,
            'current': 110,
            'sma_50': 100,
            'above_sma_200': True,
            'volatility_1y_pct': 10,
            'max_drawdown_1y_pct': -8,
            'cagr_3y_pct': 15,
            'cagr_5y_pct': 12,
        }, 'Fond')
        self.assertEqual(result['signal'], 'Strong')
        self.assertGreaterEqual(result['score'], 72)
        self.assertEqual(result['coverage_pct'], 100.0)
        self.assertEqual(result['model'], 'history_trend_risk_v1')

    def test_weak_high_risk_etf_gets_risk_signal(self):
        result = score_analytics({
            'return_1m_pct': -10,
            'return_3m_pct': -20,
            'return_ytd_pct': -30,
            'return_1y_pct': -40,
            'current': 80,
            'sma_50': 100,
            'above_sma_200': False,
            'volatility_1y_pct': 50,
            'max_drawdown_1y_pct': -55,
            'cagr_3y_pct': -10,
            'cagr_5y_pct': -8,
        }, 'ETF')
        self.assertEqual(result['signal'], 'Risk')
        self.assertLess(result['score'], 52)
        self.assertIn('ETF', result['event'])

    def test_sparse_history_cannot_create_strong_signal(self):
        result = score_analytics({'return_1m_pct': 20}, 'Fond')
        self.assertEqual(result['signal'], 'Watch')
        self.assertLess(result['coverage_pct'], 40)
        self.assertLessEqual(result['score'], 71)


if __name__ == '__main__':
    unittest.main()
