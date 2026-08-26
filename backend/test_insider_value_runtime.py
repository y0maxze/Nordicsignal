import unittest
from datetime import date

import insider_value_runtime as iv


class InsiderValueRuntimeTests(unittest.TestCase):
    def test_reported_transaction_price_is_actual_value(self):
        result = {
            "items": [{
                "trade_date": "2026-08-21", "transaction_type": "buy",
                "shares": 1000, "price": 42.5,
            }],
            "actor_history": [{
                "actor": "FERD AS", "timeline": [{
                    "date": "2026-08-21", "action": "buy", "shares": 1000, "price": 42.5,
                }],
            }],
        }
        out = iv.enrich_result(result, "LSG", prices={date(2026, 8, 21): 45.0})
        self.assertEqual(out["items"][0]["display_transaction_value"], 42500)
        self.assertEqual(out["items"][0]["transaction_value_basis"], "reported_transaction_price")
        self.assertEqual(out["actor_history"][0]["observed_buy_value"], 42500)
        self.assertEqual(out["actor_history"][0]["observed_buy_value_basis"], "reported_transaction_price")

    def test_missing_price_uses_clearly_labelled_market_close_estimate(self):
        prices = {date(2026, 8, 21): 46.0}
        result = {
            "items": [{
                "trade_date": "2026-08-21", "transaction_type": "buy",
                "shares": 357542, "price": None,
            }],
            "actor_history": [{
                "actor": "FERD AS", "timeline": [{
                    "date": "2026-08-21", "action": "buy", "shares": 357542, "price": None,
                }],
            }],
        }
        out = iv.enrich_result(result, "LSG", prices=prices)
        expected = 357542 * 46.0
        self.assertEqual(out["items"][0]["display_transaction_value"], expected)
        self.assertEqual(out["items"][0]["transaction_value_basis"], "market_close_estimate")
        self.assertEqual(out["items"][0]["reference_close_price"], 46.0)
        self.assertEqual(out["actor_history"][0]["observed_buy_value"], expected)
        self.assertEqual(out["actor_history"][0]["observed_buy_value_basis"], "market_close_estimate")
        self.assertEqual(out["actor_history"][0]["estimated_buy_trade_count"], 1)

    def test_reference_close_is_only_near_trade_date(self):
        prices = {
            date(2026, 8, 20): 45.0,
            date(2026, 8, 24): 48.0,
        }
        self.assertEqual(iv._reference_close("2026-08-21", prices), 45.0)
        self.assertIsNone(iv._reference_close("2026-08-10", prices))


if __name__ == "__main__":
    unittest.main()
