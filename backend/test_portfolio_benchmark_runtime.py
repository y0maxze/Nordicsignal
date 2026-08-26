import unittest

from portfolio_benchmark_runtime import _combine_current_weighted, _normalize, _clean_benchmark, _clean_period


class PortfolioBenchmarkRuntimeTests(unittest.TestCase):
    def test_normalize_starts_at_zero(self):
        rows = [('2026-01-01', 100.0), ('2026-01-02', 105.0), ('2026-01-03', 95.0)]
        out = _normalize(rows)
        self.assertAlmostEqual(out['2026-01-01'], 0.0)
        self.assertAlmostEqual(out['2026-01-02'], 5.0)
        self.assertAlmostEqual(out['2026-01-03'], -5.0)

    def test_current_weighted_mix_uses_market_weights(self):
        benchmark = [('2026-01-01', 100.0), ('2026-01-02', 110.0)]
        positions = [
            {'weight': 0.75, 'series': {'2026-01-01': 0.0, '2026-01-02': 20.0}},
            {'weight': 0.25, 'series': {'2026-01-01': 0.0, '2026-01-02': -10.0}},
        ]
        out = _combine_current_weighted(benchmark, positions)
        self.assertEqual(len(out), 2)
        self.assertAlmostEqual(out[-1]['portfolio_pct'], 12.5)
        self.assertAlmostEqual(out[-1]['benchmark_pct'], 10.0)
        self.assertAlmostEqual(out[-1]['coverage_pct'], 100.0)

    def test_invalid_choices_fall_back_safely(self):
        self.assertEqual(_clean_benchmark('not-real'), 'OSEBX')
        self.assertEqual(_clean_period('20y'), '1y')


if __name__ == '__main__':
    unittest.main()
