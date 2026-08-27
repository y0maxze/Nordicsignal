import unittest
from unittest.mock import patch

import insider_market_runtime as im


class InsiderMarketRuntimeTests(unittest.TestCase):
    def test_cluster_buying_is_prioritized(self):
        items = [
            {"ticker":"XPLRA","company":"Xplora Technologies","trade_date":"2026-08-20","direction":"buy","signal_eligible":True,"person":"CEO One","shares":1000,"display_value":500000,"currency":"NOK","activity_type":"share_purchase"},
            {"ticker":"XPLRA","company":"Xplora Technologies","trade_date":"2026-08-20","direction":"buy","signal_eligible":True,"person":"CFO Two","shares":2000,"display_value":1100000,"currency":"NOK","activity_type":"share_purchase"},
        ]
        pulse = im._pulse_groups(items)[0]
        self.assertEqual(pulse["signal_label"], "KLYNGEKJØP")
        self.assertEqual(pulse["unique_buyers"], 2)
        self.assertIn("cluster_buying", pulse["flags"])
        self.assertIn("large_buy", pulse["flags"])

    def test_large_single_purchase_is_visible(self):
        items = [{"ticker":"STECH","company":"Soiltech","trade_date":"2026-08-26","direction":"buy","signal_eligible":True,"entity":"Riverborg B.V.","shares":50008,"display_value":4000640,"currency":"NOK","activity_type":"share_purchase"}]
        pulse = im._pulse_groups(items)[0]
        self.assertEqual(pulse["signal_label"], "STORT KJØP")
        self.assertIn("large_buy", pulse["flags"])

    def test_non_trade_mechanics_are_not_signals(self):
        for text, expected in [
            ("Primary insider transferred shares from his personal account to holding company", "internal_transfer"),
            ("Primary insider was granted subscription rights and options", "rights_or_derivatives"),
            ("Purchase under employee share purchase programme", "employee_program"),
        ]:
            kind, eligible = im._activity_type(text, {"direction":"buy"})
            self.assertEqual(kind, expected)
            self.assertFalse(eligible)

    def test_ordinary_buy_remains_signal_eligible(self):
        kind, eligible = im._activity_type("The CFO purchased 10,000 shares at NOK 50 per share", {"direction":"buy"})
        self.assertEqual(kind, "share_purchase")
        self.assertTrue(eligible)

    def test_mixed_release_classifies_each_trade_segment(self):
        rows = [
            {"direction":"buy","transaction_type":"buy","shares":500000,"price":None,"summary":"Primary insider transferred shares from personal account to holding company"},
            {"direction":"buy","transaction_type":"buy","shares":25699,"price":0.35,"transaction_value":8994.65,"summary":"Primary insider purchased 25,699 shares at NOK 0.35 per share in the market"},
        ]
        item = {"ticker":"ACED","title":"ACED: Mandatory notification of trade","url":"https://example.test/release","published_at":"2026-08-26T10:00:00+00:00"}
        html = "<html><body>Primary insider mandatory notification of trade</body></html>"
        with patch.object(im.news_runtime, "_fetch_text", return_value=html), patch.object(im.insider_runtime, "parse_trades", return_value=rows):
            out = im._extract_disclosure(item)
        self.assertEqual(out[0]["activity_type"], "internal_transfer")
        self.assertFalse(out[0]["signal_eligible"])
        self.assertEqual(out[1]["activity_type"], "share_purchase")
        self.assertTrue(out[1]["signal_eligible"])
        self.assertEqual(out[1]["currency"], "NOK")


if __name__ == "__main__":
    unittest.main()
