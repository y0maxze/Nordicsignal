import unittest

import portfolio_instruments_runtime as runtime


class PortfolioInstrumentRuntimeTests(unittest.TestCase):
    def test_asset_class_mapping(self):
        self.assertEqual(runtime.asset_class_for('EQUITY'), 'Aksjer')
        self.assertEqual(runtime.asset_class_for('MUTUALFUND'), 'Fond')
        self.assertEqual(runtime.asset_class_for('ETF'), 'ETF')
        self.assertEqual(runtime.asset_class_for('unknown'), 'Øvrig')

    def test_allocation_includes_cash_and_sums_to_100(self):
        items = [
            {'asset_class': 'Aksjer', 'market_value': 20000},
            {'asset_class': 'Fond', 'market_value': 50000},
            {'asset_class': 'ETF', 'market_value': 10000},
            {'asset_class': 'Aksjer', 'market_value': None},
        ]
        cash = [{'market_value_nok': 20000}]
        rows, total = runtime._allocation(items, cash)
        self.assertEqual(total, 100000)
        by_class = {row['asset_class']: row for row in rows}
        self.assertAlmostEqual(by_class['Aksjer']['weight_pct'], 20.0)
        self.assertAlmostEqual(by_class['Fond']['weight_pct'], 50.0)
        self.assertAlmostEqual(by_class['ETF']['weight_pct'], 10.0)
        self.assertAlmostEqual(by_class['Kontanter']['weight_pct'], 20.0)
        self.assertAlmostEqual(sum(row['weight_pct'] for row in rows), 100.0)


if __name__ == '__main__':
    unittest.main()
