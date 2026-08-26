import unittest

from holding_purchase_lots_runtime import (
    InitializePurchaseIn,
    PurchaseLotIn,
    _aggregate_lots,
    _date_text,
    _lot_view,
)


class HoldingPurchaseLotTests(unittest.TestCase):
    def test_multiple_purchases_get_weighted_average(self):
        lots = [
            {'shares': 292, 'price_nok': 18.28},
            {'shares': 20, 'price_nok': 22.00},
            {'shares': 18, 'price_nok': 25.00},
        ]
        result = _aggregate_lots(lots)
        self.assertEqual(result['shares'], 330)
        self.assertAlmostEqual(result['cost_basis'], 6227.76, places=2)
        self.assertAlmostEqual(result['average_cost'], 18.872, places=3)

    def test_each_purchase_gets_its_own_profit_or_loss(self):
        cheap = _lot_view({'id': 1, 'shares': 292, 'price_nok': 18.28, 'source': 'manual'}, 20.0)
        expensive = _lot_view({'id': 2, 'shares': 18, 'price_nok': 25.0, 'source': 'manual'}, 20.0)
        self.assertEqual(cheap['status'], 'profit')
        self.assertGreater(cheap['unrealized_pnl'], 0)
        self.assertEqual(expensive['status'], 'loss')
        self.assertLess(expensive['unrealized_pnl'], 0)

    def test_unpriced_purchase_does_not_fake_result(self):
        row = _lot_view({'shares': 10, 'price_nok': 15.0, 'source': 'manual'}, None)
        self.assertIsNone(row['unrealized_pnl'])
        self.assertIsNone(row['unrealized_pnl_pct'])
        self.assertEqual(row['status'], 'unpriced')

    def test_new_purchase_date_is_optional(self):
        payload = PurchaseLotIn(shares=29, price_nok=21.92)
        self.assertIsNone(payload.purchase_date)
        self.assertIsNone(_date_text(payload.purchase_date))

    def test_existing_purchase_date_is_optional(self):
        payload = InitializePurchaseIn()
        self.assertIsNone(payload.purchase_date)
        self.assertIsNone(_date_text(payload.purchase_date))


if __name__ == '__main__':
    unittest.main()