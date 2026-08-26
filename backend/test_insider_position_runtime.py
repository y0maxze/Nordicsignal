import unittest
from datetime import date

from insider_position_runtime import build_actor_history, trade_key


class InsiderPositionRuntimeTests(unittest.TestCase):
    def test_recent_buy_without_later_sell(self):
        rows = [{
            "ticker": "LSG", "person": "Sjur Malm", "actor_type": "person",
            "role": "CFO", "transaction_type": "buy", "shares": 14500,
            "trade_date": "2026-08-25",
        }]
        history = build_actor_history(rows, now=date(2026, 8, 27))
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0]["pattern"], "recent_buy")
        self.assertTrue(history[0]["no_sale_after_latest_buy"])
        self.assertEqual(history[0]["net_observed_shares"], 14500)
        self.assertEqual(history[0]["holding_days"], 2)

    def test_quick_buy_sell_round_trip(self):
        rows = [
            {"ticker": "LSG", "entity": "FERD AS", "actor_type": "company", "transaction_type": "buy", "shares": 100000, "trade_date": "2026-08-01"},
            {"ticker": "LSG", "entity": "FERD AS", "actor_type": "company", "transaction_type": "sell", "shares": 100000, "trade_date": "2026-08-12"},
        ]
        h = build_actor_history(rows, now=date(2026, 8, 27))[0]
        self.assertEqual(h["pattern"], "quick_exit")
        self.assertEqual(h["holding_days"], 11)
        self.assertEqual(h["net_observed_shares"], 0)
        self.assertEqual(h["round_trips"][0]["days"], 11)

    def test_long_hold_before_sale(self):
        rows = [
            {"ticker": "LSG", "entity": "FERD AS", "transaction_type": "buy", "shares": 50000, "trade_date": "2026-01-01"},
            {"ticker": "LSG", "entity": "FERD AS", "transaction_type": "sell", "shares": 50000, "trade_date": "2026-08-01"},
        ]
        h = build_actor_history(rows, now=date(2026, 8, 27))[0]
        self.assertEqual(h["pattern"], "long_hold_exit")
        self.assertGreaterEqual(h["holding_days"], 180)

    def test_reaccumulating_after_prior_sale(self):
        rows = [
            {"ticker": "LSG", "person": "Example Person", "transaction_type": "buy", "shares": 1000, "trade_date": "2026-01-10"},
            {"ticker": "LSG", "person": "Example Person", "transaction_type": "sell", "shares": 1000, "trade_date": "2026-02-10"},
            {"ticker": "LSG", "person": "Example Person", "transaction_type": "buy", "shares": 2000, "trade_date": "2026-08-20"},
        ]
        h = build_actor_history(rows, now=date(2026, 8, 27))[0]
        self.assertEqual(h["pattern"], "reaccumulating")
        self.assertTrue(h["no_sale_after_latest_buy"])
        self.assertEqual(h["last_sell_date"], "2026-02-10")
        self.assertEqual(h["last_buy_date"], "2026-08-20")

    def test_actor_name_normalization_groups_same_entity(self):
        rows = [
            {"ticker": "LSG", "entity": "FERD AS", "transaction_type": "buy", "shares": 100, "trade_date": "2026-08-01"},
            {"ticker": "LSG", "entity": "Ferd AS", "transaction_type": "sell", "shares": 50, "trade_date": "2026-08-20"},
        ]
        history = build_actor_history(rows, now=date(2026, 8, 27))
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0]["buy_count"], 1)
        self.assertEqual(history[0]["sell_count"], 1)
        self.assertEqual(history[0]["net_observed_shares"], 50)

    def test_trade_key_dedupes_same_economic_event_across_sources(self):
        a = {
            "person": "Ivar Wulff", "transaction_type": "buy", "shares": 11500,
            "trade_date": "2026-08-25", "url": "https://example.test/one",
        }
        b = dict(a, url="https://another.example/two")
        self.assertEqual(trade_key("LSG", a), trade_key("LSG", b))


if __name__ == "__main__":
    unittest.main()
